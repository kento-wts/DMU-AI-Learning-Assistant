"""Tests for RAG prompt construction."""

import unittest

from backend.knowledge.prompt_builder import build_rag_prompt
from backend.knowledge.vector_store import SearchResult


def _result(text: str) -> SearchResult:
    return SearchResult(text=text, score=0.9, metadata={"source": "test"})


class BuildRagPromptTests(unittest.TestCase):
    def test_multiple_chunks_are_included(self) -> None:
        prompt = build_rag_prompt(
            "问题",
            [
                _result("第一段资料"),
                _result("第二段资料"),
                _result("第三段资料"),
            ],
        )

        self.assertIn("[资料 1]\n第一段资料", prompt)
        self.assertIn("[资料 2]\n第二段资料", prompt)
        self.assertIn("[资料 3]\n第三段资料", prompt)

    def test_user_query_is_included(self) -> None:
        prompt = build_rag_prompt(
            "大连海事大学有哪些专业？",
            [_result("资料")],
        )

        self.assertIn("大连海事大学有哪些专业？", prompt)

    def test_chunk_order_is_preserved(self) -> None:
        chunk_texts = ["alpha", "beta", "gamma"]
        prompt = build_rag_prompt(
            "问题",
            [_result(text) for text in chunk_texts],
        )

        positions = [prompt.index(text) for text in chunk_texts]

        self.assertEqual(positions, sorted(positions))

    def test_empty_results_still_produce_valid_prompt(self) -> None:
        prompt = build_rag_prompt("问题", [])

        self.assertIn("【知识库资料】", prompt)
        self.assertIn("当前知识库没有检索到相关资料。", prompt)
        self.assertIn("【用户问题】", prompt)
        self.assertIn("问题", prompt)

    def test_empty_query_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            build_rag_prompt("", [_result("资料")])

    def test_whitespace_query_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            build_rag_prompt("   ", [_result("资料")])

    def test_non_string_query_raises_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "query must be a string"):
            build_rag_prompt(123, [_result("资料")])  # type: ignore[arg-type]

    def test_non_list_results_raise_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "results must be a list"):
            build_rag_prompt("问题", (_result("资料"),))  # type: ignore[arg-type]

    def test_non_search_result_item_raises_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "only SearchResult"):
            build_rag_prompt("问题", ["不是 SearchResult"])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
