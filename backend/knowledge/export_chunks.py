"""Export the text and chunk stages as files you can read and diff.

``build_index.py`` writes vectors into Chroma, where the chunk text is only
visible through a query. This tool writes the two stages *before* the vectors
so they can be inspected directly:

* ``<output-dir>/text/<document_id>.txt``  - the extracted page text, NFKC-normalised
* ``<output-dir>/chunks.jsonl``            - one JSON object per chunk, with the
  same metadata that ends up in Chroma, plus the full chunk text
* ``<output-dir>/chunks-overview.md``      - a readable index: per document, every
  chunk's index, length and first line

No embedding model is loaded and no vector store is touched, so this runs in
seconds and needs no network. Chunk counts are identical to what
``build_index.py`` imports because both call the same ``load_pdf_text`` and
``chunk_text``.

Run from the repository root:

    python -m backend.knowledge.export_chunks
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .build_index import DEFAULT_DOCUMENTS_DIR, DOCUMENT_METADATA
from .chunker import chunk_text
from .pdf_loader import load_pdf_text

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "exports"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Write the extracted text and the chunks to plain files."
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DEFAULT_DOCUMENTS_DIR,
        help="Folder holding the PDFs (default: backend/knowledge/documents).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where the exports are written (default: data/exports).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1200,
        help="Chunk size limit, must match the value used for the index.",
    )
    return parser


def export(
    documents_dir: Path,
    output_dir: Path,
    max_chars: int = 1200,
) -> dict[str, Any]:
    """Write the text and chunk stages and return a summary."""
    text_dir = output_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    per_document: list[dict[str, Any]] = []
    missing: list[str] = []
    jsonl_lines: list[str] = []
    overview: list[str] = [
        "# Chunk overview",
        "",
        f"- source folder: `{documents_dir}`",
        f"- chunk limit: {max_chars} characters",
        "",
    ]

    for name, metadata in DOCUMENT_METADATA.items():
        pdf_path = documents_dir / name
        if not pdf_path.is_file():
            missing.append(name)
            continue

        document_id = str(metadata["document_id"])
        text = load_pdf_text(str(pdf_path))
        chunks = chunk_text(text, max_chars=max_chars)

        (text_dir / f"{document_id}.txt").write_text(text, encoding="utf-8", newline="\n")

        overview.append(f"## {document_id}")
        overview.append("")
        overview.append(f"- file: `{name}`")
        overview.append(f"- year: {metadata['year']}   type: {metadata['document_type']}")
        overview.append(f"- extracted text: {len(text)} characters")
        overview.append(f"- chunks: {len(chunks)}")
        overview.append("")
        overview.append("| # | chars | first line |")
        overview.append("| --- | --- | --- |")

        for index, chunk in enumerate(chunks):
            chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            jsonl_lines.append(
                json.dumps(
                    {
                        "document_id": document_id,
                        "source": name,
                        "year": metadata["year"],
                        "major": metadata["major"],
                        "document_type": metadata["document_type"],
                        "chunk_index": index,
                        "chunk_hash": chunk_hash,
                        "chars": len(chunk),
                        "text": chunk,
                    },
                    ensure_ascii=False,
                )
            )
            first_line = chunk.strip().splitlines()[0] if chunk.strip() else ""
            if len(first_line) > 70:
                first_line = first_line[:70] + "…"
            overview.append(f"| {index} | {len(chunk)} | {first_line} |")

        overview.append("")
        per_document.append(
            {
                "document_id": document_id,
                "file": name,
                "text_chars": len(text),
                "chunks": len(chunks),
                "max_chunk_chars": max((len(chunk) for chunk in chunks), default=0),
            }
        )

    (output_dir / "chunks.jsonl").write_text(
        "\n".join(jsonl_lines) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "chunks-overview.md").write_text(
        "\n".join(overview), encoding="utf-8", newline="\n"
    )

    return {
        "output_dir": str(output_dir),
        "per_document": per_document,
        "total_chunks": sum(entry["chunks"] for entry in per_document),
        "total_text_chars": sum(entry["text_chars"] for entry in per_document),
        "missing": missing,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Write the exports from the command line."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)

    if not args.documents_dir.is_dir():
        print(f"documents folder not found: {args.documents_dir}", file=sys.stderr)
        return 2

    summary = export(args.documents_dir, args.output_dir, args.max_chars)

    print(f"output dir: {summary['output_dir']}")
    print()
    print(f"{'document_id':42} {'chars':>7} {'chunks':>7} {'max chunk':>10}")
    for entry in summary["per_document"]:
        print(
            f"{entry['document_id']:42} {entry['text_chars']:>7} "
            f"{entry['chunks']:>7} {entry['max_chunk_chars']:>10}"
        )
    print()
    print(f"documents:    {len(summary['per_document'])}")
    print(f"chunks:       {summary['total_chunks']}")
    print(f"text chars:   {summary['total_text_chars']}")
    print()
    print("files written:")
    print(f"  {Path(summary['output_dir']) / 'text'}\\<document_id>.txt   (extracted text)")
    print(f"  {Path(summary['output_dir']) / 'chunks.jsonl'}              (all chunks + metadata)")
    print(f"  {Path(summary['output_dir']) / 'chunks-overview.md'}        (readable index)")

    if summary["missing"]:
        print()
        print(f"MISSING ({len(summary['missing'])}): documented but not on disk")
        for name in summary["missing"]:
            print(f"  - {name}")

    return 1 if summary["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_OUTPUT_DIR", "build_parser", "export", "main"]
