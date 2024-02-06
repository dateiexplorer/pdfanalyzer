import re
from dataclasses import dataclass
from typing import Self

import fitz

HYPERLINK_PATTERN = re.compile(r"^(http|https)://")


@dataclass
class Span:
    """Represents a span of text in a PDF document.

    Attributes:
        font_size (float): The font size of the span.
        font_family (str): The font family of the span.
        text_color (int): The color of the text.
        text (str): The actual text content of the span.
    """

    font_size: float
    font_family: str
    text_color: int
    text: str

    def has_equal_metadata(self, other: Self) -> bool:
        """Check if the metadata (all attributes except `text`) of two spans
        are equal.

        Args:
            other (Self): The other span to compare with.

        Returns:
            bool: True if the metadata is equal, False otherwise.
        """

        return (
            self.font_size == other.font_size
            and self.font_family == other.font_family
            and self.text_color == other.text_color
        )


@dataclass
class Fragment:
    """Represents a fragment of text in a PDF document.

    Attributes:
        index (int): The index of the fragment.
        spans (list[Span]): List of spans belonging to the fragment.
        font_size (float): The font size of the fragment.
        font_family (str): The font family of the fragment.
        text_color (int): The color of the text in the fragment.
        text (str): The combined text content of the spans (optional).
    """

    index: int
    spans: list[Span]
    font_size: float
    font_family: str
    text_color: int
    # The text attribute is set if the spans belong together, e.g. a
    # hyper link.
    text: str = None

    def to_string(self, join_str: str = " ") -> str:
        """Convert the fragment to a string by joining the text of its spans.

        Args:
            join_str (str): The string used to join the spans' text. Default is
                a space ' '.

        Returns:
            str: The combined text content of the spans.
        """

        return join_str.join([span.text for span in self.spans])


class PDFAnalyzer:
    """Analyzes a PDF document and provides various methods to extract
    information.
    """

    def __init__(self, path) -> None:
        """Initializes the PDFAnalyzer with a PDF document.

        Args:
            path (str): The path to the PDF document.
        """

        with fitz.open(path) as doc:
            pages = [page.get_text("dict") for page in doc]

        spans = self.extract_spans(pages)
        self._fragments = self.convert_to_fragments(spans)

    def get_fragments(self, start=0, end=None) -> list[Fragment]:
        """Get a list of fragments from the analyzed PDF document.

        Args:
            start (int): The starting index of the fragments. Default is 0.
            end (int): The ending index of the fragments. Default is None.

        Returns:
            list[Fragment]: A list of fragments.
        """

        return self._fragments[start:end]

    def get_fragment(self, index: int) -> Fragment:
        """Get a fragment from the analyzed PDF document by its index.

        Args:
            index (int): The index of the fragment.

        Returns:
            Fragment: The fragment.
        """

        return self._fragments[index]

    def extract_spans(self, pages: list[dict]) -> list[Span]:
        """
        Extract spans of text from the pages of the PDF document.

        Args:
            pages (list[dict]): A list of page dictionaries obtained from `get_text('dict')`.

        Returns:
            list[Span]: A list of spans.
        """

        spans: list[Span] = []
        # Extract texts from a list of dicts constructed with get_text('dict').
        # Each page has blocks, each blocks has lines, each lines has spans.
        # For further analyses we are only interested and can rely on the span
        # information.
        #
        # Some text blongs to each other, even if it is in other blocks.
        # The dicts stores somoe metadata, such as font and text color
        # information.
        for page in pages:
            for block in page["blocks"]:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    for span in line["spans"]:
                        spans.append(
                            Span(
                                span["size"], span["font"], span["color"], span["text"]
                            )
                        )

        return spans

    def convert_to_fragments(self, spans: list[Span]) -> list[Fragment]:
        """Convert a list of spans to fragments based on their metadata.

        Args:
            spans (list[Span]): A list of spans.

        Returns:
            list[Fragment]: A list of fragments.
        """

        fragments: list[Fragment] = []

        previous: Span = spans[0]
        fragment: list[Span] = [previous]
        index = 0
        for current in spans[1:]:
            # If the metadata (all attributes but text) differs, assume that
            # this data doesn't belong to each other. Start a new fragemnt and
            # add the old data to the list of fragments.
            if not current.has_equal_metadata(previous):
                fragments.append(
                    Fragment(
                        index,
                        fragment.copy(),
                        previous.font_size,
                        previous.font_family,
                        previous.text_color,
                    )
                )
                index += 1
                fragment.clear()

            fragment.append(current)
            previous = current

        fragments.append(
            Fragment(
                index,
                fragment.copy(),
                previous.font_size,
                previous.font_family,
                previous.text_color,
            )
        )
        return fragments

    def join_hyperlinks(self, start=0, end=None) -> None:
        """Join consecutive spans representing hyperlinks into a single fragment.

        Args:
            start (int): The starting index of the fragments to join. Default is 0.
            end (int): The ending index of the fragments to join. Default is None.
        """

        for fragment in self._fragments[start:end]:
            # 1544191 = blue
            if fragment.text_color == 1544191 and HYPERLINK_PATTERN.match(
                fragment.spans[0].text
            ):
                text = fragment.to_string(join_str="")
                fragment.text = text

    def get_paragraph(self, start=0, end=None) -> tuple[str, int]:
        """Get a paragraph of text from the analyzed PDF document.

        Args:
            start (int): The starting index of the fragments. Default is 0.
            end (int): The ending index of the fragments. Default is None.

        Returns:
            tuple[str, int]: The combined text content of the fragments and
                the index of the break.
        """

        previous: Fragment = self._fragments[start]
        paragraph: list[str] = [previous.text or previous.to_string()]
        break_index = previous.index
        for current in self._fragments[start + 1 : end]:
            if current.font_size != previous.font_size:
                break_index = current.index
                break
            else:
                text = current.text or current.to_string()
                paragraph.append(text)
            previous = current

        return "".join(paragraph), break_index

    def get_index_by_text(self, text: str, start=0, end=None) -> tuple[int, int]:
        """Get the index of a fragment and the index of its span by its text.

        Args:
            text (str): The text to search for.
            start (int): The starting index of the fragments. Default is 0.
            end (int): The ending index of the fragments. Default is None.

        Returns:
            tuple[int, int]: The index of the fragment and the index of its
                span.
        """

        for fragment in self._fragments[start:end]:
            for i, span in enumerate(fragment.spans):
                if span.text == text:
                    return fragment.index, i

        return -1, -1
