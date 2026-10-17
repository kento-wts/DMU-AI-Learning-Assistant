"""Retrieval orchestration for knowledge-base queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .embedding import embed_text
from .vector_store import SearchResult

if TYPE_CHECKING:
    from .chroma_store import ChromaVectorStore

DEFAULT_TOP_K = 3


class Retriever:
    """Turn a natural-language query into relevant stored chunks."""

    def __init__(self, store: ChromaVectorStore) -> None:
        self._store = store

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        metadata_filter: dict[str, Any] | None = None,
        min_score: float | None = None,
    ) -> list[SearchResult]:
        """Embed ``query`` and return the top matching chunks from ``store``.

        ``min_score`` is forwarded to the store as an optional similarity
        floor; ``None`` (the default) keeps the previous behaviour.
        """
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query must be a non-empty string")

        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 1:
            raise ValueError("top_k must be greater than zero")

        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a dictionary")

        if min_score is not None:
            if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
                raise TypeError("min_score must be a number or None")
            if not 0.0 <= float(min_score) <= 1.0:
                raise ValueError("min_score must be between 0 and 1")

        query_vector = embed_text(query)
        return self._store.search(
            query_vector,
            top_k=top_k,
            metadata_filter=metadata_filter,
            min_score=min_score,
        )


__all__ = ["DEFAULT_TOP_K", "Retriever"]
