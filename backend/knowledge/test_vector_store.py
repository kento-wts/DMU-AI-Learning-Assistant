"""Tests for the in-memory vector store."""

import unittest

from backend.knowledge.vector_store import SearchResult, VectorStore


class VectorStoreTests(unittest.TestCase):
    def test_add_stores_text_vector_and_metadata(self) -> None:
        store = VectorStore()

        store.add("人工智能", [1.0, 0.0], {"year": 2026, "major": "软件工程"})

        self.assertEqual(len(store), 1)
        result = store.search([1.0, 0.0])[0]
        self.assertEqual(result.text, "人工智能")
        self.assertEqual(result.metadata, {"year": 2026, "major": "软件工程"})

    def test_search_returns_top_k_by_similarity(self) -> None:
        store = VectorStore()
        store.add("B", [0.9, 0.1], {"id": "b"})
        store.add("A", [1.0, 0.0], {"id": "a"})
        store.add("C", [0.0, 1.0], {"id": "c"})

        results = store.search([1.0, 0.0], top_k=2)

        self.assertEqual([result.text for result in results], ["A", "B"])

    def test_search_scores_are_sorted_from_high_to_low(self) -> None:
        store = VectorStore()
        store.add("least", [0.1, 1.0], {"id": "least"})
        store.add("best", [1.0, 0.0], {"id": "best"})
        store.add("middle", [0.7, 0.7], {"id": "middle"})

        results = store.search([1.0, 0.0], top_k=3)

        self.assertEqual([result.text for result in results], ["best", "middle", "least"])
        self.assertGreaterEqual(results[0].score, results[1].score)
        self.assertGreaterEqual(results[1].score, results[2].score)

    def test_search_filters_metadata_before_scoring(self) -> None:
        store = VectorStore()
        store.add(
            "target",
            [1.0, 0.0],
            {"year": 2026, "major": "软件工程"},
        )
        store.add(
            "wrong-year",
            [0.9, 0.1],
            {"year": 2025, "major": "软件工程"},
        )
        store.add(
            "wrong-major",
            [0.8, 0.2],
            {"year": 2026, "major": "航海技术"},
        )

        results = store.search(
            [1.0, 0.0],
            top_k=10,
            metadata_filter={"year": 2026, "major": "软件工程"},
        )

        self.assertEqual([result.text for result in results], ["target"])

    def test_mismatched_vector_dimensions_are_rejected(self) -> None:
        store = VectorStore()
        store.add("first", [1.0, 0.0], {})

        with self.assertRaisesRegex(ValueError, "dimension"):
            store.add("second", [1.0, 0.0, 0.0], {})

    def test_empty_vector_is_rejected(self) -> None:
        store = VectorStore()

        with self.assertRaisesRegex(ValueError, "empty"):
            store.add("empty", [], {})

    def test_zero_length_vector_is_rejected(self) -> None:
        store = VectorStore()

        with self.assertRaisesRegex(ValueError, "zero-length"):
            store.add("zero", [0.0, 0.0], {})

    def test_invalid_top_k_is_rejected(self) -> None:
        store = VectorStore()
        store.add("first", [1.0, 0.0], {})

        for top_k in (0, -1):
            with self.subTest(top_k=top_k):
                with self.assertRaisesRegex(ValueError, "top_k"):
                    store.search([1.0, 0.0], top_k=top_k)

    def test_search_on_empty_store_returns_empty_list(self) -> None:
        store = VectorStore()

        self.assertEqual(store.search([1.0, 0.0]), [])

    def test_query_vector_dimension_mismatch_is_rejected(self) -> None:
        store = VectorStore()
        store.add("first", [1.0, 0.0], {})

        with self.assertRaisesRegex(ValueError, "dimension"):
            store.search([1.0, 0.0, 0.0])

    def test_search_result_is_a_typed_result(self) -> None:
        store = VectorStore()
        store.add("first", [1.0, 0.0], {"year": 2026})

        result = store.search([1.0, 0.0])[0]

        self.assertIsInstance(result, SearchResult)


if __name__ == "__main__":
    unittest.main()
