"""Command-line entry point for importing one PDF into Chroma."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .chroma_store import ChromaVectorStore
from .ingest import ingest_pdf_to_store


def ingest_document(
    pdf_path: str | Path,
    metadata: dict[str, Any],
    store: ChromaVectorStore | None = None,
) -> dict[str, Any]:
    """Import one PDF and return a summary of the data written to Chroma.

    Args:
        pdf_path: Path to the source PDF.
        metadata: Metadata shared by every chunk from this PDF.
        store: Optional vector store. When omitted, the default persistent
            Chroma store is used.

    Returns:
        A dictionary containing the PDF filename, imported chunk count, stored
        metadata, and the Chroma storage details.
    """
    path = Path(pdf_path)
    chunk_metadata = dict(metadata)
    store = store if store is not None else ChromaVectorStore()

    chunk_count = ingest_pdf_to_store(str(path), chunk_metadata, store)

    return {
        "filename": path.name,
        "chunk_count": chunk_count,
        "metadata": {**chunk_metadata, "source": path.name},
        "persist_directory": str(store.persist_directory),
        "collection_name": store.collection_name,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Import one PDF document into the Chroma knowledge base."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to import.")
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Document year, for example 2026.",
    )
    parser.add_argument(
        "--major",
        required=True,
        help="Relevant major, for example 软件工程.",
    )
    parser.add_argument(
        "--document-type",
        required=True,
        help="Document type, for example 管理办法.",
    )
    parser.add_argument(
        "--document-id",
        help=(
            "Stable document identity. When omitted, the normalized PDF "
            "path is used."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the import from command-line arguments."""
    args = build_parser().parse_args(argv)

    metadata = {
        "year": args.year,
        "major": args.major,
        "document_type": args.document_type,
    }
    if args.document_id is not None:
        metadata["document_id"] = args.document_id

    result = ingest_document(args.pdf_path, metadata)

    print(f"PDF file: {result['filename']}")
    print(f"Chunks imported: {result['chunk_count']}")
    print(
        "Metadata: "
        + json.dumps(result["metadata"], ensure_ascii=False, indent=2)
    )
    print(f"Chroma persist directory: {result['persist_directory']}")
    print(f"Chroma collection: {result['collection_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ingest_document", "main"]
