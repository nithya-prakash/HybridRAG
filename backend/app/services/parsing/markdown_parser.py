from markdown_it import MarkdownIt

from app.services.parsing.errors import ParsingError
from app.services.parsing.models import (
    BLOCK_TYPE_CODE,
    BLOCK_TYPE_LIST_ITEM,
    BLOCK_TYPE_PARAGRAPH,
    ParsedBlock,
    ParsedDocument,
)
from app.services.parsing.page_estimate import estimate_page_number

_CODE_TOKEN_TYPES = ("fence", "code_block")

_md = MarkdownIt("commonmark")


def parse_markdown(content: bytes) -> ParsedDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParsingError(f"Not valid UTF-8 text: {exc}") from exc

    tokens = _md.parse(text)

    blocks: list[ParsedBlock] = []
    heading_stack: list[tuple[int, str]] = []
    list_item_depth = 0
    pending_heading_level: int | None = None
    offset = 0

    for token in tokens:
        if token.type == "heading_open":
            pending_heading_level = int(token.tag[1:])
            continue

        if token.type == "heading_close":
            pending_heading_level = None
            continue

        if token.type == "list_item_open":
            list_item_depth += 1
            continue

        if token.type == "list_item_close":
            list_item_depth = max(0, list_item_depth - 1)
            continue

        if token.type == "inline":
            text_content = token.content.strip()
            if not text_content:
                continue

            if pending_heading_level is not None:
                while heading_stack and heading_stack[-1][0] >= pending_heading_level:
                    heading_stack.pop()
                heading_stack.append((pending_heading_level, text_content))
                continue

            block_type = BLOCK_TYPE_LIST_ITEM if list_item_depth > 0 else BLOCK_TYPE_PARAGRAPH
            blocks.append(
                ParsedBlock(
                    text=text_content,
                    block_type=block_type,
                    heading_path=[title for _, title in heading_stack],
                    page_number=estimate_page_number(offset),
                )
            )
            offset += len(text_content) + 2
            continue

        if token.type in _CODE_TOKEN_TYPES:
            code_content = token.content.rstrip("\n")
            if not code_content.strip():
                continue
            blocks.append(
                ParsedBlock(
                    text=code_content,
                    block_type=BLOCK_TYPE_CODE,
                    heading_path=[title for _, title in heading_stack],
                    page_number=estimate_page_number(offset),
                )
            )
            offset += len(code_content) + 2
            continue

    return ParsedDocument(blocks=blocks)
