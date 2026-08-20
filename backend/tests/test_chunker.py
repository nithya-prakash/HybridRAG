import hashlib

from app.services.parsing.chunker import chunk_document
from app.services.parsing.models import BLOCK_TYPE_PARAGRAPH, ParsedBlock, ParsedDocument
from app.services.parsing.tokenizer import count_tokens


def _block(
    text: str, heading_path: list[str] | None = None, page: int | None = 1
) -> ParsedBlock:
    return ParsedBlock(
        text=text,
        block_type=BLOCK_TYPE_PARAGRAPH,
        heading_path=heading_path or [],
        page_number=page,
    )


def test_chunk_empty_document_returns_no_chunks():
    assert chunk_document(ParsedDocument(blocks=[])) == []


def test_chunk_respects_max_tokens():
    blocks = [_block(" ".join(f"word{i}{j}" for i in range(15))) for j in range(20)]
    doc = ParsedDocument(blocks=blocks)

    chunks = chunk_document(doc, max_tokens=30, overlap_tokens=5)

    assert len(chunks) > 1
    assert all(c.token_count <= 30 for c in chunks)


def test_chunk_indices_are_sequential_from_zero():
    blocks = [_block(f"paragraph number {i} with a little text") for i in range(10)]
    doc = ParsedDocument(blocks=blocks)

    chunks = chunk_document(doc, max_tokens=15, overlap_tokens=0)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_overlap_present_within_same_section():
    blocks = [
        _block("Alpha bravo charlie delta echo foxtrot golf hotel india juliet."),
        _block("Kilo lima mike november oscar papa quebec romeo sierra tango."),
    ]
    doc = ParsedDocument(blocks=blocks)

    # block 1 is 16 tokens, block 2 is 20 — sized so each fits comfortably
    # alone (no oversized-block splitting) but the two together (36) don't
    # fit in one 25-token chunk, forcing a flush + overlap between them.
    chunks = chunk_document(doc, max_tokens=25, overlap_tokens=4)

    assert len(chunks) >= 2
    # the second chunk should start with a token-tail carried from the first
    first_words = chunks[0].content.split()
    second_words = chunks[1].content.split()
    overlap_candidates = set(first_words[-6:])
    assert overlap_candidates & set(second_words[:6])


def test_chunk_overlap_does_not_cross_section_boundary():
    blocks = [
        _block(
            "Section one content that ends right here with a distinctive tail phrase.",
            ["Intro"],
        ),
        _block("Section two content begins on a totally different topic.", ["Next Steps"]),
    ]
    doc = ParsedDocument(blocks=blocks)

    chunks = chunk_document(doc, max_tokens=8, overlap_tokens=6)

    intro_chunks = [c for c in chunks if c.section_path == ["Intro"]]
    next_chunks = [c for c in chunks if c.section_path == ["Next Steps"]]
    assert intro_chunks and next_chunks
    assert "distinctive" not in next_chunks[0].content


def test_chunk_metadata_fields_are_populated_correctly():
    blocks = [_block("Some content here.", heading_path=["Topic"], page=3)]
    doc = ParsedDocument(blocks=blocks)

    chunks = chunk_document(doc, max_tokens=50, overlap_tokens=0)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.section_path == ["Topic"]
    assert chunk.page_number == 3
    assert chunk.char_start == 0
    assert chunk.char_end == len("Some content here.")
    assert chunk.token_count == count_tokens(chunk.content)
    assert chunk.content_hash == hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()


def test_oversized_single_block_is_split_and_stays_within_limit():
    huge_text = " ".join(f"distinctword{i}" for i in range(500))
    doc = ParsedDocument(blocks=[_block(huge_text)])

    chunks = chunk_document(doc, max_tokens=40, overlap_tokens=0)

    assert len(chunks) > 1
    assert all(c.token_count <= 40 for c in chunks)
    # char spans for split pieces should be distinct and increasing, not all
    # collapsed onto the parent block's full span
    spans = [(c.char_start, c.char_end) for c in chunks]
    assert len(set(spans)) == len(spans)
    assert spans == sorted(spans)


def test_chunks_from_different_sections_never_merge_into_one_chunk():
    blocks = [
        _block("Short.", ["A"]),
        _block("Also short.", ["B"]),
    ]
    doc = ParsedDocument(blocks=blocks)

    chunks = chunk_document(doc, max_tokens=1000, overlap_tokens=0)

    assert len(chunks) == 2
    assert chunks[0].section_path == ["A"]
    assert chunks[1].section_path == ["B"]
