"""Build the persistent Chroma knowledge base from the PDF folder.

This is the dedicated "produce the database" entry point: it turns every PDF in
``backend/knowledge/documents/`` into text, chunks, vectors and metadata, and
writes them into the Chroma directory the running service reads
(``data/chroma`` by default).

Design notes
------------
* Every document gets an **explicit** ``document_id`` from the table below.
  ``ingest_pdf_to_store`` would otherwise fall back to the normalised absolute
  path of the PDF, so the same document would be written twice after the
  repository is cloned or moved to another machine.
* The run is **idempotent**: chunk ids are content-derived and
  ``replace_document`` removes stale chunks, so re-running does not duplicate
  rows. Running it twice is a no-op in terms of collection size.
* Documents are addressed by the table, not by globbing the folder, so a
  missing file is reported instead of being silently skipped. Extra PDFs that
  are not in the table are reported too and left alone.
* Nothing is deleted. This script never drops the collection; refreshing a
  document replaces only that document's chunks, and it has no reset flag on
  purpose.

Run from the repository root:

    python -m backend.knowledge.build_index

Useful flags:

    --dry-run             extract and chunk only; no vectors, no writes
    --persist-directory   write somewhere other than data/chroma
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from .chroma_store import DEFAULT_PERSIST_DIRECTORY, ChromaVectorStore
from .ingest import ingest_pdf, ingest_pdf_to_store

DEFAULT_DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"

# Identity and provenance for each shipped document. The document_id values are
# stable keys: they are what retrieval filters on, what the evaluation dataset
# in evaluation_dataset.json expects, and what the provenance inventory in
# tools/rag_verification/document-inventory.json records. Changing one means
# re-importing that document and updating both files.
#
# ``major`` is a retrieval facet, not a claim about the document. School-wide
# documents carry "全校"; the one cohort-scoped document names its college.
DOCUMENT_METADATA: dict[str, dict[str, Any]] = {
    "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf": {
        "document_id": "dlmu-competition-list-2026",
        "year": 2026,
        "major": "全校",
        "document_type": "竞赛列表",
    },
    "附件.《大连海事大学本科生创新创业竞赛列表(2025年)》.pdf": {
        "document_id": "dlmu-competition-list-2025",
        "year": 2025,
        "major": "全校",
        "document_type": "竞赛列表",
    },
    "大连海事大学办公室关于印发《大连海事大学大学生创新创业竞赛管理办法》的通知.pdf": {
        "document_id": "dlmu-innovation-competition-rules-2023",
        "year": 2023,
        "major": "全校",
        "document_type": "管理办法",
    },
    "大连海事大学大学生科技创新奖励办法（正文）.pdf": {
        "document_id": "dlmu-innovation-award-2024",
        "year": 2024,
        "major": "全校",
        "document_type": "奖励办法",
    },
    "大连海事大学党政办公室关于印发《大连海事大学推荐优秀应届本科毕业生免试攻读硕士研究生办法》的通知.pdf": {
        "document_id": "dlmu-postgraduate-recommendation-2025",
        "year": 2025,
        "major": "全校",
        "document_type": "推免办法",
    },
    "大连海事大学党政办公室关于印发《大连海事大学非航海类专业本科生学籍管理规定》的通知.pdf": {
        "document_id": "dlmu-status-rules-2021",
        "year": 2021,
        "major": "全校",
        "document_type": "学籍管理规定",
    },
    "大连海事大学本科生奖学金评定办法.pdf": {
        "document_id": "dlmu-scholarship-2023",
        "year": 2023,
        "major": "全校",
        "document_type": "奖学金评定办法",
    },
    "大连海事大学学生违纪处分办法.pdf": {
        "document_id": "dlmu-discipline-2022",
        "year": 2022,
        "major": "全校",
        "document_type": "违纪处分办法",
    },
    "2025-2中队本科生综合素质测评实施细则.pdf": {
        "document_id": "dlmu-xinxikexue-2025-2-assessment",
        "year": 2025,
        "major": "信息科学技术学院",
        "document_type": "综合素质测评实施细则",
    },
    "大连海事大学学生离校请假单.pdf": {
        "document_id": "dlmu-leave-form",
        "year": 2025,
        "major": "全校",
        "document_type": "表单",
    },
}


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Turn every knowledge PDF into chunks, vectors and metadata in the "
            "persistent Chroma knowledge base."
        )
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DEFAULT_DOCUMENTS_DIR,
        help="Folder holding the PDFs (default: backend/knowledge/documents).",
    )
    parser.add_argument(
        "--persist-directory",
        type=Path,
        default=DEFAULT_PERSIST_DIRECTORY,
        help="Chroma directory to write (default: data/chroma).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and chunk only; do not embed and do not write anything.",
    )
    return parser


def _documents_in_folder(documents_dir: Path) -> list[str]:
    return sorted(path.name for path in documents_dir.glob("*.pdf"))


def build_index(
    documents_dir: Path = DEFAULT_DOCUMENTS_DIR,
    persist_directory: Path = DEFAULT_PERSIST_DIRECTORY,
) -> dict[str, Any]:
    """Import every known document and return a summary of the run.

    Args:
        documents_dir: Folder holding the source PDFs.
        persist_directory: Chroma directory to write into.

    Returns:
        A dictionary with per-document chunk counts, the collection size, the
        list of missing documents, and the list of PDFs that are not covered by
        :data:`DOCUMENT_METADATA`.
    """
    store = ChromaVectorStore(persist_directory=persist_directory)
    try:
        return _import_all(store, documents_dir)
    finally:
        store.close()


def _import_all(store: ChromaVectorStore, documents_dir: Path) -> dict[str, Any]:
    per_document: list[dict[str, Any]] = []
    missing: list[str] = []

    for name, metadata in DOCUMENT_METADATA.items():
        pdf_path = documents_dir / name
        if not pdf_path.is_file():
            missing.append(name)
            continue

        chunk_count = ingest_pdf_to_store(str(pdf_path), dict(metadata), store)
        per_document.append(
            {
                "file": name,
                "document_id": metadata["document_id"],
                "year": metadata["year"],
                "document_type": metadata["document_type"],
                "chunks": chunk_count,
            }
        )

    untracked = [
        name
        for name in _documents_in_folder(documents_dir)
        if name not in DOCUMENT_METADATA
    ]

    return {
        "per_document": per_document,
        "total_chunks": sum(entry["chunks"] for entry in per_document),
        "collection_size": len(store),
        "missing": missing,
        "untracked": untracked,
        "persist_directory": str(store.persist_directory),
        "collection_name": store.collection_name,
    }


def _dry_run(documents_dir: Path) -> dict[str, Any]:
    per_document: list[dict[str, Any]] = []
    missing: list[str] = []

    for name, metadata in DOCUMENT_METADATA.items():
        pdf_path = documents_dir / name
        if not pdf_path.is_file():
            missing.append(name)
            continue

        chunks = ingest_pdf(str(pdf_path))
        per_document.append(
            {
                "file": name,
                "document_id": metadata["document_id"],
                "year": metadata["year"],
                "document_type": metadata["document_type"],
                "chunks": len(chunks),
                "max_chunk_chars": max((len(chunk) for chunk in chunks), default=0),
            }
        )

    return {
        "per_document": per_document,
        "total_chunks": sum(entry["chunks"] for entry in per_document),
        "missing": missing,
        "untracked": [
            name
            for name in _documents_in_folder(documents_dir)
            if name not in DOCUMENT_METADATA
        ],
    }


def _report(summary: dict[str, Any], dry_run: bool) -> None:
    mode = "DRY RUN (no vectors written)" if dry_run else "INDEX BUILD"
    print(f"=== {mode} ===")
    if not dry_run:
        print(f"Chroma persist directory: {summary['persist_directory']}")
        print(f"Chroma collection:        {summary['collection_name']}")
    print()
    print(f"{'document_id':42} {'year':>5}  {'type':<14} chunks")
    for entry in summary["per_document"]:
        print(
            f"{entry['document_id']:42} {entry['year']:>5}  "
            f"{entry['document_type']:<14} {entry['chunks']}"
        )
    print()
    print(f"documents imported: {len(summary['per_document'])}")
    print(f"total chunks:       {summary['total_chunks']}")
    if not dry_run:
        print(f"collection size:    {summary['collection_size']}")
    if summary["missing"]:
        print()
        print(f"MISSING ({len(summary['missing'])}): documented but not on disk")
        for name in summary["missing"]:
            print(f"  - {name}")
    if summary["untracked"]:
        print()
        print(f"NOT IMPORTED ({len(summary['untracked'])}): on disk but not in the table")
        for name in summary["untracked"]:
            print(f"  - {name}")


def main(argv: Sequence[str] | None = None) -> int:
    """Build the knowledge base from the command line."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)

    if not args.documents_dir.is_dir():
        print(f"documents folder not found: {args.documents_dir}", file=sys.stderr)
        return 2

    if args.dry_run:
        summary = _dry_run(args.documents_dir)
        _report(summary, dry_run=True)
        return 1 if summary["missing"] else 0

    summary = build_index(args.documents_dir, args.persist_directory)
    _report(summary, dry_run=False)
    return 1 if summary["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DOCUMENT_METADATA", "build_index", "build_parser", "main"]
