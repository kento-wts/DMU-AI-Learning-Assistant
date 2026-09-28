"""Persistent vector storage backed by a local Chroma database."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import chromadb

from .vector_store import SearchResult

DEFAULT_COLLECTION_NAME = "knowledge_chunks"
DEFAULT_PERSIST_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "chroma"


class ChromaVectorStore:
    """Store embeddings in Chroma and search them with Chroma's index."""

    def __init__(
        self,
        persist_directory: str | Path = DEFAULT_PERSIST_DIRECTORY,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(self.persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    def __len__(self) -> int:
        return self._collection.count()

    def close(self) -> None:
        """Release the underlying Chroma client."""
        if self._client is None:
            return

        self._client.close()
        self._client = None
        self._collection = None

    def add(
        self,
        text: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """Add one text chunk, its embedding vector, and metadata."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text.strip():
            raise ValueError("text must be a non-empty string")

        values = _validate_vector(vector)

        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")

        self._collection.add(
            ids=[uuid4().hex],
            embeddings=[values],
            documents=[text],
            metadatas=[dict(metadata)],
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int = 3,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return the ``top_k`` most relevant chunks from Chroma."""
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be an integer greater than zero")

        values = _validate_vector(query_vector)

        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a dictionary")

        collection_size = self._collection.count()
        if collection_size == 0:
            return []

        response = self._collection.query(
            query_embeddings=[values],
            n_results=min(top_k, collection_size),
            where=_build_where(metadata_filter),
            include=["documents", "metadatas", "distances"],
        )

        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]

        results: list[SearchResult] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            results.append(
                SearchResult(
                    text=text,
                    score=_distance_to_score(distance),
                    metadata=dict(metadata or {}),
                )
            )

        return results


def _validate_vector(vector: Any) -> list[float]:
    """Validate a numeric vector and return normalised float values."""
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

    return values


def _build_where(
    metadata_filter: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Translate a simple equality filter into Chroma's where syntax."""
    if not metadata_filter:
        return None

    conditions = [
        {key: {"$eq": value}}
        for key, value in metadata_filter.items()
    ]

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _distance_to_score(distance: float) -> float:
    """Convert Chroma's cosine distance to a similarity score."""
    score = 1.0 - float(distance)
    return max(0.0, min(1.0, score))


__all__ = [
    "DEFAULT_COLLECTION_NAME",
    "DEFAULT_PERSIST_DIRECTORY",
    "ChromaVectorStore",
]
