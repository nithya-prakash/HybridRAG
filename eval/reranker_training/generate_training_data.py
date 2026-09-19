#!/usr/bin/env python
"""Builds a reranker fine-tuning dataset from this project's own real corpus
(the same 8 documents / 50 chunks eval/corpus.py indexes for the 116-query
benchmark) — WITHOUT using any of that benchmark's 116 human-authored
queries, and WITHOUT touching the LLM.

Query synthesis is deterministic, not LLM-generated: every indexed chunk's
nearest section heading (`section_path[-1]`, from the real structure-aware
chunker — see app/services/parsing/chunker.py) is turned into a natural-
sounding pseudo-query via a small fixed template set, chosen per chunk by a
stable hash (not Python's randomized `hash()`, which isn't reproducible
across processes) — same chunk always yields the same template, every run,
on any machine. This is a real, disclosed limitation versus a real user
question (see eval/RESULTS.md), not hidden.

For each pseudo-query, the source chunk is the positive. Hard negatives are
mined from the REAL retrieval pipeline: real dense (Qdrant) + real BM25
(Postgres FTS) search, fused with the exact production RRF implementation
(app/services/retrieval/fusion.py) — the same pattern eval/run_eval.py's
evaluate_retrieval() already uses for its ablation study — then the top
fused candidates that are NOT the source chunk become hard negatives: real
retrieval confusion, not randomly sampled text.

Leakage prevention: the 8 documents are split 75/25 (6 train / 2
calibration) by a seeded shuffle (random.Random(42), see DOCUMENT_SPLIT_SEED
below) — hard-negative candidates for a query are restricted to the SAME
split's documents, so no chunk ever crosses the train/calibration boundary.
The 116-query benchmark is untouched by any of this (different, human-
authored query strings entirely) and is never read by this script.

Run from backend/:
    uv run python ../eval/reranker_training/generate_training_data.py

Writes eval/reranker_training/data/{train,calibration}.jsonl (gitignored —
regenerable from this script, same precedent as eval/results/*.json) and
eval/reranker_training/data/dataset_stats.json (committed — small
provenance metadata, the actual reproducibility artifact for this step).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Forced single-threaded BEFORE torch (imported transitively by
# LocalEmbeddingBackend below) does anything: multi-threaded BLAS reduction
# order for the embedding matmuls isn't guaranteed bit-identical run to run,
# which was real, measured, and traced directly — two sequential, isolated
# runs of this script's hard-negative mining differed on 4/39 train queries
# (always a near-tied candidate right at the top-4 cutoff, e.g. a `PTO`
# chunk swapping in for an unrelated query depending on a sub-percent
# similarity-score wobble), with zero difference in dataset_stats.json's
# aggregate counts, splits, or template selection — all of which stay fully
# deterministic on their own. Re-verified 0/39 differing after adding this
# (see eval/RESULTS.md). Confined to this offline, one-time generation
# script — never applied to the production RetrievalService's embedding
# path, which has no reproducibility requirement and shouldn't pay this
# script's determinism cost.
import torch  # noqa: E402

torch.set_num_threads(1)

from app.core.config import get_settings  # noqa: E402
from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.embeddings import EmbeddingBackend, LocalEmbeddingBackend  # noqa: E402
from app.core.vector_store import get_vector_store  # noqa: E402
from app.repositories.chunk_repository import ChunkRepository  # noqa: E402
from app.services.retrieval.fusion import reciprocal_rank_fusion  # noqa: E402
from eval.corpus import build_corpus, teardown_corpus  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"

# Fixed, not tuned against any evaluation result — a small, deliberately
# generic set so no single template's phrasing dominates the training
# signal. Chosen by a stable hash per chunk (see _template_for), not
# randomly at generation time, so re-running this script is byte-for-byte
# reproducible.
QUERY_TEMPLATES = [
    "What is the policy on {heading}?",
    "Can you explain {heading}?",
    "What are the requirements for {heading}?",
    "Tell me about {heading}.",
    "What does the {heading} section cover?",
    "How does {heading} work here?",
]

# Document-level split, not chunk-level or query-level: this is what
# guarantees a chunk mined as a hard negative for a training-split query can
# never also appear in the calibration split, and vice versa. 75/25 (6/2 of
# the 8 real documents) via a seeded shuffle over the sorted dataset ids —
# fixed regardless of dict/filesystem ordering, and not alphabetically
# biased (a plain sorted-then-sliced split would put every "e"-prefixed
# document in the same half by coincidence of this corpus's real names).
DOCUMENT_SPLIT_SEED = 42
CALIBRATION_FRACTION = 0.25

RETRIEVAL_TOP_K = 30  # over-fetch depth for hard-negative mining
MAX_HARD_NEGATIVES_PER_QUERY = 4


@dataclass
class Example:
    split: str
    query: str
    passage: str
    label: float
    chunk_id: str
    document_id: str
    document_dataset_id: str
    template_index: int
    is_hard_negative: bool


def _template_for(stable_chunk_key: str) -> tuple[str, int]:
    # `stable_chunk_key` must be content-derived (dataset document id +
    # chunk_index — see run()), NOT the real DB row's `chunk.id`: that UUID
    # is freshly random (`default=uuid.uuid4()`, app/models/chunk.py) on
    # every corpus rebuild, so keying on it would make template selection
    # non-reproducible across separate runs even though it's stable within
    # one — caught by actually re-running this script twice and diffing
    # `dataset_stats.json`'s template_usage_counts, not assumed.
    #
    # hashlib, not the builtin hash(): str hashing is salted per process by
    # default (PYTHONHASHSEED), which would make "the same chunk gets the
    # same template" true only within one process, not across repeated runs
    # — the opposite of what "reproducible dataset generation" requires.
    digest = hashlib.sha256(stable_chunk_key.encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(QUERY_TEMPLATES)
    return QUERY_TEMPLATES[idx], idx


def _heading_phrase(section_path: list[str]) -> str:
    if not section_path:
        return "this topic"
    heading = section_path[-1].strip().rstrip(".:").lower()
    return heading or "this topic"


def split_documents(dataset_ids: list[str]) -> tuple[set[str], set[str]]:
    """Deterministic 75/25 document-level split. Returns (train_ids,
    calibration_ids). Sorted first so the input order (dict/filesystem
    iteration) never affects the result — only DOCUMENT_SPLIT_SEED does."""
    ordered = sorted(dataset_ids)
    rng = random.Random(DOCUMENT_SPLIT_SEED)
    shuffled = ordered[:]
    rng.shuffle(shuffled)
    n_calibration = max(1, round(len(shuffled) * CALIBRATION_FRACTION))
    calibration = set(shuffled[:n_calibration])
    train = set(shuffled[n_calibration:])
    return train, calibration


async def run() -> dict:
    settings = get_settings()
    embedding_backend: EmbeddingBackend = LocalEmbeddingBackend()
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as session:
        corpus = await build_corpus(session, vector_store, embedding_backend)
        if corpus.unresolved_markers:
            print(
                "ERROR: unresolved content_markers in the eval dataset — fix before trusting "
                "anything downstream:",
                file=sys.stderr,
            )
            for m in corpus.unresolved_markers:
                print(f"  - {m}", file=sys.stderr)
            await teardown_corpus(session, vector_store, corpus)
            raise SystemExit(1)

        try:
            train_dataset_ids, calibration_dataset_ids = split_documents(
                list(corpus.documents.keys())
            )

            chunk_repo = ChunkRepository(session)

            # Real chunk rows (content + section_path), one query per chunk,
            # keyed by dataset_id so hard-negative filtering can check split
            # membership without a second DB round trip per candidate.
            chunk_split: dict[uuid.UUID, str] = {}
            chunk_dataset_id: dict[uuid.UUID, str] = {}
            chunk_by_id = {}
            chunk_rows = []  # (dataset_id, split, Chunk row)
            for dataset_id, indexed_doc in corpus.documents.items():
                split = "train" if dataset_id in train_dataset_ids else "calibration"
                rows = await chunk_repo.list_for_document(
                    indexed_doc.document_id, corpus.user_id
                )
                for row in rows:
                    chunk_split[row.id] = split
                    chunk_dataset_id[row.id] = dataset_id
                    chunk_by_id[row.id] = row
                    chunk_rows.append((dataset_id, split, row))

            real_query_texts = {q.query.strip().lower() for q in corpus.queries}

            examples: list[Example] = []
            template_counts = {i: 0 for i in range(len(QUERY_TEMPLATES))}
            collisions: list[str] = []

            for dataset_id, split, chunk in chunk_rows:
                section_path = chunk.chunk_metadata.get("section_path") or []
                heading = _heading_phrase(section_path)
                stable_chunk_key = f"{dataset_id}:{chunk.chunk_metadata['chunk_index']}"
                template, template_idx = _template_for(stable_chunk_key)
                query = template.format(heading=heading)
                template_counts[template_idx] += 1

                if query.strip().lower() in real_query_texts:
                    collisions.append(query)
                    continue

                examples.append(
                    Example(
                        split=split,
                        query=query,
                        passage=chunk.content,
                        label=1.0,
                        chunk_id=str(chunk.id),
                        document_id=str(chunk.document_id),
                        document_dataset_id=dataset_id,
                        template_index=template_idx,
                        is_hard_negative=False,
                    )
                )

                query_vector = (await embedding_backend.embed_batch([query]))[0]
                dense_hits = await vector_store.search(
                    user_id=corpus.user_id, query_vector=query_vector, top_k=RETRIEVAL_TOP_K
                )
                dense_ids = [uuid.UUID(hit.payload["chunk_id"]) for hit in dense_hits]

                bm25_hits = await chunk_repo.search_by_keyword(
                    user_id=corpus.user_id, query=query, top_k=RETRIEVAL_TOP_K
                )
                bm25_ids = [c.id for c, _score in bm25_hits]

                fused = reciprocal_rank_fusion(
                    [dense_ids, bm25_ids], k=settings.hybrid_search_rrf_k
                )

                negatives_added = 0
                for candidate_id, _score in fused:
                    if negatives_added >= MAX_HARD_NEGATIVES_PER_QUERY:
                        break
                    if candidate_id == chunk.id:
                        continue
                    if chunk_split.get(candidate_id) != split:
                        continue  # cross-split leakage guard
                    candidate_chunk = chunk_by_id.get(candidate_id)
                    if candidate_chunk is None:
                        continue
                    examples.append(
                        Example(
                            split=split,
                            query=query,
                            passage=candidate_chunk.content,
                            label=0.0,
                            chunk_id=str(candidate_id),
                            document_id=str(candidate_chunk.document_id),
                            document_dataset_id=chunk_dataset_id[candidate_id],
                            template_index=template_idx,
                            is_hard_negative=True,
                        )
                    )
                    negatives_added += 1

            if collisions:
                noun = "pseudo-query" if len(collisions) == 1 else "pseudo-queries"
                print(
                    f"ERROR: {len(collisions)} generated {noun} exactly matched a real "
                    "116-query benchmark string — refusing to write a dataset that could "
                    "leak into the held-out benchmark:",
                    file=sys.stderr,
                )
                for c in collisions:
                    print(f"  - {c!r}", file=sys.stderr)
                await teardown_corpus(session, vector_store, corpus)
                raise SystemExit(1)

            DATA_DIR.mkdir(parents=True, exist_ok=True)
            for split_name in ("train", "calibration"):
                split_examples = [e for e in examples if e.split == split_name]
                out_path = DATA_DIR / f"{split_name}.jsonl"
                with out_path.open("w") as f:
                    for ex in split_examples:
                        f.write(json.dumps(asdict(ex)) + "\n")

            stats = {
                "document_split_seed": DOCUMENT_SPLIT_SEED,
                "calibration_fraction_target": CALIBRATION_FRACTION,
                "train_documents": sorted(train_dataset_ids),
                "calibration_documents": sorted(calibration_dataset_ids),
                "n_chunks_total": len(chunk_rows),
                "n_chunks_train": sum(1 for _, s, _ in chunk_rows if s == "train"),
                "n_chunks_calibration": sum(1 for _, s, _ in chunk_rows if s == "calibration"),
                "retrieval_top_k_for_mining": RETRIEVAL_TOP_K,
                "max_hard_negatives_per_query": MAX_HARD_NEGATIVES_PER_QUERY,
                "template_usage_counts": template_counts,
                "n_examples_train": sum(1 for e in examples if e.split == "train"),
                "n_examples_train_positive": sum(
                    1 for e in examples if e.split == "train" and e.label == 1.0
                ),
                "n_examples_train_hard_negative": sum(
                    1 for e in examples if e.split == "train" and e.is_hard_negative
                ),
                "n_examples_calibration": sum(1 for e in examples if e.split == "calibration"),
                "n_examples_calibration_positive": sum(
                    1 for e in examples if e.split == "calibration" and e.label == 1.0
                ),
                "n_examples_calibration_hard_negative": sum(
                    1 for e in examples if e.split == "calibration" and e.is_hard_negative
                ),
                "n_pseudo_query_collisions_with_real_benchmark": len(collisions),
            }
            (DATA_DIR / "dataset_stats.json").write_text(json.dumps(stats, indent=2))
            return stats
        finally:
            await teardown_corpus(session, vector_store, corpus)


def main() -> None:
    stats = asyncio.run(run())
    print()
    print("=" * 72)
    print("RERANKER TRAINING DATASET GENERATED")
    print("=" * 72)
    print(f"train documents       : {stats['train_documents']}")
    print(f"calibration documents : {stats['calibration_documents']}")
    print(
        f"train examples        : {stats['n_examples_train']} "
        f"({stats['n_examples_train_positive']} positive, "
        f"{stats['n_examples_train_hard_negative']} hard negative)"
    )
    print(
        f"calibration examples  : {stats['n_examples_calibration']} "
        f"({stats['n_examples_calibration_positive']} positive, "
        f"{stats['n_examples_calibration_hard_negative']} hard negative)"
    )
    print(f"template usage        : {stats['template_usage_counts']}")
    print(f"benchmark collisions  : {stats['n_pseudo_query_collisions_with_real_benchmark']}")
    print("=" * 72)
    print(f"\nWrote {DATA_DIR / 'train.jsonl'}, {DATA_DIR / 'calibration.jsonl'}, "
          f"{DATA_DIR / 'dataset_stats.json'}")


if __name__ == "__main__":
    main()
