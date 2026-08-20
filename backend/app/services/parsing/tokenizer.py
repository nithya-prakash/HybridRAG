from functools import lru_cache

import tiktoken

from app.core.config import get_settings


@lru_cache
def _get_encoding() -> tiktoken.Encoding:
    settings = get_settings()
    try:
        return tiktoken.encoding_for_model(settings.openai_embedding_model)
    except KeyError:
        # Unrecognized model string (e.g. a future/renamed model) — cl100k_base is
        # the encoding every current OpenAI embedding model uses.
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_encoding().encode(text))


def split_by_token_budget(text: str, max_tokens: int) -> list[str]:
    """Fallback splitter for a single block of text that alone exceeds
    max_tokens (e.g. one huge paragraph with no internal structure to chunk
    along). Splits on token boundaries directly — the pieces may cut mid-word,
    which is an acceptable tradeoff for staying under the embedding model's
    hard input limit; this path is rare in practice."""
    encoding = _get_encoding()
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return [text]
    return [
        encoding.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)
    ]


def tail_by_tokens(text: str, n: int) -> str:
    """The last n tokens of `text`, decoded back to a string — used to carry a
    bounded amount of the previous chunk's ending into the next chunk as
    overlap."""
    if n <= 0 or not text:
        return ""
    encoding = _get_encoding()
    tokens = encoding.encode(text)
    if len(tokens) <= n:
        return text
    return encoding.decode(tokens[-n:])
