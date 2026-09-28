"""Tests for the backend RAG chat service."""

import unittest
from typing import Any
from unittest.mock import patch

from backend.knowledge.vector_store import SearchResult
from backend.rag_chat import RagChatError, RagChatService, SYSTEM_PROMPT


class FakeRetriever:
    """Records retrieve calls and returns pre-built search results."""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = list(results)
        self.last_call: dict[str, Any] | None = None

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        self.last_call = {
            "query": query,
            "top_k": top_k,
            "metadata_filter": metadata_filter,
        }
        return list(self.results)


class FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content: str | None) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.last_request: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> FakeCompletion:
        self.last_request = kwargs
        return FakeCompletion(self.content)


class FakeChat:
    def __init__(self, content: str | None) -> None:
        self.completions = FakeCompletions(content)


class FakeClient:
    def __init__(self, content: str | None) -> None:
        self.chat = FakeChat(content)


def _result(text: str) -> SearchResult:
    return SearchResult(text=text, score=0.9, metadata={"source": "test"})


class RagChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = [_result("第一段资料"), _result("第二段资料")]
        self.retriever = FakeRetriever(self.results)

    def _service(self, content: str | None, model: str = "deepseek-test") -> RagChatService:
        return RagChatService(
            retriever=self.retriever,  # type: ignore[arg-type]
            client=FakeClient(content),  # type: ignore[arg-type]
            model=model,
        )

    def test_retriever_is_called_correctly(self) -> None:
        service = self._service("答案")

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="rag prompt",
        ):
            service.chat(
                "什么是人工智能",
                top_k=2,
                metadata_filter={"major": "软件工程"},
            )

        self.assertEqual(
            self.retriever.last_call,
            {
                "query": "什么是人工智能",
                "top_k": 2,
                "metadata_filter": {"major": "软件工程"},
            },
        )

    def test_prompt_builder_is_called_with_query_and_results(self) -> None:
        service = self._service("答案")

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="rag prompt",
        ) as prompt_mock:
            service.chat("什么是人工智能", top_k=2)

        prompt_mock.assert_called_once_with("什么是人工智能", self.results)

    def test_deepseek_receives_system_and_user_messages(self) -> None:
        client = FakeClient("答案")
        service = RagChatService(
            retriever=self.retriever,  # type: ignore[arg-type]
            client=client,  # type: ignore[arg-type]
            model="deepseek-test",
        )

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="构建好的 RAG Prompt",
        ):
            service.chat("问题")

        self.assertEqual(
            client.chat.completions.last_request["messages"],
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "构建好的 RAG Prompt"},
            ],
        )
        self.assertIs(client.chat.completions.last_request["stream"], False)

    def test_model_parameter_is_used(self) -> None:
        client = FakeClient("答案")
        service = RagChatService(
            retriever=self.retriever,  # type: ignore[arg-type]
            client=client,  # type: ignore[arg-type]
            model="deepseek-v4-pro",
        )

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="rag prompt",
        ):
            service.chat("问题")

        self.assertEqual(
            client.chat.completions.last_request["model"],
            "deepseek-v4-pro",
        )

    def test_deepseek_content_is_returned(self) -> None:
        service = self._service("  最终回答  ")

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="rag prompt",
        ):
            answer = service.chat("问题")

        self.assertEqual(answer, "  最终回答  ")

    def test_empty_deepseek_content_raises_error(self) -> None:
        service = self._service("   ")

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="rag prompt",
        ):
            with self.assertRaisesRegex(RagChatError, "empty content"):
                service.chat("问题")

    def test_none_deepseek_content_raises_error(self) -> None:
        service = self._service(None)

        with patch(
            "backend.rag_chat.build_rag_prompt",
            return_value="rag prompt",
        ):
            with self.assertRaisesRegex(RagChatError, "empty content"):
                service.chat("问题")

    def test_empty_query_raises_value_error(self) -> None:
        service = self._service("答案")

        with self.assertRaisesRegex(ValueError, "non-empty"):
            service.chat("   ")

    def test_non_string_query_raises_type_error(self) -> None:
        service = self._service("答案")

        with self.assertRaisesRegex(TypeError, "query must be a string"):
            service.chat(123)  # type: ignore[arg-type]

    def test_top_k_zero_or_negative_raises_value_error(self) -> None:
        service = self._service("答案")

        for top_k in (0, -1):
            with self.subTest(top_k=top_k):
                with self.assertRaisesRegex(ValueError, "greater than zero"):
                    service.chat("问题", top_k=top_k)

    def test_non_integer_top_k_raises_type_error(self) -> None:
        service = self._service("答案")

        with self.assertRaisesRegex(TypeError, "top_k must be an integer"):
            service.chat("问题", top_k="3")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
