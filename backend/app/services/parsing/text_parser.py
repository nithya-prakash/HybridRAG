from app.services.parsing.errors import ParsingError
from app.services.parsing.models import BLOCK_TYPE_PARAGRAPH, ParsedBlock, ParsedDocument
from app.services.parsing.page_estimate import estimate_page_number

# Plain text has no heading syntax to exploit — the best structure available is
# paragraph boundaries (blank lines). heading_path is left empty; page_number
# is a best-effort estimate (see page_estimate.py).


def parse_text(content: bytes) -> ParsedDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParsingError(f"Not valid UTF-8 text: {exc}") from exc

    blocks: list[ParsedBlock] = []
    offset = 0
    for raw_paragraph in text.split("\n\n"):
        paragraph = raw_paragraph.strip()
        if paragraph:
            blocks.append(
                ParsedBlock(
                    text=paragraph,
                    block_type=BLOCK_TYPE_PARAGRAPH,
                    page_number=estimate_page_number(offset),
                )
            )
        offset += len(raw_paragraph) + 2  # +2 for the "\n\n" separator

    return ParsedDocument(blocks=blocks)
