"""Pure, dependency-free statistical helpers for the baseline-vs-fine-tuned
comparison — no scipy (not already a dependency anywhere in this project;
adding it just for one exact test would be exactly the "unnecessary
infrastructure" this work is meant to avoid). Both tests below are standard,
closed-form, and implementable with the standard library alone.

Used by evaluate_baseline_vs_finetuned.py to distinguish what the paired
116-query comparison actually supports statistically from what's merely
observed in the aggregate metrics — see that script's module docstring and
eval/RESULTS.md's "Statistical analysis" subsection for how these numbers
are read.
"""

from __future__ import annotations

import math
import random


def mcnemar_exact_test(b: int, c: int) -> dict:
    """Exact (binomial) McNemar's test for paired binary outcomes — the
    right tool for "did model A and model B disagree on the same items more
    than chance would predict," given two classifiers scored on the SAME
    test set (as opposed to an unpaired test, which would incorrectly
    treat the two models' results as independent samples).

    `b`: number of items the first model got right and the second got
    wrong. `c`: the reverse. Items where both models agreed (both right or
    both wrong) carry no information for this test and aren't passed in.

    Under the null hypothesis (the two models are equally likely to be the
    one that's wrong, whenever they disagree), the discordant count
    `b` follows Binomial(n=b+c, p=0.5) — the exact two-sided p-value is the
    probability of a split at least as extreme as the one observed.
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_value": None, "note": "no disagreement"}

    k = min(b, c)
    # P(X <= k) for X ~ Binomial(n, 0.5), doubled for a two-sided test
    # (McNemar's test is inherently two-sided: "which model is better" is
    # symmetric under the null), capped at 1.0 since the doubled tail
    # probabilities can exceed it when k is close to n/2.
    cumulative = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
    p_value = min(1.0, 2 * cumulative)

    return {
        "b": b,
        "c": c,
        "n_discordant": n,
        "p_value": round(p_value, 6),
        "significant_at_0.05": p_value < 0.05,
    }


def paired_bootstrap_ci(
    values: list[float], n_resamples: int = 10_000, seed: int = 42, confidence: float = 0.95
) -> dict:
    """Percentile bootstrap confidence interval for the mean of `values`
    (e.g. per-query Recall@1 as 0/1, or per-query reciprocal rank) —
    resamples queries with replacement, recomputes the mean each time, and
    reports the empirical interval. Seeded for reproducibility: re-running
    this against the same `values` list produces the identical interval.

    Deliberately NOT used to manufacture a "statistically significant
    improvement" claim where none exists — see evaluate_baseline_vs_finetuned.py
    for how this is applied only to describe estimation uncertainty on each
    model's own metric, not to a difference that both scripts and
    eval/RESULTS.md already report as exactly zero.
    """
    if not values:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None}

    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()

    alpha = 1 - confidence
    lower_idx = int((alpha / 2) * n_resamples)
    upper_idx = int((1 - alpha / 2) * n_resamples) - 1
    upper_idx = min(upper_idx, n_resamples - 1)

    return {
        "n": n,
        "mean": round(sum(values) / n, 4),
        "confidence": confidence,
        "n_resamples": n_resamples,
        "ci_low": round(means[lower_idx], 4),
        "ci_high": round(means[upper_idx], 4),
    }
