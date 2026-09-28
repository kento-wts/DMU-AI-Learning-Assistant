"""Tests for the RAG-enabled FastAPI chat endpoint."""

import asyncio
import os
import unittest
from typing import Any
from unittest.mock import patch

os.environ["DEEPSEEK_API_KEY"] = "test-key"

from fastapi import HTTPException

from backend import main
from backend.knowledge.vector_store import SearchResult


class FakeRetriever:
    """Records retrieve calls and returns fixed search results."""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = list(results)
        self.retrieve_calls: list[dict[str, Any]] = []

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        self.retrieve_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "metadata_filter": metadata_filter,
            }
        )
        return list(self.results)


class FakeDelta:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.delta = FakeDelta(content)


class FakeChunk:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(
        self,
        chunks: list[FakeChunk],
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks
        self.error = error
        self.last_request: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.last_request = kwargs

        if self.error is not None:
            raise self.error

        return iter(self.chunks)


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeClient:
    def __init__(
        self,
        chunks: list[FakeChunk],
        error: Exception | None = None,
    ) -> None:
        self.chat = FakeChat(FakeCompletions(chunks, error))


def _consume(response: Any) -> list[str]:
    async def collect() -> list[str]:
        return [chunk async for chunk in response.body_iterator]

    return asyncio.run(collect())


def _messages(*roles_and_contents: tuple[str, str]) -> list[main.Message]:
    return [
        main.Message(role=role, content=content)
        for role, content in roles_and_contents
    ]


class MainChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = [
            SearchResult(text="资料一", score=0.9, metadata={}),
            SearchResult(text="资料二", score=0.8, metadata={}),
        ]
        self.retriever = FakeRetriever(self.results)

    def test_latest_user_message_is_used_for_retrieval(self) -> None:
        client = FakeClient([FakeChunk("回答")])
        request = main.ChatRequest(
            messages=_messages(
                ("user", "第一个问题"),
                ("ai", "第一个回答"),
                ("user", "最新问题"),
            )
        )

        with (
            patch.object(main, "_get_retriever", return_value=self.retriever),
            patch.object(main, "client", client),
            patch(
                "backend.main.build_rag_prompt",
                return_value="RAG_PROMPT",
            ) as prompt_mock,
        ):
            _consume(main.chat(request))

        self.assertEqual(
            self.retriever.retrieve_calls[0]["query"],
            "最新问题",
        )
        self.assertEqual(self.retriever.retrieve_calls[0]["top_k"], 3)
        prompt_mock.assert_called_once_with("最新问题", self.results)

    def test_no_user_message_returns_clear_error(self) -> None:
        request = main.ChatRequest(
            messages=_messages(("ai", "只有助手消息")),
        )

        with patch.object(main, "_get_retriever") as retriever_mock:
            with self.assertRaisesRegex(HTTPException, "没有 user 消息"):
                main.chat(request)

        retriever_mock.assert_not_called()

    def test_rag_context_is_added_to_system_message(self) -> None:
        client = FakeClient([FakeChunk("回答")])
        request = main.ChatRequest(messages=_messages(("user", "问题")))

        with (
            patch.object(main, "_get_retriever", return_value=self.retriever),
            patch.object(main, "client", client),
            patch(
                "backend.main.build_rag_prompt",
                return_value="RAG_PROMPT",
            ),
        ):
            _consume(main.chat(request))

        system_message = client.chat.completions.last_request["messages"][0]

        self.assertEqual(system_message["role"], "system")
        self.assertIn(main.BASE_SYSTEM_PROMPT, system_message["content"])
        self.assertIn("RAG_PROMPT", system_message["content"])
        self.assertIn(main.RAG_CONTEXT_NOTE, system_message["content"])

    def test_original_history_is_kept_and_ai_becomes_assistant(self) -> None:
        client = FakeClient([FakeChunk("回答")])
        request = main.ChatRequest(
            messages=_messages(
                ("user", "第一问"),
                ("ai", "第一答"),
                ("user", "第二问"),
            )
        )

        with (
            patch.object(main, "_get_retriever", return_value=self.retriever),
            patch.object(main, "client", client),
            patch(
                "backend.main.build_rag_prompt",
                return_value="RAG_PROMPT",
            ),
        ):
            _consume(main.chat(request))

        sent_messages = client.chat.completions.last_request["messages"]

        self.assertEqual(
            sent_messages[1:],
            [
                {"role": "user", "content": "第一问"},
                {"role": "assistant", "content": "第一答"},
                {"role": "user", "content": "第二问"},
            ],
        )

    def test_deepseek_uses_stream_mode(self) -> None:
        client = FakeClient([FakeChunk("回答")])
        request = main.ChatRequest(messages=_messages(("user", "问题")))

        with (
            patch.object(main, "_get_retriever", return_value=self.retriever),
            patch.object(main, "client", client),
            patch(
                "backend.main.build_rag_prompt",
                return_value="RAG_PROMPT",
            ),
        ):
            _consume(main.chat(request))

        self.assertIs(
            client.chat.completions.last_request["stream"],
            True,
        )
        self.assertEqual(
            client.chat.completions.last_request["model"],
            "deepseek-v4-flash",
        )

    def test_sse_format_is_preserved(self) -> None:
        client = FakeClient([FakeChunk("你好")])
        request = main.ChatRequest(messages=_messages(("user", "问题")))

        with (
            patch.object(main, "_get_retriever", return_value=self.retriever),
            patch.object(main, "client", client),
            patch(
                "backend.main.build_rag_prompt",
                return_value="RAG_PROMPT",
            ),
        ):
            events = _consume(main.chat(request))

        self.assertEqual(
            events,
            [
                'data: {"content": "你好"}\n\n',
                "data: [DONE]\n\n",
            ],
        )

    def test_deepseek_error_is_returned_as_sse(self) -> None:
        client = FakeClient([], error=RuntimeError("接口故障"))
        request = main.ChatRequest(messages=_messages(("user", "问题")))

        with (
            patch.object(main, "_get_retriever", return_value=self.retriever),
            patch.object(main, "client", client),
            patch(
                "backend.main.build_rag_prompt",
                return_value="RAG_PROMPT",
            ),
        ):
            events = _consume(main.chat(request))

        self.assertEqual(
            events,
            [
                'data: {"error": "DeepSeek API 调用失败: 接口故障"}\n\n',
            ],
        )


if __name__ == "__main__":
    unittest.main()
