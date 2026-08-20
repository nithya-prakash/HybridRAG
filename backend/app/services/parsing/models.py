from dataclasses import dataclass, field

# Content block types. Headings themselves aren't emitted as blocks — they're
# consumed by parsers to build each block's `heading_path` and never become
# chunk content directly; the heading hierarchy is fully captured in metadata.
BLOCK_TYPE_PARAGRAPH = "paragraph"
BLOCK_TYPE_LIST_ITEM = "list_item"
BLOCK_TYPE_CODE = "code"


@dataclass
class ParsedBlock:
    text: str
    block_type: str
    heading_path: list[str] = field(default_factory=list)
    page_number: int | None = None


@dataclass
class ParsedDocument:
    blocks: list[ParsedBlock] = field(default_factory=list)


@dataclass
class Chunk:
    content: str
    chunk_index: int
    page_number: int | None
    section_path: list[str]
    char_start: int
    char_end: int
    token_count: int
    content_hash: str
