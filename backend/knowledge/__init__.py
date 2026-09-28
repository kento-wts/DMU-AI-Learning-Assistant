"""Knowledge-base document processing."""

from .chunker import DEFAULT_MAX_CHARS, chunk_text
from .embedding import EmbeddingError, cosine_similarity, embed_text
from .ingest import ingest_pdf, ingest_pdf_to_store
from .pdf_loader import PdfLoadError, load_pdf_text

__all__ = [
    "DEFAULT_MAX_CHARS",
    "EmbeddingError",
    "PdfLoadError",
    "chunk_text",
    "cosine_similarity",
    "embed_text",
    "ingest_pdf",
    "ingest_pdf_to_store",
    "load_pdf_text",
]
