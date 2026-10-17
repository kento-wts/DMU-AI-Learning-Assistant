"""Guards for the curated evaluation question set.

These tests do not run retrieval. They keep ``evaluation_dataset.json``
self-consistent so a silent edit cannot leave the set with duplicate ids,
an answerable question without an expected document, or a negative question
pointing at a document that does not exist.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

DATASET_PATH = Path(__file__).with_name("evaluation_dataset.json")
INVENTORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "rag_verification"
    / "document-inventory.json"
)

ANSWERABLE = "answerable"
NOT_IN_CORPUS = "not_in_corpus"
KNOWN_BEHAVIOURS = {
    ANSWERABLE,
    NOT_IN_CORPUS,
    "scope_mismatch",
    "not_reliably_answerable_from_text",
}


def _load_dataset() -> list[dict]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


class EvaluationDatasetTests(unittest.TestCase):
    """Keep the curated question set usable by the verification tools."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = _load_dataset()

    def test_dataset_is_a_non_empty_list(self) -> None:
        self.assertIsInstance(self.dataset, list)
        self.assertGreater(len(self.dataset), 1)

    def test_ids_are_unique_and_non_empty(self) -> None:
        ids = [entry.get("id") for entry in self.dataset]
        self.assertTrue(all(isinstance(value, str) and value for value in ids))
        self.assertEqual(len(ids), len(set(ids)), f"duplicate ids: {ids}")

    def test_every_entry_has_a_question_and_notes(self) -> None:
        for entry in self.dataset:
            with self.subTest(entry=entry.get("id")):
                self.assertTrue(entry.get("question", "").strip())
                self.assertIsInstance(entry.get("notes"), str)

    def test_legacy_entry_keeps_its_original_shape(self) -> None:
        """q1 predates the extended schema and must stay usable as-is."""
        entry = next(item for item in self.dataset if item["id"] == "q1")
        self.assertIn("relevant_competitions", entry)
        self.assertNotIn("expected_behaviour", entry)

    def test_answerable_entries_declare_documents_and_ground_truth(self) -> None:
        answerable = [e for e in self.dataset if e.get("expected_behaviour") == ANSWERABLE]
        self.assertGreaterEqual(len(answerable), 10)
        for entry in answerable:
            with self.subTest(entry=entry["id"]):
                self.assertTrue(entry.get("expected_document_ids"))
                self.assertTrue(entry.get("ground_truth_points"))

    def test_negative_entries_expect_no_document(self) -> None:
        negatives = [e for e in self.dataset if e.get("expected_behaviour") == NOT_IN_CORPUS]
        self.assertGreaterEqual(len(negatives), 3)
        for entry in negatives:
            with self.subTest(entry=entry["id"]):
                self.assertEqual(entry.get("expected_document_ids"), [])
                self.assertEqual(entry.get("ground_truth_points"), [])

    def test_behaviour_values_are_known(self) -> None:
        for entry in self.dataset:
            behaviour = entry.get("expected_behaviour")
            if behaviour is None:
                continue
            with self.subTest(entry=entry["id"]):
                self.assertIn(behaviour, KNOWN_BEHAVIOURS)

    def test_expected_documents_exist_in_the_provenance_inventory(self) -> None:
        if not INVENTORY_PATH.is_file():
            self.skipTest("provenance inventory is not present in this checkout")

        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        known = {doc["document_id"] for doc in inventory["documents"]}

        for entry in self.dataset:
            for document_id in entry.get("expected_document_ids") or []:
                with self.subTest(entry=entry["id"], document_id=document_id):
                    self.assertIn(document_id, known)


def _category(entry: dict) -> str | None:
    """Map one entry to the review categories used by the quality report."""
    behaviour = entry.get("expected_behaviour")
    if behaviour == "not_in_corpus":
        return "corpus_missing"
    if behaviour == "scope_mismatch":
        return "scope_mismatch"
    if behaviour == "not_reliably_answerable_from_text":
        return "partial"
    if behaviour == "answerable":
        return "partial" if entry.get("completeness") == "partial" else "full"
    return None


class DatasetCategoryTests(unittest.TestCase):
    """The four review categories must stay distinguishable in the data."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = _load_dataset()

    def test_all_four_categories_are_represented(self) -> None:
        categories = {_category(entry) for entry in self.dataset}

        self.assertTrue(
            {"full", "partial", "corpus_missing", "scope_mismatch"} <= categories,
            f"missing categories, got {categories}",
        )

    def test_partial_entries_stay_answerable_with_ground_truth(self) -> None:
        partial = [entry for entry in self.dataset if entry.get("completeness") == "partial"]

        self.assertTrue(partial, "at least one partially answerable question is expected")
        for entry in partial:
            with self.subTest(entry=entry["id"]):
                self.assertEqual(entry.get("expected_behaviour"), "answerable")
                self.assertTrue(entry.get("expected_document_ids"))
                self.assertTrue(entry.get("ground_truth_points"))

    def test_completeness_values_are_known(self) -> None:
        for entry in self.dataset:
            value = entry.get("completeness")
            if value is None:
                continue
            with self.subTest(entry=entry["id"]):
                self.assertIn(value, {"full", "partial"})

    def test_corpus_gaps_carry_no_completeness(self) -> None:
        for entry in self.dataset:
            if entry.get("expected_behaviour") != "not_in_corpus":
                continue
            with self.subTest(entry=entry["id"]):
                self.assertNotIn("completeness", entry)


if __name__ == "__main__":
    unittest.main()
