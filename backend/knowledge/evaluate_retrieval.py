"""Evaluate retrieval quality against the manually curated dataset.

This script is intentionally diagnostic rather than a fully automatic metric.
It reads ``evaluation_dataset.json``, runs the real :class:`Retriever` against
the persistent Chroma store, and prints complete results for manual review.

Recall is not computed here. The script only reports:

* which chunks were returned for each ``top_k`` value,
* each chunk's score, metadata, and full text,
* the manually curated ``Ground Truth candidates``,
* the ``Retrieved candidates`` found by a conservative name-overlap check.

The name-overlap check is a review aid, not a relevance verdict. Whether a
chunk truly answers the question still requires human confirmation.

Run from the repository root:

    python -m backend.knowledge.evaluate_retrieval
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

try:
    from .chroma_store import ChromaVectorStore
    from .retriever import Retriever
except ImportError:  # pragma: no cover - supports ``python <file>.py`` runs
    from backend.knowledge.chroma_store import ChromaVectorStore
    from backend.knowledge.retriever import Retriever

DEFAULT_DATASET_PATH = Path(__file__).with_name("evaluation_dataset.json")
DEFAULT_QUERY_ID = "q1"
TOP_K_VALUES = (3, 5, 10)


def _load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    """Load and lightly validate the evaluation dataset."""
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Evaluation dataset not found: {dataset_path}")

    with dataset_path.open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)

    if not isinstance(dataset, list):
        raise ValueError("evaluation_dataset.json must contain a JSON array")
    return dataset


def _find_query(
    dataset: list[dict[str, Any]],
    query_id: str,
) -> dict[str, Any]:
    """Return the dataset entry matching ``query_id``."""
    for entry in dataset:
        if entry.get("id") == query_id:
            return entry
    raise KeyError(f"No dataset entry found for id={query_id!r}")


def _normalise(text: str) -> str:
    """Normalise Unicode compatibility forms for loose name matching.

    Extracted PDF text often contains compatibility ideographs such as
    ``U+2F24`` (⼤) instead of ``U+5927`` (大). NFKC maps those forms back to
    the canonical character so candidate names can be compared meaningfully.
    The original text is never altered in the printed output.
    """
    return unicodedata.normalize("NFKC", text).strip()


def _match_ground_truth_names(
    ground_truth: list[str],
    retrieved_chunks: list[str],
) -> list[str]:
    """Return ground truth names whose normalised text appears in a chunk."""
    normalised_chunks = [_normalise(chunk) for chunk in retrieved_chunks]
    matches: list[str] = []
    for name in ground_truth:
        normalised_name = _normalise(name)
        if not normalised_name:
            continue
        if any(normalised_name in chunk for chunk in normalised_chunks):
            matches.append(name)
    return matches


def _print_separator(character: str = "=", width: int = 100) -> None:
    print(character * width)


def _print_chunk(rank: int, chunk: Any) -> None:
    print(f"Chunk #{rank}")
    print(f"Score: {chunk.score:.6f}")
    print("Metadata:")
    print(json.dumps(chunk.metadata, ensure_ascii=False, indent=2))
    print("Chunk text:")
    print(chunk.text)
    print("-" * 100)


def _evaluate_query(
    retriever: Retriever,
    entry: dict[str, Any],
) -> None:
    question = entry.get("question", "")
    ground_truth = entry.get("relevant_competitions", [])

    _print_separator()
    print(f"Query ID: {entry.get('id')}")
    print(f"Question: {question}")
    print(f"Notes: {entry.get('notes', '')}")
    print()
    print("Ground Truth candidates:")
    for index, name in enumerate(ground_truth, start=1):
        print(f"  {index}. {name}")
    print()

    for top_k in TOP_K_VALUES:
        _print_separator()
        print(f"top_k = {top_k}")
        results = retriever.retrieve(question, top_k=top_k)
        print(f"Chunks returned: {len(results)}")
        print()

        if not results:
            print("No chunks returned.")
        else:
            for rank, chunk in enumerate(results, start=1):
                _print_chunk(rank, chunk)

        retrieved_candidates = _match_ground_truth_names(
            ground_truth,
            [chunk.text for chunk in results],
        )
        print("Retrieved candidates (name-overlap check only, for manual review):")
        for index, name in enumerate(retrieved_candidates, start=1):
            print(f"  {index}. {name}")
        print(
            "Ground Truth names matched by the name-overlap check: "
            f"{len(retrieved_candidates)} / {len(ground_truth)}"
        )
        print(
            "Note: name overlap is not a relevance verdict; "
            "confirm the chunk text above manually before computing recall."
        )
        print()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Diagnostically evaluate retrieval over the evaluation dataset."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to evaluation_dataset.json.",
    )
    parser.add_argument(
        "--query-id",
        default=DEFAULT_QUERY_ID,
        help="ID of the dataset query to evaluate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the diagnostic retrieval evaluation."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    dataset = _load_dataset(args.dataset)
    entry = _find_query(dataset, args.query_id)

    store = ChromaVectorStore()
    try:
        retriever = Retriever(store)

        print(f"Chroma collection: {store.collection_name}")
        print(f"Chroma persist directory: {store.persist_directory}")
        print(f"Collection size: {len(store)}")
        print()

        _evaluate_query(retriever, entry)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
