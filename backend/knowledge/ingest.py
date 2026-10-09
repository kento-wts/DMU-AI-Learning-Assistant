"""PDF ingestion pipeline for knowledge-base documents."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .chunker import DEFAULT_MAX_CHARS, chunk_text
from .embedding import embed_text
from .pdf_loader import load_pdf_text

if TYPE_CHECKING:
    from .chroma_store import ChromaRecord, ChromaVectorStore


def ingest_pdf(
    pdf_path: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[str]:
    """Extract text from a PDF and split it into knowledge-base chunks.

    Args:
        pdf_path: Path to the source PDF file.
        max_chars: Maximum number of characters in each returned chunk.

    Returns:
        A list of chunks produced from the extracted PDF text. A PDF with no
        extractable text returns an empty list.

    Raises:
        FileNotFoundError: The PDF path does not exist.
        IsADirectoryError: The path is not a regular file.
        PdfLoadError: The PDF exists but cannot be parsed or read.
        ValueError: ``max_chars`` is not greater than zero.
    """
    extracted_text = load_pdf_text(pdf_path)
    return chunk_text(extracted_text, max_chars=max_chars)


def ingest_pdf_to_store(
    pdf_path: str,
    metadata: dict[str, Any],
    store: ChromaVectorStore,
) -> int:
    """Extract, chunk, embed, and replace one PDF in a vector store.

    The complete new version is prepared before any old records are replaced.
    A legal PDF that yields no text removes the document's old records; a PDF
    loading failure occurs before replacement and therefore leaves old records
    unchanged.

    Args:
        pdf_path: Path to the source PDF file.
        metadata: Metadata shared by every chunk in this PDF. An optional
            ``document_id`` value overrides the normalized file path identity.
        store: Vector store into which chunks and embeddings are written.

    Returns:
        The number of chunks in the imported version.

    Raises:
        TypeError: ``metadata`` is not a dictionary.
        TypeError: ``document_id`` is present but is not a string.
        ValueError: ``document_id`` is present but is empty.
        FileNotFoundError: The PDF path does not exist.
        IsADirectoryError: The path is not a regular file.
        PdfLoadError: The PDF exists but cannot be parsed or read.
        EmbeddingError: The local embedding model cannot produce a vector.
    """
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")

    document_id = _resolve_document_id(pdf_path, metadata)

    extracted_text = load_pdf_text(pdf_path)
    chunks = chunk_text(extracted_text)

    chunk_metadata = dict(metadata)
    chunk_metadata["document_id"] = document_id
    chunk_metadata["source"] = Path(pdf_path).name

    # Prepare every vector before mutating the store so a failed parse or
    # embedding call cannot remove the current document version.
    vectors = [embed_text(chunk) for chunk in chunks]

    from .chroma_store import ChromaRecord

    records: list[ChromaRecord] = []
    for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        chunk_hash = _hash_text(chunk)
        record_metadata = {
            **chunk_metadata,
            "chunk_index": chunk_index,
            "chunk_hash": chunk_hash,
        }
        records.append(
            ChromaRecord(
                id=_build_chunk_id(document_id, chunk_index, chunk_hash),
                text=chunk,
                vector=vector,
                metadata=record_metadata,
            )
        )

    # Chroma does not provide a transaction spanning the read, upsert, and
    # stale-record delete performed by replace_document.
    store.replace_document(document_id, records)

    return len(records)


def _resolve_document_id(
    pdf_path: str,
    metadata: dict[str, Any],
) -> str:
    """Return an explicit document ID or a normalized absolute PDF path."""
    explicit_document_id = metadata.get("document_id")
    if explicit_document_id is not None:
        if not isinstance(explicit_document_id, str):
            raise TypeError("document_id must be a string")
        if not explicit_document_id.strip():
            raise ValueError("document_id must be a non-empty string")
        return explicit_document_id

    normalized_path = Path(pdf_path).expanduser().resolve(strict=False)
    return os.path.normcase(str(normalized_path))


def _hash_text(text: str) -> str:
    """Return the SHA-256 hash of one chunk's UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_chunk_id(
    document_id: str,
    chunk_index: int,
    chunk_hash: str,
) -> str:
    """Build a stable chunk ID from document identity and chunk content."""
    payload = f"{document_id}\0{chunk_index}\0{chunk_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["ingest_pdf", "ingest_pdf_to_store"]
