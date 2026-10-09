#!/usr/bin/env python
"""Cross-check of the in-house LLM-judge scores using RAGAS.

Reads a run_eval.py report (needs the `context` field it now records per
query), scores answered, answerable queries with RAGAS faithfulness and
reference-based context precision, and writes eval/results/ragas_<ts>.json.

    pip install -r eval/requirements-ragas.txt      # separate venv
    JUDGE_BASE_URL=... JUDGE_MODEL=... JUDGE_API_KEY=... \\
        python eval/ragas_eval.py [eval/results/generation_latest.json]

Judge = any OpenAI-compatible endpoint (default local Ollama qwen2.5:7b;
Gemini/Groq/OpenAI URLs work too). Declined queries are skipped: they have no
real answer to ground.
"""
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def load_samples(report: dict) -> tuple[list[dict], int]:
    samples, skipped = [], 0
    for q in report["per_query"]:
        g = q.get("generation") or {}
        if g.get("declined") or not g.get("answer") or not g.get("context"):
            skipped += 1
            continue
        samples.append(
            {
                "id": q["id"],
                "question": q["query"],
                "contexts": [g["context"]],
                "answer": g["answer"],
                "reference": g.get("reference_answer") or "",
            }
        )
    return samples, skipped


def score(samples: list[dict]) -> dict:
    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference
    from ragas.run_config import RunConfig

    llm = LangchainLLMWrapper(
        ChatOpenAI(
            base_url=os.getenv("JUDGE_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("JUDGE_API_KEY", "ollama"),
            model=os.getenv("JUDGE_MODEL", "qwen2.5:7b"),
            temperature=0,
        )
    )
    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=s["question"],
                retrieved_contexts=s["contexts"],
                response=s["answer"],
                reference=s["reference"],
            )
            for s in samples
        ]
    )
    df = evaluate(
        dataset,
        metrics=[Faithfulness(llm=llm), LLMContextPrecisionWithReference(llm=llm)],
        run_config=RunConfig(
            # low default: hosted free tiers rate-limit tokens per minute
            max_workers=int(os.getenv("JUDGE_WORKERS", "2")),
            timeout=int(os.getenv("JUDGE_TIMEOUT", "240")),
            max_retries=int(os.getenv("JUDGE_RETRIES", "12")),
        ),
        raise_exceptions=False,
    ).to_pandas()
    cols = [c for c in ("faithfulness", "llm_context_precision_with_reference") if c in df]
    df.insert(0, "id", [s["id"] for s in samples])
    return {
        "judge": os.getenv("JUDGE_MODEL", "qwen2.5:7b"),
        "summary": {c: round(float(df[c].mean()), 3) for c in cols},
        "scored_samples": {c: int(df[c].notna().sum()) for c in cols},
        "per_query": json.loads(df[["id", *cols]].to_json(orient="records")),
    }


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS / "generation_latest.json"
    samples, skipped = load_samples(json.loads(path.read_text()))
    if not samples:
        sys.exit(f"No scorable queries in {path} (re-run run_eval.py with a chat backend).")
    report = {**score(samples), "source": path.name, "skipped_declined_or_no_context": skipped}
    out = RESULTS / f"ragas_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("judge", "summary", "scored_samples")}, indent=2))
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
