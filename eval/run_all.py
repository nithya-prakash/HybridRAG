#!/usr/bin/env python
"""The single reproducible entrypoint for the whole evaluation suite:
dataset stats, retrieval (5 configurations), the hallucination guard's
confusion matrix, latency, generation/groundedness (opt-in — real local/
OpenAI generation is slow and/or costs money, see `--generation-sample`),
and the backend test suite + coverage. Writes each phase's own JSON report
(already produced by that phase's own script) plus one combined
`eval/results/final_report.json` and a human-readable
`eval/results/FINAL_REPORT.md`.

Each phase is a real subprocess invocation of that phase's own
already-independently-runnable script (`run_eval.py`,
`evaluate_hallucination.py`, `benchmark_latency.py`, `pytest`) — this file
does no evaluation math of its own, it only orchestrates and aggregates, so
every number in the final report is reproducible by running that phase's
script directly too.

Run from backend/:
    uv run python ../eval/run_all.py
    uv run python ../eval/run_all.py --generation-sample 20   # also run real generation eval
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
BACKEND_DIR = EVAL_DIR.parent / "backend"


def _run(cmd: list[str], label: str) -> tuple[int, str]:
    print(f"\n>>> {label}")
    print(f"    $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=BACKEND_DIR, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    print(output[-4000:])  # avoid flooding the console on a long retrieval log
    if proc.returncode != 0:
        print(f"    ⚠ {label} exited with code {proc.returncode}", file=sys.stderr)
    return proc.returncode, output


def dataset_stats() -> dict:
    dataset = json.loads((EVAL_DIR / "datasets" / "knowledge_base_eval.json").read_text())
    from collections import Counter

    categories = Counter(q["category"] for q in dataset["queries"])
    answerable = sum(1 for q in dataset["queries"] if q.get("answerable", True))
    return {
        "n_documents": len(dataset["documents"]),
        "n_questions": len(dataset["queries"]),
        "n_answerable": answerable,
        "n_unanswerable": len(dataset["queries"]) - answerable,
        "categories": dict(categories.most_common()),
        "description": dataset["description"],
    }


_COVERAGE_TOTAL_RE = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", re.MULTILINE)


def _count(pattern: str, text: str) -> int:
    # Each count is searched independently (rather than one combined
    # all-optional regex) — a single regex with every group optional and no
    # anchor matches an empty string at position 0 before ever reaching the
    # real numbers later in the line, silently returning all-zero counts.
    # Verified directly: that exact bug produced "0 passed" against a real
    # "209 passed, 1 warning in 103.22s" pytest summary line.
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def parse_pytest_output(output: str) -> dict:
    summary_line = next(
        (
            line
            for line in reversed(output.splitlines())
            if ("passed" in line or "failed" in line or "error" in line) and "=" in line
        ),
        "",
    )
    passed = _count(r"(\d+) passed", summary_line)
    failed = _count(r"(\d+) failed", summary_line)
    skipped = _count(r"(\d+) skipped", summary_line)
    errors = _count(r"(\d+) error", summary_line)

    cov_match = _COVERAGE_TOTAL_RE.search(output)
    coverage_pct = int(cov_match.group(3)) if cov_match else None

    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "total": passed + failed + skipped + errors,
        "coverage_pct": coverage_pct,
        "raw_summary_line": summary_line.strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generation-sample", type=int, default=0,
        help="run real generation/groundedness eval on this many labeled queries (default: 0 "
        "= skip, and reuse eval/results/generation_latest.json if it already exists from a "
        "prior run — see eval/RESULTS.md for why this is opt-in rather than automatic)",
    )
    parser.add_argument("--retrieval-top-k", type=int, default=10)
    parser.add_argument("--latency-n-retrieval", type=int, default=60)
    parser.add_argument("--latency-n-generation", type=int, default=5)
    parser.add_argument("--skip-tests", action="store_true", help="skip the pytest+coverage phase")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {"generated_at": datetime.now(UTC).isoformat()}

    print("=" * 72)
    print("STEP 1/6 — Dataset")
    print("=" * 72)
    report["dataset"] = dataset_stats()
    print(json.dumps(report["dataset"], indent=2))

    print("\n" + "=" * 72)
    print("STEP 2/6 — Retrieval evaluation (5 configurations)")
    print("=" * 72)
    retrieval_output_path = RESULTS_DIR / "retrieval_only_latest.json"
    _run(
        [
            "uv", "run", "python", "../eval/run_eval.py",
            "--retrieval-only", "--top-k", str(args.retrieval_top_k),
            "--output", str(retrieval_output_path),
        ],
        "Retrieval evaluation",
    )
    report["retrieval"] = (
        json.loads(retrieval_output_path.read_text()) if retrieval_output_path.exists() else None
    )

    print("\n" + "=" * 72)
    print("STEP 3/6 — Hallucination guard evaluation")
    print("=" * 72)
    _run(
        ["uv", "run", "python", "../eval/evaluate_hallucination.py"],
        "Hallucination guard evaluation",
    )
    hallucination_path = RESULTS_DIR / "hallucination_latest.json"
    report["hallucination"] = (
        json.loads(hallucination_path.read_text()) if hallucination_path.exists() else None
    )

    print("\n" + "=" * 72)
    print("STEP 4/6 — Latency benchmark")
    print("=" * 72)
    _run(
        [
            "uv", "run", "python", "../eval/benchmark_latency.py",
            "--n-retrieval", str(args.latency_n_retrieval),
            "--n-generation", str(args.latency_n_generation),
        ],
        "Latency benchmark",
    )
    latency_path = RESULTS_DIR / "latency_latest.json"
    report["latency"] = json.loads(latency_path.read_text()) if latency_path.exists() else None

    print("\n" + "=" * 72)
    print("STEP 5/6 — Generation & groundedness evaluation")
    print("=" * 72)
    generation_path = RESULTS_DIR / "generation_latest.json"
    if args.generation_sample > 0:
        _run(
            [
                "uv", "run", "python", "../eval/run_eval.py",
                "--limit-queries", str(args.generation_sample),
                "--output", str(generation_path),
            ],
            f"Generation evaluation ({args.generation_sample} queries)",
        )
    elif generation_path.exists():
        print(f"Reusing existing {generation_path} (pass --generation-sample N to re-run fresh)")
    else:
        print(
            "Skipped: no --generation-sample given and no prior generation_latest.json found. "
            "Real generation calls are slow (local CPU) or cost money (OpenAI) — this phase is "
            "opt-in. Run with --generation-sample N to include it."
        )
    report["generation"] = (
        json.loads(generation_path.read_text()) if generation_path.exists() else None
    )

    if args.skip_tests:
        print("\n" + "=" * 72)
        print("STEP 6/6 — Test suite + coverage: skipped (--skip-tests)")
        print("=" * 72)
        report["tests"] = None
    else:
        print("\n" + "=" * 72)
        print("STEP 6/6 — Test suite + coverage")
        print("=" * 72)
        _, output = _run(
            ["uv", "run", "pytest", "--cov", "--cov-report=term"], "Backend test suite + coverage"
        )
        report["tests"] = parse_pytest_output(output)

    final_report_path = RESULTS_DIR / "final_report.json"
    final_report_path.write_text(json.dumps(report, indent=2))
    print(f"\nCombined machine-readable report written to {final_report_path}")
    print("Run eval/generate_final_report.py to produce FINAL_REPORT.md from it.")


if __name__ == "__main__":
    main()
