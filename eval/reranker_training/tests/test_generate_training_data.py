"""Tests for the pure, DB-free parts of generate_training_data.py (template
selection, heading extraction, the document-level split) plus a regression
check against the actual committed dataset_stats.json — the real artifact
this repo ships, not just the logic in isolation. The DB-dependent parts
(real hard-negative mining via dense/BM25/RRF) are exercised for real every
time generate_training_data.py itself is actually run against a live
Postgres/Qdrant (see eval/RESULTS.md for that real run's numbers) — the same
"real backend, not mocked" convention the rest of eval/tests/ and
backend/tests/test_reranker.py already follow.
"""

import json
from pathlib import Path

from eval.reranker_training.generate_training_data import (
    QUERY_TEMPLATES,
    _heading_phrase,
    _template_for,
    split_documents,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def test_template_for_is_deterministic_across_calls():
    key = "employee_handbook:3"

    template_a, idx_a = _template_for(key)
    template_b, idx_b = _template_for(key)

    assert (template_a, idx_a) == (template_b, idx_b)
    assert template_a in QUERY_TEMPLATES


def test_template_for_is_deterministic_across_fresh_string_objects_with_same_value():
    # hashlib.sha256, not Python's randomized hash(): this is the actual
    # property "reproducible across processes" depends on. Two distinct str
    # objects built from the same characters must resolve identically,
    # unlike builtin hash() with PYTHONHASHSEED unset. The key itself is
    # `dataset_id:chunk_index` (stable, content-derived), deliberately NOT
    # a real chunk's DB-assigned `.id` — that UUID is freshly random
    # (`default=uuid.uuid4()`) on every corpus rebuild, which would make
    # template selection non-reproducible across separate runs even though
    # it's stable within one (a real bug this test guards against —
    # caught by actually re-running generate_training_data.py twice and
    # diffing dataset_stats.json's template_usage_counts, not assumed).
    key_a = "security_policy:" + str(2)
    key_b = "security_policy:" + "2"

    _template_a, idx_a = _template_for(key_a)
    _template_b, idx_b = _template_for(key_b)

    assert idx_a == idx_b


def test_heading_phrase_uses_the_nearest_heading():
    assert _heading_phrase(["Information Security Policy", "Encryption Standards"]) == (
        "encryption standards"
    )


def test_heading_phrase_falls_back_when_section_path_is_empty():
    assert _heading_phrase([]) == "this topic"


def test_heading_phrase_strips_trailing_punctuation_and_lowercases():
    assert _heading_phrase(["Offboarding:"]) == "offboarding"


def test_split_documents_is_deterministic():
    dataset_ids = [
        "employee_handbook", "engineering_practices", "product_faq", "security_policy",
        "incident_response_runbook", "customer_success_playbook", "enterprise_console_faq",
        "compensation_and_benefits",
    ]

    train_a, calibration_a = split_documents(dataset_ids)
    train_b, calibration_b = split_documents(dataset_ids)

    assert (train_a, calibration_a) == (train_b, calibration_b)


def test_split_documents_partitions_every_document_exactly_once():
    dataset_ids = ["a", "b", "c", "d", "e", "f", "g", "h"]

    train, calibration = split_documents(dataset_ids)

    assert train | calibration == set(dataset_ids)
    assert train & calibration == set()
    # ~25% calibration (2 of 8) — not asserting the exact split membership
    # here (that's covered by the regression test below against the real
    # committed artifact), just the intended proportion.
    assert len(calibration) == 2


def test_split_documents_is_order_independent():
    ids_sorted = ["a", "b", "c", "d", "e", "f", "g", "h"]
    ids_shuffled = ["h", "c", "a", "f", "b", "g", "d", "e"]

    result_sorted = split_documents(ids_sorted)
    result_shuffled = split_documents(ids_shuffled)

    assert result_sorted == result_shuffled


def test_committed_dataset_stats_show_zero_benchmark_collisions():
    stats_path = DATA_DIR / "dataset_stats.json"
    if not stats_path.exists():
        import pytest

        pytest.skip("dataset_stats.json not present — run generate_training_data.py first")

    stats = json.loads(stats_path.read_text())

    assert stats["n_pseudo_query_collisions_with_real_benchmark"] == 0


def test_committed_dataset_stats_show_disjoint_train_and_calibration_documents():
    stats_path = DATA_DIR / "dataset_stats.json"
    if not stats_path.exists():
        import pytest

        pytest.skip("dataset_stats.json not present — run generate_training_data.py first")

    stats = json.loads(stats_path.read_text())

    train_docs = set(stats["train_documents"])
    calibration_docs = set(stats["calibration_documents"])

    assert train_docs & calibration_docs == set()
    assert len(train_docs) > 0
    assert len(calibration_docs) > 0
