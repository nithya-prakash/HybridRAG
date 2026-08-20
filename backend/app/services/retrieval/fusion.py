def reciprocal_rank_fusion[T](ranked_lists: list[list[T]], k: int) -> list[tuple[T, float]]:
    """Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, 2009).

    For every ranked list an item appears in, it contributes `1 / (k + rank)`
    to its fused score, where `rank` is 1-indexed (the top result of a list
    contributes the most). An item's final score is the sum of its
    contributions across every list it appears in — an item ranked
    reasonably well in *both* the dense and keyword lists ends up outscoring
    one ranked #1 in only one of them, which is exactly the "two independent
    signals agreeing" property hybrid search is fusing for.

    `k` (`settings.hybrid_search_rrf_k`, default 60 — the constant the
    original paper found worked well and that most hybrid-search
    implementations since have converged on) dampens how much exact rank
    position matters at the very top of a list: without it, rank 1 vs. rank 2
    would swing a score by 2x (`1/1` vs. `1/2`); with `k=60` it's roughly a
    1.6% difference (`1/61` vs. `1/62`). RRF cares much more about *which*
    items show up near the top of a list than about the precise ordering
    among them — a deliberate design choice, since dense and keyword scores
    live on completely different, incomparable scales (cosine similarity vs.
    a `ts_rank_cd` value) and fusing on rank sidesteps ever having to
    normalize or compare them directly.

    Returns `(item, score)` pairs sorted by score descending. An item present
    in only one list still gets a score (just a smaller one, from a single
    contribution) — it is not excluded from the fused result.
    """
    scores: dict[T, float] = {}
    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
