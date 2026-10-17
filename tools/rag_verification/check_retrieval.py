"""Retrieval check record for the curated question set.

Builds a throwaway Chroma corpus from the 10 knowledge PDFs with the real
embedding model and runs every question in
``backend/knowledge/evaluation_dataset.json`` through the real
:class:`~backend.knowledge.retriever.Retriever`.

For each question the record shows:

* the curated expectation (``expected_behaviour``, ``expected_document_ids``),
* every returned chunk with its score, ``document_id`` and source file,
* which curated ground-truth points appear verbatim in a returned chunk.

This is a **review aid, not an accuracy metric**. A quote appearing in a
returned chunk only means the text was retrieved; whether the chunk actually
answers the question still needs a human. No recall or precision figure is
derived here, and none may be quoted from this file.

Nothing in the repository's own index (``data/chroma``) is opened or modified:
the corpus lives in a ``tempfile.TemporaryDirectory``.

Run from the repository root:

    python tools/rag_verification/check_retrieval.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import verify_rag as harness  # noqa: E402  (same directory, reuses the corpus builder)

from backend.knowledge.chroma_store import ChromaVectorStore  # noqa: E402
from backend.knowledge.embedding import embed_text  # noqa: E402
from backend.knowledge.pdf_loader import load_pdf_text  # noqa: E402
from backend.knowledge.retriever import Retriever  # noqa: E402

DEFAULT_DATASET_PATH = REPO_ROOT / "backend" / "knowledge" / "evaluation_dataset.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "retrieval-check-record.txt"
REFERENCE_PATH = Path(__file__).resolve().parent / "reference" / "retrieval-check-record.txt"
DEFAULT_TOP_K = 5


def _normalise(text: str) -> str:
    """NFKC-normalise and collapse whitespace for a tolerant substring check."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _first_rank_containing(point: str, chunks: list[str]) -> int | None:
    """Return the 1-based rank of the first chunk containing ``point``."""
    needle = _normalise(point)
    if not needle:
        return None
    for rank, chunk in enumerate(chunks, start=1):
        if needle in _normalise(chunk):
            return rank
    return None


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Record real retrieval results for the curated question set."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = parser.parse_args(argv)

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    if not isinstance(dataset, list):
        raise ValueError("the dataset must be a JSON array")

    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line)

    emit("=" * 96)
    emit("Retrieval check record - curated question set")
    emit("=" * 96)
    # Placeholders / relative paths only: this record is committed.
    emit("repository root:  <repo root>")
    emit(f"dataset:          {args.dataset.relative_to(REPO_ROOT) if args.dataset.is_relative_to(REPO_ROOT) else '<custom>'}")
    emit(f"questions:        {len(dataset)}")
    emit(f"top_k:            {args.top_k}")
    emit("")
    emit("A quote appearing below only means the text was retrieved. It is not a")
    emit("relevance verdict and not recall; a human still has to read the chunk.")
    emit("")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        persist_dir = Path(temp_dir) / "chroma"
        store = ChromaVectorStore(
            persist_directory=persist_dir,
            collection_name="rag_retrieval_check",
        )
        try:
            chunk_count = harness._ingest_corpus(store, load_pdf_text, embed_text)
            emit("throwaway Chroma dir (the repo index is never opened): <temp>/chroma")
            emit(f"corpus chunks: {chunk_count}   len(store): {len(store)}")
            emit("")

            retriever = Retriever(store)
            expected_hit_top3 = 0
            expected_total = 0
            negative_top_scores: list[tuple[str, float]] = []

            for entry in dataset:
                question = entry["question"]
                behaviour = entry.get("expected_behaviour", "legacy")
                expected_ids = list(entry.get("expected_document_ids") or [])
                points = list(entry.get("ground_truth_points") or [])

                results = retriever.retrieve(question, top_k=args.top_k)
                chunks = [result.text for result in results]
                returned_ids = [str(result.metadata.get("document_id", "?")) for result in results]

                emit("-" * 96)
                emit(f"{entry['id']}  [{behaviour}]  top_k={args.top_k}")
                emit(f"Q: {question}")

                if expected_ids:
                    expected_total += 1
                    if any(doc_id in expected_ids for doc_id in returned_ids[:3]):
                        expected_hit_top3 += 1
                    emit(f"expected document_id(s): {', '.join(expected_ids)}")
                else:
                    emit("expected document_id(s): (none - this question should not be answered from the corpus)")

                emit(f"chunks returned: {len(results)}")
                emit("")
                for rank, result in enumerate(results, start=1):
                    doc_id = str(result.metadata.get("document_id", "?"))
                    source = str(result.metadata.get("source", "?"))
                    marker = " [expected doc]" if doc_id in expected_ids else ""
                    emit(f"  #{rank}  score={result.score:.4f}  {doc_id}{marker}")
                    emit(f"       source: {source}")

                if results and behaviour == "not_in_corpus":
                    negative_top_scores.append((entry["id"], results[0].score))

                if points:
                    emit("")
                    emit("  curated ground-truth points found in the returned text (review aid):")
                    for point in points:
                        rank = _first_rank_containing(point, chunks)
                        label = f"chunk #{rank}" if rank else "not present in the returned chunks"
                        emit(f"    - [{label}] {point}")

                emit("")
                emit("  human check: does any returned chunk above answer the question, and")
                emit("               does the answer respect the document's scope and year?")
                emit("               ( ) yes   ( ) partly   ( ) no        reviewer: __________")
                emit("")

            emit("=" * 96)
            emit("Summary (indicators, not scores)")
            emit("=" * 96)
            emit(f"questions with an expected document: {expected_total}")
            emit(f"  of those, expected document present in top_3: {expected_hit_top3}")
            emit("  (the rest are returned-chunk evidence for humans to judge, not failures)")
            if negative_top_scores:
                emit("")
                emit("not_in_corpus questions - highest score returned:")
                for question_id, score in negative_top_scores:
                    emit(f"  {question_id}: {score:.4f}")
                emit("  A high score here means an unrelated chunk looked similar; there is")
                emit("  no minimum-score threshold in the pipeline, so nothing rejects it.")
            emit("")
            emit("No accuracy figure is computed. The curated set is small and its")
            emit("ground truth is partial by design.")
        finally:
            store.close()

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if REFERENCE_PATH.parent.is_dir():
        REFERENCE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"Reference copy updated: {REFERENCE_PATH}")
    print(f"\nRecord written to {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
