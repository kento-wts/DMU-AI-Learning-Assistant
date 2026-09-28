"""RAG chat service that connects retrieval and prompt building to DeepSeek."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from .knowledge.prompt_builder import build_rag_prompt
from .knowledge.retriever import Retriever

SYSTEM_PROMPT = "你是 DMU AI学习助手。"


class RagChatError(RuntimeError):
    """Raised when the DeepSeek chat service cannot produce an answer."""


class RagChatService:
    """Run retrieval-augmented chat through a DeepSeek-compatible client."""

    def __init__(
        self,
        retriever: Retriever,
        client: OpenAI,
        model: str,
    ) -> None:
        self._retriever = retriever
        self._client = client
        self._model = model

    def chat(
        self,
        query: str,
        top_k: int = 3,
        metadata_filter: dict[str, Any] | None = None,
    ) -> str:
        """Retrieve knowledge chunks, build a RAG prompt, and ask DeepSeek."""
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query must be a non-empty string")

        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 1:
            raise ValueError("top_k must be greater than zero")

        results = self._retriever.retrieve(
            query,
            top_k=top_k,
            metadata_filter=metadata_filter,
        )

        rag_prompt = build_rag_prompt(query, results)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": rag_prompt,
                },
            ],
            stream=False,
        )

        choices = getattr(response, "choices", None)
        if not choices:
            raise RagChatError("DeepSeek returned no completion choices")

        content = getattr(choices[0].message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise RagChatError("DeepSeek returned empty content")

        return content


__all__ = ["RagChatError", "RagChatService", "SYSTEM_PROMPT"]
