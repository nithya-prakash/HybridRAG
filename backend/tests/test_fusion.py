import math

from app.services.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_matches_hand_computed_scores():
    # k=60, two lists of 3. Hand-computed:
    #   A: rank1 in list1 (1/61) + rank2 in list2 (1/62) = 0.03252245...
    #   B: rank2 in list1 (1/62) + rank1 in list2 (1/61) = 0.03252245...  (same as A)
    #   C: rank3 in list1 only    (1/63)                 = 0.01587301...
    #   D: rank3 in list2 only    (1/63)                 = 0.01587301...  (same as C)
    fused = reciprocal_rank_fusion([["A", "B", "C"], ["B", "A", "D"]], k=60)
    scores = dict(fused)

    assert math.isclose(scores["A"], 1 / 61 + 1 / 62, rel_tol=1e-9)
    assert math.isclose(scores["B"], 1 / 62 + 1 / 61, rel_tol=1e-9)
    assert math.isclose(scores["C"], 1 / 63, rel_tol=1e-9)
    assert math.isclose(scores["D"], 1 / 63, rel_tol=1e-9)
    assert scores["A"] == scores["B"]
    assert scores["C"] == scores["D"]


def test_rrf_orders_items_present_in_both_lists_above_single_list_top_rank():
    # An item ranked #2 in both lists should outscore an item ranked #1 in
    # only one of them — the "two signals agreeing" property RRF exists for.
    fused = reciprocal_rank_fusion([["only_first", "both"], ["only_second", "both"]], k=60)
    scores = dict(fused)

    assert scores["both"] > scores["only_first"]
    assert scores["both"] > scores["only_second"]


def test_rrf_result_is_sorted_descending_by_score():
    fused = reciprocal_rank_fusion([["A", "B", "C"], ["A", "C", "B"]], k=60)

    values = [score for _, score in fused]
    assert values == sorted(values, reverse=True)


def test_rrf_item_in_single_list_still_gets_a_score():
    fused = reciprocal_rank_fusion([["A"], []], k=60)

    assert dict(fused)["A"] == 1 / 61


def test_rrf_empty_lists_returns_empty():
    assert reciprocal_rank_fusion([], k=60) == []
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_rrf_larger_k_flattens_score_gap_between_adjacent_ranks():
    small_k = dict(reciprocal_rank_fusion([["A", "B"]], k=1))
    large_k = dict(reciprocal_rank_fusion([["A", "B"]], k=1000))

    small_k_gap = small_k["A"] - small_k["B"]
    large_k_gap = large_k["A"] - large_k["B"]
    assert small_k_gap > large_k_gap
