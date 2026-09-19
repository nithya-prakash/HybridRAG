"""Tests for the pure, DB-free parts of evaluate_baseline_vs_finetuned.py —
the report-shaping logic (_diff, _compute_statistics) exercised against
synthetic per-query records, not a live corpus. The DB-dependent retrieval/
reranking loop is exercised for real every time
evaluate_baseline_vs_finetuned.py itself is actually run (see eval/RESULTS.md
for that real run's numbers) — same convention as
test_generate_training_data.py.
"""

from eval.reranker_training.evaluate_baseline_vs_finetuned import _compute_statistics, _diff


def _fake_model_result(
    *, retrieval: dict, guard: dict, latency_mean: float, per_query: dict
) -> dict:
    return {
        "label": "fake",
        "model_name": "fake-model",
        "retrieval": retrieval,
        "hallucination_guard": guard,
        "reranking_latency_ms": {"mean": latency_mean, "p95": latency_mean, "n_samples": 10},
        "per_query": per_query,
    }


def test_diff_computes_finetuned_minus_baseline_for_every_reported_metric():
    baseline = _fake_model_result(
        retrieval={"recall@1": 0.9, "recall@5": 1.0, "recall@10": 1.0, "mrr": 0.95, "ndcg@5": 0.96},
        guard={"accuracy": 0.9, "precision": 0.8, "recall": 0.7, "f1": 0.75},
        latency_mean=800.0,
        per_query={},
    )
    finetuned = _fake_model_result(
        retrieval={"recall@1": 0.9, "recall@5": 1.0, "recall@10": 1.0, "mrr": 0.95, "ndcg@5": 0.96},
        guard={"accuracy": 0.9, "precision": 0.85, "recall": 0.6, "f1": 0.70},
        latency_mean=850.0,
        per_query={},
    )

    diff = _diff(baseline, finetuned)

    assert diff["recall@1"] == 0.0
    assert diff["hallucination_guard_precision"] == 0.05
    assert diff["hallucination_guard_recall"] == -0.1
    assert diff["hallucination_guard_f1"] == round(0.70 - 0.75, 4)
    assert diff["reranking_latency_mean_ms"] == 50.0


def test_compute_statistics_report_has_the_expected_schema():
    baseline = _fake_model_result(
        retrieval={}, guard={}, latency_mean=0.0,
        per_query={
            "q1": {"guard_correct": True, "recall_at_1": 1.0, "reciprocal_rank": 1.0},
            "q2": {"guard_correct": False, "recall_at_1": 0.0, "reciprocal_rank": 0.0},
        },
    )
    finetuned = _fake_model_result(
        retrieval={}, guard={}, latency_mean=0.0,
        per_query={
            "q1": {"guard_correct": True, "recall_at_1": 1.0, "reciprocal_rank": 1.0},
            "q2": {"guard_correct": True, "recall_at_1": 0.0, "reciprocal_rank": 0.0},
        },
    )

    stats = _compute_statistics(baseline, finetuned)

    assert set(stats) == {
        "n_paired_queries",
        "hallucination_guard_mcnemar",
        "recall_at_1_mcnemar",
        "recall_at_1_bootstrap_ci",
        "mrr_bootstrap_ci",
    }
    assert stats["n_paired_queries"] == 2
    for key in ("b", "c", "n_discordant", "p_value"):
        assert key in stats["hallucination_guard_mcnemar"]
    for section in (stats["recall_at_1_bootstrap_ci"], stats["mrr_bootstrap_ci"]):
        assert set(section) == {"baseline", "finetuned"}
        for model_result in section.values():
            assert set(model_result) >= {"n", "mean", "ci_low", "ci_high"}


def test_compute_statistics_guard_mcnemar_counts_only_disagreements():
    # q1: both correct (agreement, doesn't count). q2: baseline correct,
    # finetuned wrong (a "b"). q3: baseline wrong, finetuned correct (a "c").
    # q4: both wrong (agreement, doesn't count).
    baseline = _fake_model_result(
        retrieval={}, guard={}, latency_mean=0.0,
        per_query={
            "q1": {"guard_correct": True, "recall_at_1": None, "reciprocal_rank": None},
            "q2": {"guard_correct": True, "recall_at_1": None, "reciprocal_rank": None},
            "q3": {"guard_correct": False, "recall_at_1": None, "reciprocal_rank": None},
            "q4": {"guard_correct": False, "recall_at_1": None, "reciprocal_rank": None},
        },
    )
    finetuned = _fake_model_result(
        retrieval={}, guard={}, latency_mean=0.0,
        per_query={
            "q1": {"guard_correct": True, "recall_at_1": None, "reciprocal_rank": None},
            "q2": {"guard_correct": False, "recall_at_1": None, "reciprocal_rank": None},
            "q3": {"guard_correct": True, "recall_at_1": None, "reciprocal_rank": None},
            "q4": {"guard_correct": False, "recall_at_1": None, "reciprocal_rank": None},
        },
    )

    stats = _compute_statistics(baseline, finetuned)

    assert stats["hallucination_guard_mcnemar"]["b"] == 1
    assert stats["hallucination_guard_mcnemar"]["c"] == 1


def test_compute_statistics_recall_at_1_excludes_unanswerable_queries():
    # q1 has no labeled-relevant chunk (recall_at_1 is None, like an
    # out_of_corpus query) — must be excluded from the paired Recall@1
    # analysis on both sides, the same restriction the aggregate Recall@1
    # metric already applies (eval/metrics/retrieval_metrics.py).
    baseline = _fake_model_result(
        retrieval={}, guard={}, latency_mean=0.0,
        per_query={
            "q1": {"guard_correct": True, "recall_at_1": None, "reciprocal_rank": None},
            "q2": {"guard_correct": True, "recall_at_1": 1.0, "reciprocal_rank": 1.0},
        },
    )
    finetuned = _fake_model_result(
        retrieval={}, guard={}, latency_mean=0.0,
        per_query={
            "q1": {"guard_correct": True, "recall_at_1": None, "reciprocal_rank": None},
            "q2": {"guard_correct": True, "recall_at_1": 1.0, "reciprocal_rank": 1.0},
        },
    )

    stats = _compute_statistics(baseline, finetuned)

    assert stats["recall_at_1_bootstrap_ci"]["baseline"]["n"] == 1
    assert stats["recall_at_1_bootstrap_ci"]["finetuned"]["n"] == 1
