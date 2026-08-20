# DOCX/TXT/MD have no page concept in the source file itself (pagination is a
# rendering-time property Word/a browser computes, not something stored in the
# document) — PDF is the only format with real, exact page numbers. This is a
# rough heuristic stand-in ("best estimate", not exact) so every chunk still
# carries *some* page_number for citation UX, clearly less trustworthy than
# PDF's.
CHARS_PER_PAGE_ESTIMATE = 3000


def estimate_page_number(char_offset: int) -> int:
    return (char_offset // CHARS_PER_PAGE_ESTIMATE) + 1
