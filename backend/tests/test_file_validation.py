import pytest

from app.core.file_validation import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    safe_filename,
    validate_and_normalize_file_type,
    validate_file_size,
)


def test_validate_file_size_allows_within_limit():
    validate_file_size(10, max_size_mb=1)


def test_validate_file_size_rejects_over_limit():
    with pytest.raises(FileTooLargeError):
        validate_file_size(2 * 1024 * 1024, max_size_mb=1)


def test_validate_pdf_accepts_matching_magic_bytes():
    file_type = validate_and_normalize_file_type("report.pdf", b"%PDF-1.4\n...")
    assert file_type == "pdf"


def test_validate_pdf_rejects_mismatched_content():
    with pytest.raises(UnsupportedFileTypeError):
        validate_and_normalize_file_type("report.pdf", b"not actually a pdf")


def test_validate_docx_accepts_zip_magic_bytes():
    file_type = validate_and_normalize_file_type("doc.docx", b"PK\x03\x04rest-of-zip")
    assert file_type == "docx"


def test_validate_docx_rejects_mismatched_content():
    with pytest.raises(UnsupportedFileTypeError):
        validate_and_normalize_file_type("doc.docx", b"not a zip")


def test_validate_txt_accepts_utf8_text():
    assert validate_and_normalize_file_type("notes.txt", b"hello") == "txt"


def test_validate_txt_rejects_non_utf8_binary():
    with pytest.raises(UnsupportedFileTypeError):
        validate_and_normalize_file_type("notes.txt", b"\xff\xfe\x00\x01binary-garbage")


def test_validate_markdown_accepts_utf8_text():
    assert validate_and_normalize_file_type("readme.md", b"# Title") == "md"


def test_validate_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileTypeError):
        validate_and_normalize_file_type("virus.exe", b"MZ")


def test_validate_rejects_missing_extension():
    with pytest.raises(UnsupportedFileTypeError):
        validate_and_normalize_file_type("noextension", b"whatever")


def test_safe_filename_strips_directory_components():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("/absolute/path/file.txt") == "file.txt"
    assert safe_filename("plain.txt") == "plain.txt"
