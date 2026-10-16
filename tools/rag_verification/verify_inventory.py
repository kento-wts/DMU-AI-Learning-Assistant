"""Verify the provenance inventory against the shipped PDF text.

Reads ``tools/rag_verification/document-inventory.json`` and checks, for every document:

* the file exists and its sha256 still matches
* the page count still matches
* any string recorded as present in the document text is actually present

Run from the repository root:

    python tools/rag_verification/verify_inventory.py

Exit code 0 means every recorded claim still holds. Exit code 1 lists every
mismatch. Read-only: no PDF and no vector store is modified.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pypdf import PdfReader  # noqa: E402

DOCUMENTS_DIR = REPO_ROOT / "backend" / "knowledge" / "documents"
INVENTORY_PATH = Path(__file__).resolve().parent / "document-inventory.json"

# Inventory fields whose value must appear verbatim in the extracted text.
# Fields suffixed _iso or _summary are this verification's own renderings and
# are intentionally excluded.
TEXT_FIELDS = (
    "title_in_text",
    "issuing_body_in_text",
    "document_number_in_text",
    "issue_date_in_text",
    "effective_from_in_text",
    "supersedes_in_text",
)


def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.replace("\r\n", "\n").replace("\r", "\n").strip())
    return unicodedata.normalize("NFKC", "\n\n".join(pages))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    checked = 0
    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line)

    for entry in inventory["documents"]:
        name = entry["file"]
        pdf_path = DOCUMENTS_DIR / name

        if not pdf_path.is_file():
            failures.append(f"{name}: file is missing")
            continue

        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            failures.append(
                f"{name}: sha256 changed\n    inventory: {entry['sha256']}\n    actual:    {digest}"
            )

        reader = PdfReader(str(pdf_path))
        if len(reader.pages) != entry["pages"]:
            failures.append(
                f"{name}: page count changed "
                f"(inventory {entry['pages']}, actual {len(reader.pages)})"
            )

        creation = str((reader.metadata or {}).get("/CreationDate", ""))
        expected_creation = entry.get("pdf_creation_date_in_text")
        if expected_creation is not None and creation != expected_creation:
            failures.append(
                f"{name}: PDF /CreationDate changed "
                f"(inventory {expected_creation!r}, actual {creation!r})"
            )

        text = _extract_text(pdf_path)
        if len(text) != entry["text_chars"]:
            failures.append(
                f"{name}: extracted character count changed "
                f"(inventory {entry['text_chars']}, actual {len(text)})"
            )

        for field in TEXT_FIELDS:
            value = entry.get(field)
            if value is None:
                continue
            if value not in text:
                failures.append(f"{name}: {field} not found in document text: {value!r}")
            else:
                checked += 1
                emit(f"OK  {name} :: {field} = {value}")

        for marker in entry.get("scope_markers") or []:
            if marker not in text:
                failures.append(f"{name}: scope marker not found: {marker!r}")
            else:
                checked += 1
                emit(f"OK  {name} :: scope marker = {marker}")

    emit()
    emit(f"documents checked: {len(inventory['documents'])}   text claims verified: {checked}")

    if failures:
        emit()
        emit(f"FAILURES ({len(failures)}):")
        for failure in failures:
            emit(f"  - {failure}")
    else:
        emit("PASS: every inventory claim matches the shipped documents.")

    reference = Path(__file__).resolve().parent / "reference"
    if reference.is_dir():
        (reference / "inventory-verification.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
