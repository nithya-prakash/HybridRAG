"""Standard IR retrieval-quality metrics, computed against a labeled set of
relevant ids per query. Every function takes a ranked list of retrieved ids
(best match first) and a set of ids known to be relevant, so the same code
works regardless of which retrieval variant (dense-only, BM25-only,
fused+reranked) produced the ranking.

Relevance is binary throughout (a chunk either is or isn't one of the
hand-labeled relevant chunks for a query) — the eval dataset doesn't grade
degrees of relevance, so graded-relevance NDCG variants would be undocumented
precision this harness doesn't actually have.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence


def recall_at_k[T: Hashable](retrieved: Sequence[T], relevant: set[T], k: int) -> float:
    """Fraction of relevant ids present in the top k retrieved ids.

    Undefined (returns None) when `relevant` is empty — there is nothing to
    recall, and averaging in a 0 or 1 would misrepresent queries that have no
    correct answer (e.g. a deliberately out-of-corpus question) as retrieval
    successes or failures.
    """
    if not relevant:
        return None
    hits = len(set(retrieved[:k]) & relevant)
    return hits / len(relevant)


def reciprocal_rank[T: Hashable](retrieved: Sequence[T], relevant: set[T]) -> float:
    """1 / (rank of the first relevant id), 0 if none of `retrieved` is
    relevant. Rank is 1-indexed, over the full retrieved list (not truncated
    to a k) — MRR conventionally measures how far down the *entire* ranking
    a user has to look, not just whether a hit lands in some fixed window.
    """
    if not relevant:
        return None
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k[T: Hashable](retrieved: Sequence[T], relevant: set[T], k: int) -> float:
    """Normalized Discounted Cumulative Gain over the top k retrieved ids,
    with binary relevance (gain=1 for a relevant id, 0 otherwise).
    """
    if not relevant:
        return None
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, item in enumerate(retrieved[:k], start=1)
        if item in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def mean_over_queries(values: Sequence[float | None]) -> tuple[float, int]:
    """Average a per-query metric, skipping queries where it was undefined
    (empty relevant set). Returns (mean, number_of_queries_included) so
    callers can report how many queries actually contributed — silently
    averaging over a shrunk denominator would hide that some queries (e.g.
    the out-of-corpus one) don't participate in retrieval scoring at all.
    """
    included = [v for v in values if v is not None]
    if not included:
        return 0.0, 0
    return sum(included) / len(included), len(included)
