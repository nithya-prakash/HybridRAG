from app.core.config import get_settings


def fake_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hash embedding — no OpenAI calls needed.
    Distinct texts get distinct (L2-normalized) vectors, and texts sharing
    words end up with non-zero cosine similarity, which is enough for dense
    search to produce a meaningful, testable ranking without a real model."""
    size = get_settings().qdrant_vector_size
    vec = [0.0] * size
    for word in text.lower().split():
        vec[hash(word) % size] += 1.0
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class FakeEmbeddingBackend:
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [fake_embed(t) for t in texts]
