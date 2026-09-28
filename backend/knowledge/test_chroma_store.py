"""Tests for the persistent Chroma-backed vector store."""

import tempfile
import unittest
from pathlib import Path

from backend.knowledge.chroma_store import ChromaVectorStore


class ChromaVectorStoreTests(unittest.TestCase):
    def test_add_stores_text_vector_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChromaVectorStore(persist_directory=temp_dir)
            try:
                store.add(
                    "人工智能",
                    [1.0, 0.0],
                    {"year": 2026, "major": "软件工程"},
                )

                results = store.search([1.0, 0.0])

                self.assertEqual(len(store), 1)
                self.assertEqual(results[0].text, "人工智能")
                self.assertEqual(
                    results[0].metadata,
                    {"year": 2026, "major": "软件工程"},
                )
            finally:
                store.close()

    def test_search_returns_top_k_by_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChromaVectorStore(persist_directory=temp_dir)
            try:
                store.add("B", [0.9, 0.1], {"id": "b"})
                store.add("A", [1.0, 0.0], {"id": "a"})
                store.add("C", [0.0, 1.0], {"id": "c"})

                results = store.search([1.0, 0.0], top_k=2)

                self.assertEqual([result.text for result in results], ["A", "B"])
                self.assertGreaterEqual(results[0].score, results[1].score)
            finally:
                store.close()

    def test_metadata_filter_is_passed_to_chroma(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChromaVectorStore(persist_directory=temp_dir)
            try:
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
            finally:
                store.close()

    def test_search_on_empty_store_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChromaVectorStore(persist_directory=temp_dir)
            try:
                self.assertEqual(store.search([1.0, 0.0]), [])
            finally:
                store.close()

    def test_data_persists_across_store_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_path = Path(temp_dir)

            first_store = ChromaVectorStore(
                persist_directory=persist_path,
                collection_name="persist_test",
            )
            first_store.add(
                "persistent",
                [1.0, 0.0],
                {"year": 2026},
            )
            first_store.close()

            second_store = ChromaVectorStore(
                persist_directory=persist_path,
                collection_name="persist_test",
            )
            try:
                results = second_store.search([1.0, 0.0])

                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].text, "persistent")
                self.assertEqual(results[0].metadata, {"year": 2026})
            finally:
                second_store.close()


if __name__ == "__main__":
    unittest.main()
