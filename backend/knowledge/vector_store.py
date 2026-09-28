"""In-memory vector storage with cosine similarity search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .embedding import cosine_similarity

DEFAULT_TOP_K = 3


@dataclass(frozen=True)
class VectorRecord:
    """A single stored text chunk and its embedding."""

    text: str
    vector: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchResult:
    """A single similarity-search result."""

    text: str
    score: float
    metadata: dict[str, Any]


class VectorStore:
    """Small, append-only vector store kept entirely in process memory."""

    def __init__(self) -> None:
        self._records: list[VectorRecord] = []
        self._dimension: int | None = None

    def __len__(self) -> int:
        return len(self._records)

    def add(
        self,
        text: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """Add one text chunk with its embedding vector and metadata."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text.strip():
            raise ValueError("text must be a non-empty string")

        dimension = _validate_vector(vector)

        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")

        if self._dimension is None:
            self._dimension = dimension
        elif dimension != self._dimension:
            raise ValueError(
                f"vector dimension must be {self._dimension}, got {dimension}"
            )

        self._records.append(
            VectorRecord(
                text=text,
                vector=[float(value) for value in vector],
                metadata=dict(metadata),
            )
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int = DEFAULT_TOP_K,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return the ``top_k`` chunks most similar to ``query_vector``."""
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be an integer greater than zero")

        query_dimension = _validate_vector(query_vector)

        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a dictionary")

        if not self._records:
            return []

        if self._dimension != query_dimension:
            raise ValueError(
                f"query vector dimension must be {self._dimension}, "
                f"got {query_dimension}"
            )

        results: list[SearchResult] = []
        for record in self._records:
            if metadata_filter and not _matches_metadata(record.metadata, metadata_filter):
                continue

            score = cosine_similarity(query_vector, record.vector)
            results.append(
                SearchResult(
                    text=record.text,
                    score=score,
                    metadata=dict(record.metadata),
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]


def _validate_vector(vector: Any) -> int:
    """Validate a numeric vector and return its dimension."""
    if isinstance(vector, (str, bytes)) or not hasattr(vector, "__len__"):
        raise TypeError("vector must be a non-empty sequence of numbers")

    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError):
        raise TypeError("vector must contain only numbers") from None

    if not values:
        raise ValueError("vector must not be empty")
    if all(value == 0.0 for value in values):
        raise ValueError("vector must not be zero-length")

    return len(values)


def _matches_metadata(
    metadata: dict[str, Any],
    metadata_filter: dict[str, Any],
) -> bool:
    """Return whether all filter keys are present and equal in ``metadata``."""
    return all(
        key in metadata and metadata[key] == value
        for key, value in metadata_filter.items()
    )


__all__ = [
    "DEFAULT_TOP_K",
    "SearchResult",
    "VectorRecord",
    "VectorStore",
]
