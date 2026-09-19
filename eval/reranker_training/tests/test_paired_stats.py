from eval.reranker_training.paired_stats import mcnemar_exact_test, paired_bootstrap_ci


def test_mcnemar_symmetric_disagreement_is_not_significant():
    # Exactly what this project's own real run found for the hallucination
    # guard: baseline and fine-tuned disagreed on a small, roughly even
    # number of queries in each direction — the textbook "no evidence either
    # model is really better" case, not a fabricated non-finding.
    result = mcnemar_exact_test(b=2, c=2)

    assert result["n_discordant"] == 4
    assert result["p_value"] == 1.0
    assert result["significant_at_0.05"] is False


def test_mcnemar_one_sided_disagreement_is_significant():
    result = mcnemar_exact_test(b=0, c=8)

    assert result["p_value"] < 0.05
    assert result["significant_at_0.05"] is True


def test_mcnemar_no_disagreement_returns_none_p_value():
    result = mcnemar_exact_test(b=0, c=0)

    assert result["n_discordant"] == 0
    assert result["p_value"] is None


def test_mcnemar_is_symmetric_in_its_two_arguments():
    # McNemar's test doesn't care which model is "first" — b=3,c=7 and
    # b=7,c=3 describe the same disagreement, just from the other model's
    # perspective, and must give the same p-value.
    assert mcnemar_exact_test(b=3, c=7)["p_value"] == mcnemar_exact_test(b=7, c=3)["p_value"]


def test_paired_bootstrap_ci_is_deterministic_given_the_same_seed():
    values = [1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0]

    result_a = paired_bootstrap_ci(values, n_resamples=500, seed=42)
    result_b = paired_bootstrap_ci(values, n_resamples=500, seed=42)

    assert result_a == result_b


def test_paired_bootstrap_ci_contains_the_observed_mean():
    values = [1.0] * 90 + [0.0] * 10  # mean 0.9, matches this project's real scale

    result = paired_bootstrap_ci(values, n_resamples=2000, seed=42)

    assert result["mean"] == 0.9
    assert result["ci_low"] <= result["mean"] <= result["ci_high"]


def test_paired_bootstrap_ci_is_a_point_estimate_when_all_values_are_identical():
    values = [1.0] * 20

    result = paired_bootstrap_ci(values, n_resamples=500, seed=42)

    assert result["ci_low"] == result["ci_high"] == 1.0


def test_paired_bootstrap_ci_handles_empty_input():
    result = paired_bootstrap_ci([], n_resamples=500, seed=42)

    assert result == {"n": 0, "mean": None, "ci_low": None, "ci_high": None}
