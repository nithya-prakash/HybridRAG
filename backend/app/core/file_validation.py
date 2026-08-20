from pathlib import Path

# extension -> normalized file_type stored on the document row
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
}


class UnsupportedFileTypeError(Exception):
    pass


class FileTooLargeError(Exception):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(f"{size_bytes} bytes exceeds limit of {max_bytes} bytes")


def validate_file_size(size_bytes: int, max_size_mb: int) -> None:
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise FileTooLargeError(size_bytes, max_bytes)


def validate_and_normalize_file_type(filename: str, content: bytes) -> str:
    """Validate the file's extension against the allowlist and sanity-check its
    content against that extension's magic bytes — a client-supplied extension
    alone is not trustworthy. Returns the normalized file_type to store."""
    extension = Path(filename).suffix.lower()
    file_type = ALLOWED_EXTENSIONS.get(extension)
    if file_type is None:
        raise UnsupportedFileTypeError(f"Unsupported file extension: {extension or '(none)'}")

    if file_type == "pdf" and not content.startswith(b"%PDF-"):
        raise UnsupportedFileTypeError("File extension is .pdf but content is not a valid PDF")

    if file_type == "docx" and not content.startswith(b"PK\x03\x04"):
        raise UnsupportedFileTypeError("File extension is .docx but content is not a valid DOCX")

    if file_type in ("txt", "md"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileTypeError(
                f"File extension is {extension} but content is not valid UTF-8 text"
            ) from exc

    return file_type


def safe_filename(filename: str) -> str:
    """Strip any directory components from a client-supplied filename so it can't
    be used for path traversal when building a storage key."""
    return Path(filename).name
