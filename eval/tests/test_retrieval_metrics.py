from eval.metrics.retrieval_metrics import (
    mean_over_queries,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k_counts_hits_within_k_only():
    retrieved = ["a", "b", "c", "d"]
    relevant = {"c", "z"}

    assert recall_at_k(retrieved, relevant, k=2) == 0.0
    assert recall_at_k(retrieved, relevant, k=3) == 0.5
    assert recall_at_k(retrieved, relevant, k=4) == 0.5


def test_recall_at_k_is_undefined_for_empty_relevant_set():
    assert recall_at_k(["a", "b"], set(), k=5) is None


def test_reciprocal_rank_uses_first_relevant_hit_over_the_full_list():
    assert reciprocal_rank(["a", "b", "c"], {"c"}) == 1 / 3
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0


def test_reciprocal_rank_is_zero_when_nothing_relevant_is_retrieved():
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0


def test_reciprocal_rank_is_undefined_for_empty_relevant_set():
    assert reciprocal_rank(["a", "b"], set()) is None


def test_ndcg_at_k_is_perfect_when_relevant_items_are_ranked_first():
    # Two relevant items, both in the top 2 -> ideal ranking achieved.
    assert ndcg_at_k(["a", "b", "c"], {"a", "b"}, k=3) == 1.0


def test_ndcg_at_k_penalizes_a_relevant_item_ranked_lower():
    # One relevant item at rank 1 scores higher than the same item at rank 3.
    high = ndcg_at_k(["a", "b", "c"], {"a"}, k=3)
    low = ndcg_at_k(["b", "c", "a"], {"a"}, k=3)
    assert high == 1.0
    assert 0 < low < high


def test_ndcg_at_k_is_zero_when_no_relevant_item_is_retrieved():
    assert ndcg_at_k(["a", "b"], {"z"}, k=2) == 0.0


def test_ndcg_at_k_is_undefined_for_empty_relevant_set():
    assert ndcg_at_k(["a", "b"], set(), k=2) is None


def test_ndcg_at_k_ideal_denominator_is_capped_by_k_not_by_relevant_set_size():
    # 3 relevant items exist, but k=1 means only the ideal top-1 is achievable
    # even in the best possible ranking -> a single top-ranked hit is perfect.
    assert ndcg_at_k(["a", "x", "y"], {"a", "b", "c"}, k=1) == 1.0


def test_mean_over_queries_skips_none_values_and_reports_included_count():
    mean, n = mean_over_queries([1.0, None, 0.5, None])
    assert mean == 0.75
    assert n == 2


def test_mean_over_queries_all_none_returns_zero_and_zero_count():
    assert mean_over_queries([None, None]) == (0.0, 0)
