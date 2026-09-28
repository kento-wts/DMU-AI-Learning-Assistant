"""Debug retrieval against the real Chroma knowledge base."""

from __future__ import annotations

import json
import sys

from .chroma_store import ChromaVectorStore
from .retriever import Retriever


def main() -> int:
    """Retrieve chunks for a real question and print the results."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    query = "2026年大连海事大学本科生有哪些创新创业竞赛？"
    store = ChromaVectorStore()
    retriever = Retriever(store)

    print(f"Query: {query}")
    print(f"Chroma collection: {store.collection_name}")
    print(f"Chroma persist directory: {store.persist_directory}")

    results = retriever.retrieve(query, top_k=3)
    print(f"Results returned: {len(results)}")
    print()

    for rank, result in enumerate(results, start=1):
        print(f"Rank {rank}")
        print(f"Similarity score: {result.score:.6f}")
        print(
            "Metadata: "
            + json.dumps(result.metadata, ensure_ascii=False, indent=2)
        )
        print("Chunk text:")
        print(result.text)
        print("-" * 60)

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
