"""Tests for the natural-language retrieval orchestrator."""

import unittest
from typing import Any
from unittest.mock import patch

from backend.knowledge.retriever import DEFAULT_TOP_K, Retriever
from backend.knowledge.vector_store import SearchResult


class FakeStore:
    """Stores search arguments and returns pre-built search results."""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = list(results)
        self.last_query_vector: list[float] | None = None
        self.last_top_k: int | None = None
        self.last_metadata_filter: dict[str, Any] | None = None

    def search(
        self,
        query_vector: list[float],
        top_k: int = DEFAULT_TOP_K,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        self.last_query_vector = query_vector
        self.last_top_k = top_k
        self.last_metadata_filter = metadata_filter

        if metadata_filter:
            filtered = [
                result
                for result in self.results
                if all(
                    result.metadata.get(key) == value
                    for key, value in metadata_filter.items()
                )
            ]
        else:
            filtered = list(self.results)

        return filtered[:top_k]


def _result(text: str, metadata: dict[str, Any]) -> SearchResult:
    return SearchResult(text=text, score=1.0, metadata=metadata)


class RetrieverTests(unittest.TestCase):
    def test_retrieve_returns_search_results(self) -> None:
        expected = _result("人工智能", {"major": "软件工程"})
        retriever = Retriever(FakeStore([expected]))

        with patch(
            "backend.knowledge.retriever.embed_text",
            return_value=[0.1, 0.2, 0.3],
        ):
            results = retriever.retrieve("什么是人工智能")

        self.assertEqual(results, [expected])
        self.assertIsInstance(results[0], SearchResult)

    def test_top_k_limits_result_count(self) -> None:
        store = FakeStore(
            [
                _result("first", {"id": 1}),
                _result("second", {"id": 2}),
                _result("third", {"id": 3}),
            ]
        )
        retriever = Retriever(store)

        with patch(
            "backend.knowledge.retriever.embed_text",
            return_value=[0.1, 0.2, 0.3],
        ):
            results = retriever.retrieve("query", top_k=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(store.last_top_k, 2)

    def test_metadata_filter_is_passed_and_applied(self) -> None:
        store = FakeStore(
            [
                _result("target", {"year": 2026, "major": "软件工程"}),
                _result("wrong-year", {"year": 2025, "major": "软件工程"}),
                _result("wrong-major", {"year": 2026, "major": "航海技术"}),
            ]
        )
        retriever = Retriever(store)
        metadata_filter = {"year": 2026, "major": "软件工程"}

        with patch(
            "backend.knowledge.retriever.embed_text",
            return_value=[0.1, 0.2, 0.3],
        ):
            results = retriever.retrieve(
                "query",
                metadata_filter=metadata_filter,
            )

        self.assertEqual([result.text for result in results], ["target"])
        self.assertEqual(store.last_metadata_filter, metadata_filter)

    def test_empty_query_raises_value_error(self) -> None:
        retriever = Retriever(FakeStore([]))

        with patch("backend.knowledge.retriever.embed_text") as embed_mock:
            with self.assertRaisesRegex(ValueError, "non-empty"):
                retriever.retrieve("   ")

        embed_mock.assert_not_called()

    def test_top_k_zero_or_negative_raises_value_error(self) -> None:
        retriever = Retriever(FakeStore([]))

        for top_k in (0, -1):
            with self.subTest(top_k=top_k):
                with patch(
                    "backend.knowledge.retriever.embed_text"
                ) as embed_mock:
                    with self.assertRaisesRegex(ValueError, "greater than zero"):
                        retriever.retrieve("query", top_k=top_k)

                embed_mock.assert_not_called()

    def test_embedding_function_is_called_with_query(self) -> None:
        retriever = Retriever(FakeStore([_result("first", {})]))

        with patch(
            "backend.knowledge.retriever.embed_text",
            return_value=[0.1, 0.2, 0.3],
        ) as embed_mock:
            retriever.retrieve("什么是人工智能", top_k=1)

        embed_mock.assert_called_once_with("什么是人工智能")

    def test_non_string_query_raises_type_error(self) -> None:
        retriever = Retriever(FakeStore([]))

        with self.assertRaisesRegex(TypeError, "query must be a string"):
            retriever.retrieve(123)  # type: ignore[arg-type]

    def test_invalid_metadata_filter_raises_type_error(self) -> None:
        retriever = Retriever(FakeStore([]))

        with self.assertRaisesRegex(TypeError, "metadata_filter must be a dictionary"):
            retriever.retrieve("query", metadata_filter="year")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
