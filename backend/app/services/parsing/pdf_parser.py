from collections import Counter

import pymupdf

from app.services.parsing.errors import ParsingError
from app.services.parsing.models import BLOCK_TYPE_PARAGRAPH, ParsedBlock, ParsedDocument

# Heading detection heuristic: PDFs generally carry no semantic structure (no
# equivalent of DOCX's "Heading 1" style or Markdown's `#`) unless the author
# added bookmarks, which many don't. Font size relative to the document's most
# common ("body text") size is a reasonable proxy — real headings are usually
# both larger than body text and short. This is a heuristic, not authoritative;
# a PDF with an embedded outline/table-of-contents could do better, but reading
# that back onto extracted text blocks is significantly more involved and is
# left as a documented future improvement (see ARCHITECTURE.md).
_HEADING_MAX_WORDS = 20
_LEVEL_1_RATIO = 1.5
_LEVEL_2_RATIO = 1.3
_LEVEL_3_RATIO = 1.15


def _block_text_and_size(block: dict) -> tuple[str, float]:
    lines_text: list[str] = []
    sizes: list[float] = []
    for line in block.get("lines", []):
        span_texts = []
        for span in line.get("spans", []):
            span_texts.append(span.get("text", ""))
            sizes.append(span.get("size", 0.0))
        lines_text.append("".join(span_texts))
    text = " ".join(t.strip() for t in lines_text if t.strip())
    size = max(sizes) if sizes else 0.0
    return text, size


def _heading_level(text: str, size: float, body_size: float) -> int | None:
    if body_size <= 0 or len(text.split()) > _HEADING_MAX_WORDS:
        return None
    ratio = size / body_size
    if ratio >= _LEVEL_1_RATIO:
        return 1
    if ratio >= _LEVEL_2_RATIO:
        return 2
    if ratio >= _LEVEL_3_RATIO:
        return 3
    return None


def parse_pdf(content: bytes) -> ParsedDocument:
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ParsingError(f"Could not open PDF: {exc}") from exc

    try:
        pages_blocks: list[list[dict]] = []
        size_counts: Counter[float] = Counter()

        for page in doc:
            page_dict = page.get_text("dict")
            blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]
            pages_blocks.append(blocks)
            for block in blocks:
                text, size = _block_text_and_size(block)
                if size > 0 and text:
                    # Weight by character count, not block count: body text is
                    # usually far more voluminous than headings even when a
                    # document has many short heading blocks, so this is a much
                    # more reliable "what's the body size" signal than a per-
                    # block tally (which a heading-heavy, text-light document
                    # could easily tie or invert).
                    size_counts[round(size)] += len(text)

        if not size_counts:
            return ParsedDocument(blocks=[])

        body_size = size_counts.most_common(1)[0][0]

        parsed_blocks: list[ParsedBlock] = []
        heading_stack: list[tuple[int, str]] = []

        for page_index, blocks in enumerate(pages_blocks):
            page_number = page_index + 1
            for block in blocks:
                text, size = _block_text_and_size(block)
                if not text:
                    continue

                level = _heading_level(text, size, body_size)
                if level is not None:
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, text))
                    continue

                parsed_blocks.append(
                    ParsedBlock(
                        text=text,
                        block_type=BLOCK_TYPE_PARAGRAPH,
                        heading_path=[title for _, title in heading_stack],
                        page_number=page_number,
                    )
                )

        return ParsedDocument(blocks=parsed_blocks)
    except ParsingError:
        raise
    except Exception as exc:
        raise ParsingError(f"Could not read PDF content: {exc}") from exc
    finally:
        doc.close()
