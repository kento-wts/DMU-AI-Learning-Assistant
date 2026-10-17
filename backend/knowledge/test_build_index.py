"""Guards for the index-building entry point.

``build_index.py`` decides which PDFs become which documents. If its table
drifts from the shipped files or from the recorded document ids, retrieval
silently starts filtering on ids that no longer exist. These tests catch that
without embedding anything.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from .build_index import DOCUMENT_METADATA, DEFAULT_DOCUMENTS_DIR, build_parser

INVENTORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "rag_verification"
    / "document-inventory.json"
)


class BuildIndexTableTests(unittest.TestCase):
    """Keep the document table, the folder and the inventory in step."""

    def test_every_shipped_pdf_is_covered(self) -> None:
        on_disk = {path.name for path in DEFAULT_DOCUMENTS_DIR.glob("*.pdf")}
        self.assertTrue(on_disk, "no PDFs found; is the documents folder present?")
        self.assertEqual(
            on_disk - set(DOCUMENT_METADATA),
            set(),
            "PDFs on disk are missing from DOCUMENT_METADATA, so they would never "
            "be imported",
        )

    def test_every_table_entry_has_a_file(self) -> None:
        missing = [
            name
            for name in DOCUMENT_METADATA
            if not (DEFAULT_DOCUMENTS_DIR / name).is_file()
        ]
        self.assertEqual(missing, [], f"DOCUMENT_METADATA names files that do not exist: {missing}")

    def test_document_ids_are_unique_and_stable_looking(self) -> None:
        ids = [metadata["document_id"] for metadata in DOCUMENT_METADATA.values()]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate document_id: {ids}")
        for document_id in ids:
            with self.subTest(document_id=document_id):
                self.assertTrue(document_id.startswith("dlmu-"))
                self.assertNotIn("\\", document_id)
                self.assertNotIn("/", document_id)

    def test_every_entry_carries_the_retrieval_facets(self) -> None:
        for name, metadata in DOCUMENT_METADATA.items():
            with self.subTest(file=name):
                self.assertIsInstance(metadata.get("year"), int)
                self.assertTrue(str(metadata.get("major", "")).strip())
                self.assertTrue(str(metadata.get("document_type", "")).strip())

    def test_document_ids_match_the_provenance_inventory(self) -> None:
        if not INVENTORY_PATH.is_file():
            self.skipTest("provenance inventory is not present in this checkout")

        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        recorded = {doc["document_id"]: doc["file"] for doc in inventory["documents"]}
        table = {
            metadata["document_id"]: name
            for name, metadata in DOCUMENT_METADATA.items()
        }

        self.assertEqual(set(table), set(recorded), "document ids differ between the table and the inventory")
        for document_id, name in table.items():
            with self.subTest(document_id=document_id):
                self.assertEqual(name, recorded[document_id])

    def test_defaults_point_at_the_shipped_locations(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.documents_dir, DEFAULT_DOCUMENTS_DIR)
        self.assertTrue(str(args.persist_directory).replace("\\", "/").endswith("data/chroma"))
        self.assertFalse(args.dry_run)


if __name__ == "__main__":
    unittest.main()
