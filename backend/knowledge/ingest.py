"""PDF ingestion pipeline for knowledge-base documents."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .chunker import DEFAULT_MAX_CHARS, chunk_text
from .embedding import embed_text
from .pdf_loader import load_pdf_text

if TYPE_CHECKING:
    from .chroma_store import ChromaVectorStore


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
    """Extract, chunk, embed, and persist one PDF in a vector store.

    Args:
        pdf_path: Path to the source PDF file.
        metadata: Metadata shared by every chunk in this PDF.
        store: Vector store into which chunks and embeddings are written.

    Returns:
        The number of chunks successfully written to ``store``.

    Raises:
        TypeError: ``metadata`` is not a dictionary.
        FileNotFoundError: The PDF path does not exist.
        IsADirectoryError: The path is not a regular file.
        PdfLoadError: The PDF exists but cannot be parsed or read.
        EmbeddingError: The local embedding model cannot produce a vector.
    """
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")

    extracted_text = load_pdf_text(pdf_path)
    chunks = chunk_text(extracted_text)
    if not chunks:
        return 0

    chunk_metadata = dict(metadata)
    chunk_metadata["source"] = Path(pdf_path).name

    for chunk in chunks:
        vector = embed_text(chunk)
        store.add(text=chunk, vector=vector, metadata=chunk_metadata)

    return len(chunks)


__all__ = ["ingest_pdf", "ingest_pdf_to_store"]
