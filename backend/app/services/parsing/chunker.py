import hashlib

from app.core.config import get_settings
from app.services.parsing.models import Chunk, ParsedBlock, ParsedDocument
from app.services.parsing.tokenizer import count_tokens, split_by_token_budget, tail_by_tokens


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_chunk(
    chunk_index: int,
    content: str,
    page_number: int | None,
    section_path: list[str],
    char_start: int,
    char_end: int,
) -> Chunk:
    return Chunk(
        content=content,
        chunk_index=chunk_index,
        page_number=page_number,
        section_path=section_path,
        char_start=char_start,
        char_end=char_end,
        token_count=count_tokens(content),
        content_hash=_content_hash(content),
    )


def _group_into_sections(blocks: list[ParsedBlock]) -> list[list[ParsedBlock]]:
    """A section is a maximal run of consecutive blocks sharing the same
    heading_path. Chunking (and overlap) happens within a section, never
    across one — content under different headings shouldn't bleed together."""
    sections: list[list[ParsedBlock]] = []
    current: list[ParsedBlock] = []
    current_path: list[str] | None = None
    for block in blocks:
        if block.heading_path != current_path:
            if current:
                sections.append(current)
            current = []
            current_path = block.heading_path
        current.append(block)
    if current:
        sections.append(current)
    return sections


def _chunk_section(
    section_blocks: list[ParsedBlock],
    section_spans: list[tuple[int, int]],
    section_path: list[str],
    start_index: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_index = start_index

    pending_texts: list[str] = []
    pending_tokens = 0
    pending_char_start: int | None = None
    pending_char_end: int | None = None
    pending_page: int | None = None
    overlap_prefix = ""
    overlap_prefix_tokens = 0

    def joined_pending() -> str:
        return "\n\n".join(pending_texts)

    def full_pending_content() -> str:
        body = joined_pending()
        return f"{overlap_prefix}\n\n{body}" if overlap_prefix else body

    def effective_budget() -> int:
        # Budget left for *new* content once this chunk's overlap prefix (if
        # any) is accounted for — the hard max_tokens ceiling always applies
        # to overlap + new content together, never to new content alone.
        return max(max_tokens - overlap_prefix_tokens, 1)

    def flush() -> None:
        nonlocal chunk_index, pending_texts, pending_tokens
        nonlocal pending_char_start, pending_char_end, pending_page
        nonlocal overlap_prefix, overlap_prefix_tokens
        if not pending_texts:
            return
        content = full_pending_content()
        chunks.append(
            _make_chunk(
                chunk_index,
                content,
                pending_page,
                section_path,
                pending_char_start or 0,
                pending_char_end or 0,
            )
        )
        chunk_index += 1
        overlap_prefix = tail_by_tokens(joined_pending(), overlap_tokens) if overlap_tokens else ""
        overlap_prefix_tokens = count_tokens(overlap_prefix)
        if overlap_prefix_tokens >= max_tokens:
            # Pathological only if overlap_tokens is configured close to/over
            # max_tokens — drop the overlap rather than leave no room for any
            # new content at all.
            overlap_prefix = ""
            overlap_prefix_tokens = 0
        pending_texts = []
        pending_tokens = 0
        pending_char_start = None
        pending_char_end = None
        pending_page = None

    for block, (start, end) in zip(section_blocks, section_spans, strict=True):
        block_tokens = count_tokens(block.text)

        if block_tokens > max_tokens:
            flush()
            overlap_prefix = ""
            overlap_prefix_tokens = 0
            piece_cursor = start
            for piece in split_by_token_budget(block.text, max_tokens):
                piece_start = piece_cursor
                piece_end = piece_start + len(piece)
                piece_cursor = piece_end
                chunks.append(
                    _make_chunk(
                        chunk_index,
                        piece,
                        block.page_number,
                        section_path,
                        piece_start,
                        piece_end,
                    )
                )
                chunk_index += 1
            continue

        if pending_tokens + block_tokens > effective_budget():
            if pending_texts:
                flush()
            if block_tokens > effective_budget():
                # Even alone, this block plus the carried-over overlap would
                # exceed max_tokens — drop the overlap for this chunk so the
                # hard token limit always wins over the overlap "nice to have".
                overlap_prefix = ""
                overlap_prefix_tokens = 0

        if pending_char_start is None:
            pending_char_start = start
            pending_page = block.page_number
        pending_char_end = end
        pending_texts.append(block.text)
        pending_tokens += block_tokens

    flush()
    return chunks


def chunk_document(
    parsed: ParsedDocument,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    settings = get_settings()
    if max_tokens is None:
        max_tokens = settings.chunk_max_tokens
    if overlap_tokens is None:
        overlap_tokens = settings.chunk_overlap_tokens

    # A single canonical concatenation of every block's text, in document
    # order, gives char_start/char_end a coordinate system independent of how
    # chunking/overlap later group things — every block's span is fixed here,
    # before any packing decisions are made.
    spans: list[tuple[int, int]] = []
    cursor = 0
    for block in parsed.blocks:
        start = cursor
        end = start + len(block.text)
        spans.append((start, end))
        cursor = end + 2  # matches the "\n\n" separator used when joining

    sections = _group_into_sections(parsed.blocks)

    all_chunks: list[Chunk] = []
    span_offset = 0
    for section_blocks in sections:
        section_spans = spans[span_offset : span_offset + len(section_blocks)]
        span_offset += len(section_blocks)
        section_path = section_blocks[0].heading_path
        section_chunks = _chunk_section(
            section_blocks,
            section_spans,
            section_path,
            start_index=len(all_chunks),
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        all_chunks.extend(section_chunks)

    return all_chunks
