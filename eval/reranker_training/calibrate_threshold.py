#!/usr/bin/env python
"""Checks whether the fine-tuned reranker's score distribution has shifted
enough from the baseline's to justify recalibrating
`rag_min_rerank_score` (currently -0.6, calibrated against the BASELINE
model's real score distribution — see app/core/config.py) — and if so, runs
the same exhaustive-threshold-sweep methodology already used twice in this
repo's history (eval/RESULTS.md's "-3.0 -> -3.3" and "-3.3 -> -0.6"
sections) to find a real candidate.

Deliberately uses the CALIBRATION split (eval/reranker_training/data/
calibration.jsonl — 2 documents held out from training, never used for a
single gradient step) rather than the 116-query held-out benchmark: tuning
a threshold against the benchmark that then reports that same threshold's
performance would be leakage, even though this script only reads rerank
scores, not labels used for training.

Run from backend/ (after both generate_training_data.py and
train_reranker.py):
    uv run python ../eval/reranker_training/calibrate_threshold.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.core.config import get_settings  # noqa: E402
from app.core.reranker import BASELINE_RERANKER_MODEL, CrossEncoderReranker  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
MODELS_DIR = Path(__file__).parent / "models"
RESULTS_DIR = Path(__file__).parent.parent / "results"

# If the two models' calibration-split score distributions are this close
# (median absolute difference in the score each model assigns the exact
# same (query, passage) pair), the current threshold is judged still valid
# and no sweep is performed — recalibrating over noise this small would be
# fitting stochastic fine-tuning variance, not a real shift.
SCORE_SHIFT_THRESHOLD = 1.0


def _load_calibration_pairs() -> list[dict]:
    path = DATA_DIR / "calibration.jsonl"
    if not path.exists():
        print(f"ERROR: {path} not found — run generate_training_data.py first.", file=sys.stderr)
        raise SystemExit(1)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run() -> dict:
    settings = get_settings()
    examples = _load_calibration_pairs()
    finetuned_path = MODELS_DIR / "finetuned"
    if not finetuned_path.exists():
        print(
            f"ERROR: no fine-tuned checkpoint at {finetuned_path} — run train_reranker.py first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    baseline_reranker = CrossEncoderReranker(model_name=BASELINE_RERANKER_MODEL)
    finetuned_reranker = CrossEncoderReranker(model_name=str(finetuned_path))

    by_query: dict[str, list[dict]] = {}
    for ex in examples:
        by_query.setdefault(ex["query"], []).append(ex)

    baseline_records: list[dict] = []
    finetuned_records: list[dict] = []
    for query, group in by_query.items():
        ids = [uuid.uuid4() for _ in group]
        candidates = list(zip(ids, (ex["passage"] for ex in group), strict=True))
        baseline_scores = dict(await baseline_reranker.rerank(query, candidates))
        finetuned_scores = dict(await finetuned_reranker.rerank(query, candidates))
        for cid, ex in zip(ids, group, strict=True):
            baseline_records.append({"score": baseline_scores[cid], "label": ex["label"]})
            finetuned_records.append({"score": finetuned_scores[cid], "label": ex["label"]})

    def _median_abs(records: list[dict]) -> float:
        vals = sorted(r["score"] for r in records)
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    baseline_median = _median_abs(baseline_records)
    finetuned_median = _median_abs(finetuned_records)
    score_shift = abs(finetuned_median - baseline_median)
    recalibration_justified = score_shift >= SCORE_SHIFT_THRESHOLD

    result = {
        "current_threshold": settings.rag_min_rerank_score,
        "calibration_split_n_examples": len(examples),
        "baseline_median_score": round(baseline_median, 4),
        "finetuned_median_score": round(finetuned_median, 4),
        "score_shift": round(score_shift, 4),
        "score_shift_threshold_for_recalibration": SCORE_SHIFT_THRESHOLD,
        "recalibration_justified": recalibration_justified,
    }

    if recalibration_justified:
        candidates = sorted({r["score"] for r in finetuned_records})
        sweep_results = []
        for t in candidates:
            tp = tn = fp = fn = 0
            for r in finetuned_records:
                declined = r["score"] < t
                should_decline = r["label"] == 0.0
                if should_decline and declined:
                    tp += 1
                elif not should_decline and not declined:
                    tn += 1
                elif not should_decline and declined:
                    fp += 1
                else:
                    fn += 1
            n = tp + tn + fp + fn
            accuracy = (tp + tn) / n if n else 0.0
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            sweep_results.append(
                {"threshold": round(t, 4), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
                 "accuracy": round(accuracy, 4), "precision": round(precision, 4),
                 "recall": round(recall, 4), "f1": round(f1, 4)}
            )
        sweep_results.sort(key=lambda r: r["f1"], reverse=True)
        result["sweep_top_5_by_f1"] = sweep_results[:5]
        result["recommended_threshold"] = sweep_results[0]["threshold"] if sweep_results else None
    else:
        result["sweep_top_5_by_f1"] = None
        result["recommended_threshold"] = None

    return result


def print_summary(result: dict) -> None:
    print()
    print("=" * 72)
    print("HALLUCINATION-GUARD THRESHOLD CALIBRATION CHECK (calibration split)")
    print("=" * 72)
    print(f"current threshold (-> baseline)  : {result['current_threshold']}")
    print(f"calibration examples              : {result['calibration_split_n_examples']}")
    print(f"baseline median score              : {result['baseline_median_score']}")
    print(f"finetuned median score             : {result['finetuned_median_score']}")
    print(f"score shift                        : {result['score_shift']}")
    print(f"recalibration justified            : {result['recalibration_justified']}")
    if result["recalibration_justified"]:
        print()
        print("Top candidate thresholds by F1 (calibration split only):")
        for row in result["sweep_top_5_by_f1"]:
            print(f"  {row}")
        print(f"\nRecommended: {result['recommended_threshold']}")
    else:
        print()
        print(
            "No recalibration performed — score shift is below the "
            f"{result['score_shift_threshold_for_recalibration']} threshold judged meaningful. "
            "rag_min_rerank_score is left unchanged."
        )
    print("=" * 72)
    print()


def main() -> None:
    result = asyncio.run(run())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "reranker_threshold_calibration.json").write_text(json.dumps(result, indent=2))
    print_summary(result)


if __name__ == "__main__":
    main()
