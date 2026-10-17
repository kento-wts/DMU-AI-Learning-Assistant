"""Read-only PDF inspection: metadata, page count, and text preview.

This script only reads the source PDFs. It never touches the Chroma store.
Usage: python tools/rag_verification/dump_pdf_meta.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from pypdf import PdfReader

DOCUMENTS_DIR = (
    Path(__file__).resolve().parents[2] / "backend" / "knowledge" / "documents"
)
OUTPUT_DIR = Path(__file__).resolve().parent / "reference" / "pdf-text"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = []

    for pdf_path in sorted(DOCUMENTS_DIR.glob("*.pdf")):
        raw = pdf_path.read_bytes()
        reader = PdfReader(str(pdf_path))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:  # noqa: BLE001
                pages.append(f"<<extract failed: {exc}>>")

        full_text = "\n\n".join(p.strip() for p in pages if p.strip())
        (OUTPUT_DIR / (pdf_path.stem + ".txt")).write_text(full_text, encoding="utf-8")

        report.append(
            {
                "file": pdf_path.name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "pages": len(reader.pages),
                "extracted_chars": len(full_text),
                "pdf_metadata": {
                    k: str(v) for k, v in (reader.metadata or {}).items()
                },
                "head": full_text[:1800],
            }
        )

    reference_dir = Path(__file__).resolve().parent / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    (reference_dir / "pdf-inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    dump_lines: list[str] = []
    for entry in report:
        dump_lines.append("=" * 100)
        dump_lines.append(f"FILE: {entry['file']}")
        dump_lines.append(
            f"pages={entry['pages']} bytes={entry['bytes']} chars={entry['extracted_chars']}"
        )
        dump_lines.append(f"sha256={entry['sha256']}")
        dump_lines.append(
            f"pdf_metadata={json.dumps(entry['pdf_metadata'], ensure_ascii=False)}"
        )
        dump_lines.append("-" * 100)
        dump_lines.append(entry["head"])

    dump_text = "\n".join(dump_lines) + "\n"
    (reference_dir / "pdf-extraction-dump.txt").write_text(
        dump_text, encoding="utf-8", newline="\n"
    )
    print(dump_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
