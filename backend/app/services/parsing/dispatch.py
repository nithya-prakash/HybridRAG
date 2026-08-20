from collections.abc import Callable

from app.services.parsing.docx_parser import parse_docx
from app.services.parsing.errors import ParsingError
from app.services.parsing.markdown_parser import parse_markdown
from app.services.parsing.models import ParsedDocument
from app.services.parsing.pdf_parser import parse_pdf
from app.services.parsing.text_parser import parse_text

_PARSERS: dict[str, Callable[[bytes], ParsedDocument]] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "txt": parse_text,
    "md": parse_markdown,
}


def parse_document(file_type: str, content: bytes) -> ParsedDocument:
    parser = _PARSERS.get(file_type)
    if parser is None:
        raise ParsingError(f"No parser registered for file_type={file_type!r}")
    return parser(content)
