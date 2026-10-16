"""Tests for RAG prompt construction."""

import unittest

from backend.knowledge.prompt_builder import build_rag_prompt
from backend.knowledge.vector_store import SearchResult


def _result(text: str) -> SearchResult:
    return SearchResult(text=text, score=0.9, metadata={"source": "test"})


def _bare_result(text: str) -> SearchResult:
    """A result without any provenance metadata."""
    return SearchResult(text=text, score=0.9, metadata={})


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

        self.assertIn("[资料 1]", prompt)
        self.assertIn("第一段资料", prompt)
        self.assertIn("[资料 2]", prompt)
        self.assertIn("第二段资料", prompt)
        self.assertIn("[资料 3]", prompt)
        self.assertIn("第三段资料", prompt)

    def test_chunks_without_metadata_keep_the_bare_header(self) -> None:
        prompt = build_rag_prompt(
            "问题",
            [_bare_result("第一段资料"), _bare_result("第二段资料")],
        )

        self.assertIn("[资料 1]\n第一段资料", prompt)
        self.assertIn("[资料 2]\n第二段资料", prompt)

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


class PromptProvenanceTests(unittest.TestCase):
    """The prompt must let the model see where a chunk came from."""

    def test_source_and_year_are_included_when_present(self) -> None:
        prompt = build_rag_prompt(
            "2026年有哪些竞赛？",
            [
                SearchResult(
                    text="竞赛列表内容",
                    score=0.9,
                    metadata={
                        "source": "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf",
                        "document_type": "竞赛列表",
                        "year": 2026,
                        "document_id": "dlmu-competition-list-2026",
                        "chunk_index": 3,
                        "chunk_hash": "a" * 64,
                    },
                )
            ],
        )

        self.assertIn(
            "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf", prompt
        )
        self.assertIn("来源文件", prompt)
        self.assertIn("适用年份: 2026", prompt)
        self.assertIn("文档类型: 竞赛列表", prompt)
        self.assertIn("文档标识: dlmu-competition-list-2026", prompt)

    def test_internal_bookkeeping_fields_are_not_included(self) -> None:
        prompt = build_rag_prompt(
            "问题",
            [
                SearchResult(
                    text="内容",
                    score=0.9,
                    metadata={
                        "source": "a.pdf",
                        "chunk_index": 7,
                        "chunk_hash": "b" * 64,
                    },
                )
            ],
        )

        self.assertNotIn("chunk_index", prompt)
        self.assertNotIn("chunk_hash", prompt)
        self.assertNotIn("b" * 64, prompt)

    def test_empty_and_missing_provenance_values_are_omitted(self) -> None:
        prompt = build_rag_prompt(
            "问题",
            [
                SearchResult(
                    text="内容",
                    score=0.9,
                    metadata={"source": "   ", "year": None, "document_type": ""},
                )
            ],
        )

        self.assertIn("[资料 1]\n内容", prompt)
        # The bare chunk header proves no provenance label was emitted; the
        # instruction text itself legitimately mentions 来源.
        self.assertNotIn("来源文件:", prompt)
        self.assertNotIn("适用年份:", prompt)
        self.assertNotIn("文档类型:", prompt)

    def test_two_documents_stay_distinguishable_in_one_prompt(self) -> None:
        prompt = build_rag_prompt(
            "问题",
            [
                SearchResult(
                    text="2025 版本内容",
                    score=0.9,
                    metadata={"source": "列表(2025年).pdf", "year": 2025},
                ),
                SearchResult(
                    text="2026 版本内容",
                    score=0.8,
                    metadata={"source": "列表(2026年).pdf", "year": 2026},
                ),
            ],
        )

        self.assertLess(prompt.index("列表(2025年).pdf"), prompt.index("列表(2026年).pdf"))
        self.assertIn("适用年份: 2025", prompt)
        self.assertIn("适用年份: 2026", prompt)

    def test_prompt_forbids_fabricating_when_no_material_matches(self) -> None:
        prompt = build_rag_prompt("问题", [])

        self.assertIn("当前知识库没有检索到相关资料。", prompt)


if __name__ == "__main__":
    unittest.main()
