from pathlib import Path

import pytest

from app.services.parsing import ParsingError, parse_document
from app.services.parsing.models import BLOCK_TYPE_CODE, BLOCK_TYPE_LIST_ITEM

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def test_parse_pdf_extracts_two_pages_with_headings():
    doc = parse_document("pdf", _read_fixture("sample.pdf"))

    pages = {b.page_number for b in doc.blocks}
    assert pages == {1, 2}

    intro_blocks = [b for b in doc.blocks if b.heading_path == ["Introduction"]]
    background_blocks = [b for b in doc.blocks if b.heading_path == ["Background"]]
    assert intro_blocks, "expected content under the Introduction heading"
    assert background_blocks, "expected content under the Background heading"
    assert all(b.page_number == 1 for b in intro_blocks)
    assert all(b.page_number == 2 for b in background_blocks)


def test_parse_pdf_corrupt_file_raises_parsing_error():
    with pytest.raises(ParsingError):
        parse_document("pdf", _read_fixture("corrupt.pdf"))


def test_parse_docx_extracts_nested_headings():
    doc = parse_document("docx", _read_fixture("sample.docx"))

    section_paths = {tuple(b.heading_path) for b in doc.blocks}
    assert ("Project Overview",) in section_paths
    assert ("Project Overview", "Goals") in section_paths
    assert ("Project Overview", "Non-Goals") in section_paths

    goals_text = " ".join(
        b.text for b in doc.blocks if b.heading_path == ["Project Overview", "Goals"]
    )
    assert "RAG pipeline" in goals_text


def test_parse_docx_corrupt_file_raises_parsing_error():
    with pytest.raises(ParsingError):
        parse_document("docx", _read_fixture("corrupt.docx"))


def test_parse_markdown_extracts_headings_lists_and_code():
    doc = parse_document("md", _read_fixture("sample.md"))

    heading_paths = {tuple(b.heading_path) for b in doc.blocks}
    assert ("Knowledge Base Guide",) in heading_paths
    assert ("Knowledge Base Guide", "Uploading Documents") in heading_paths
    assert ("Knowledge Base Guide", "Formatting Tips") in heading_paths

    list_items = [b for b in doc.blocks if b.block_type == BLOCK_TYPE_LIST_ITEM]
    assert {b.text for b in list_items} == {"PDF", "DOCX", "TXT", "Markdown"}

    code_blocks = [b for b in doc.blocks if b.block_type == BLOCK_TYPE_CODE]
    assert len(code_blocks) == 1
    assert 'print("hello world")' in code_blocks[0].text


def test_parse_text_splits_paragraphs_with_no_headings():
    doc = parse_document("txt", _read_fixture("sample.txt"))

    assert len(doc.blocks) == 3
    assert all(b.heading_path == [] for b in doc.blocks)
    assert all(b.page_number == 1 for b in doc.blocks)
    assert "first paragraph" in doc.blocks[0].text
    assert "third and final" in doc.blocks[2].text


def test_parse_text_rejects_non_utf8_binary():
    with pytest.raises(ParsingError):
        parse_document("txt", b"\xff\xfe\x00\x01binary-garbage")


def test_parse_document_unknown_type_raises():
    with pytest.raises(ParsingError):
        parse_document("exe", b"whatever")
