"""Persistent vector storage backed by a local Chroma database."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import chromadb

from .vector_store import SearchResult

DEFAULT_COLLECTION_NAME = "knowledge_chunks"
DEFAULT_PERSIST_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "chroma"


@dataclass(frozen=True)
class ChromaRecord:
    """One record to write to Chroma."""

    id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class StoredRecord:
    """One record read back from Chroma without exposing Chroma internals."""

    id: str
    text: str
    metadata: dict[str, Any]


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
        record_id: str | None = None,
    ) -> None:
        """Add one record while preserving the original UUID-based behavior."""
        if record_id is None:
            record_id = uuid4().hex

        self.add_many(
            [
                ChromaRecord(
                    id=record_id,
                    text=text,
                    vector=vector,
                    metadata=metadata,
                )
            ]
        )

    def add_many(self, records: Sequence[ChromaRecord]) -> None:
        """Add multiple records in one Chroma call.

        Explicit IDs are required if callers need deterministic identity.
        Chroma raises an error when an explicit ID already exists.
        """
        validated = _validate_records(records)
        if not validated:
            return

        self._collection.add(
            ids=[record.id for record in validated],
            embeddings=[record.vector for record in validated],
            documents=[record.text for record in validated],
            metadatas=[record.metadata for record in validated],
        )

    def upsert(self, record: ChromaRecord) -> None:
        """Insert or replace one record with a caller-provided ID."""
        self.upsert_many([record])

    def upsert_many(self, records: Sequence[ChromaRecord]) -> None:
        """Insert or replace multiple records in one Chroma call."""
        validated = _validate_records(records)
        if not validated:
            return

        self._collection.upsert(
            ids=[record.id for record in validated],
            embeddings=[record.vector for record in validated],
            documents=[record.text for record in validated],
            metadatas=[record.metadata for record in validated],
        )

    def replace_document(
        self,
        document_id: str,
        records: Sequence[ChromaRecord],
    ) -> None:
        """Replace all stored chunks for one document.

        New records are upserted first. IDs that existed before the update but
        are absent from the new version are then deleted. This ordering avoids
        deleting the old version if the upsert fails, but the operation is not
        transactionally atomic because Chroma does not provide a transaction
        spanning both writes here.
        """
        if not isinstance(document_id, str):
            raise TypeError("document_id must be a string")
        if not document_id.strip():
            raise ValueError("document_id must be a non-empty string")

        validated = _validate_records(records)
        for record in validated:
            if record.metadata.get("document_id") != document_id:
                raise ValueError(
                    "every record metadata must contain the document_id"
                )

        existing_ids = set(
            self.get_ids({"document_id": document_id})
        )
        new_ids = {record.id for record in validated}

        if validated:
            self.upsert_many(validated)

        stale_ids = sorted(existing_ids - new_ids)
        if stale_ids:
            self._collection.delete(ids=stale_ids)

    def get_ids(
        self,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[str]:
        """Return record IDs matching an equality metadata filter."""
        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a dictionary")

        response = self._collection.get(
            where=_build_where(metadata_filter),
            include=["metadatas"],
        )
        return list(response.get("ids") or [])

    def get_records(
        self,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[StoredRecord]:
        """Return stored records matching an equality metadata filter."""
        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a dictionary")

        response = self._collection.get(
            where=_build_where(metadata_filter),
            include=["documents", "metadatas"],
        )

        ids = response.get("ids") or []
        documents = response.get("documents") or []
        metadatas = response.get("metadatas") or []

        return [
            StoredRecord(
                id=record_id,
                text=text,
                metadata=dict(metadata or {}),
            )
            for record_id, text, metadata in zip(ids, documents, metadatas)
        ]

    def delete_by_document_id(self, document_id: str) -> None:
        """Delete every record belonging to one document."""
        if not isinstance(document_id, str):
            raise TypeError("document_id must be a string")
        if not document_id.strip():
            raise ValueError("document_id must be a non-empty string")

        self._collection.delete(
            where=_build_where({"document_id": document_id}),
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


def _validate_records(records: Sequence[ChromaRecord]) -> list[ChromaRecord]:
    """Validate and copy a sequence of records for a Chroma write."""
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError("records must be a sequence of ChromaRecord")

    validated: list[ChromaRecord] = []
    for record in records:
        if not isinstance(record, ChromaRecord):
            raise TypeError("records must contain only ChromaRecord values")
        if not isinstance(record.id, str):
            raise TypeError("record id must be a string")
        if not record.id:
            raise ValueError("record id must not be empty")
        if not isinstance(record.text, str):
            raise TypeError("text must be a string")
        if not record.text.strip():
            raise ValueError("text must be a non-empty string")
        if not isinstance(record.metadata, dict):
            raise TypeError("metadata must be a dictionary")

        validated.append(
            ChromaRecord(
                id=record.id,
                text=record.text,
                vector=_validate_vector(record.vector),
                metadata=dict(record.metadata),
            )
        )

    return validated


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
    "ChromaRecord",
    "DEFAULT_COLLECTION_NAME",
    "DEFAULT_PERSIST_DIRECTORY",
    "StoredRecord",
    "ChromaVectorStore",
]
