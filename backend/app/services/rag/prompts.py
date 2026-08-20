import re
import uuid
from dataclasses import dataclass

from app.models.chunk import Chunk as ChunkModel
from app.services.retrieval.models import RetrievedChunk

ANSWER_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant that answers questions using ONLY the numbered "
    "context excerpts provided in the most recent system message below. Follow these "
    "rules strictly:\n"
    "1. Answer only using information contained in the context excerpts. Do not use "
    "outside knowledge, even if you know the answer.\n"
    "2. EVERY sentence that states a fact MUST end with the bracketed number of the "
    "excerpt it came from, e.g. [1] — never write a factual sentence without one. If a "
    "sentence draws on more than one excerpt, cite all of them, e.g. [1][2].\n"
    "3. If the context excerpts do not contain enough information to answer the "
    'question, say so explicitly — for example: "I don\'t have enough information in the '
    'indexed documents to answer this question." Do not guess, speculate, or fabricate '
    "an answer.\n"
    "4. Keep the answer concise and directly responsive to the question.\n\n"
    "Example:\n"
    "Context:\n\n"
    '[1] (from "handbook.md")\nParis is the capital of France.\n\n'
    "Question: What is the capital of France?\n"
    "Answer: Paris is the capital of France [1]."
)

INSUFFICIENT_CONTEXT_MESSAGE = (
    "I don't have enough information in the indexed documents to answer this question."
)

_CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")


@dataclass
class CitationSource:
    """The minimal shape `build_context_block`/`extract_citations` need from
    a chunk, regardless of whether it came fresh from `RetrievalService`
    (generation time) or was re-fetched from Postgres by id (citation
    reconstruction on a later read) — see `from_retrieved_chunks`/
    `from_chunk_models`."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    page_number: int | None


@dataclass
class Citation:
    marker: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    excerpt: str


def from_retrieved_chunks(chunks: list[RetrievedChunk]) -> list[CitationSource]:
    return [
        CitationSource(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            content=c.content,
            page_number=c.page_number,
        )
        for c in chunks
    ]


def from_chunk_models(rows: list[ChunkModel]) -> list[CitationSource]:
    return [
        CitationSource(
            chunk_id=row.id,
            document_id=row.document_id,
            content=row.content,
            page_number=row.chunk_metadata.get("page_number"),
        )
        for row in rows
    ]


def build_context_block(
    sources: list[CitationSource], filenames: dict[uuid.UUID, str]
) -> tuple[str, dict[int, CitationSource]]:
    """Numbers each source `[1]`, `[2]`, ... in the given order — that order
    becomes the citation marker the model is instructed to cite by, so
    callers must pass sources in the same rank order they want cited first.
    Returns the formatted block plus the marker -> source mapping needed to
    resolve markers back to real chunks after generation."""
    index_map: dict[int, CitationSource] = {}
    lines: list[str] = []
    for i, source in enumerate(sources, start=1):
        index_map[i] = source
        filename = filenames.get(source.document_id, "unknown document")
        page = f", page {source.page_number}" if source.page_number is not None else ""
        lines.append(f'[{i}] (from "{filename}"{page})\n{source.content}')
    return "\n\n".join(lines), index_map


def build_messages(
    history: list[tuple[str, str]], context_block: str, question: str
) -> list[dict[str, str]]:
    """Prior turns are included as plain role/content pairs, without their
    own context blocks — only the *current* turn's retrieved context is
    injected, as a fresh system message right before the question. Otherwise
    every past turn's context would keep riding along in every future
    prompt, growing the token cost of a long conversation without bound and
    letting old, possibly-superseded context bleed into new answers."""
    messages = [{"role": "system", "content": ANSWER_SYSTEM_PROMPT}]
    messages.extend({"role": role, "content": content} for role, content in history)
    messages.append({"role": "system", "content": f"Context:\n\n{context_block}"})
    messages.append({"role": "user", "content": question})
    return messages


def extract_citations(
    answer_text: str, index_map: dict[int, CitationSource], filenames: dict[uuid.UUID, str]
) -> list[Citation]:
    """Scans the generated answer for `[n]` markers and resolves each to the
    context source it referred to — deliberately not a claim-by-claim NLP
    attribution, since the system prompt already instructs the model to
    place markers inline; trusting that instruction and parsing its output
    is far more reliable than trying to re-derive which sentence used which
    source after the fact. Only markers that actually appear in the answer
    are returned — not every chunk that was retrieved, only the ones the
    model says it used. Unknown marker numbers (a model citing `[9]` when
    only 5 sources existed) are silently dropped rather than raised, since a
    hallucinated citation number is a model output-formatting slip, not
    something that should crash answer generation."""
    seen: dict[int, Citation] = {}
    for match in _CITATION_MARKER_RE.finditer(answer_text):
        marker = int(match.group(1))
        if marker in seen or marker not in index_map:
            continue
        source = index_map[marker]
        seen[marker] = Citation(
            marker=marker,
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            filename=filenames.get(source.document_id, "unknown document"),
            page_number=source.page_number,
            excerpt=source.content[:280],
        )
    return [seen[marker] for marker in sorted(seen)]
