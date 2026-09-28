"""Build a DeepSeek-ready RAG prompt from retrieved knowledge chunks."""

from __future__ import annotations

from .vector_store import SearchResult


def build_rag_prompt(
    query: str,
    results: list[SearchResult],
) -> str:
    """Compose a query and retrieved chunks into one RAG prompt.

    Args:
        query: The user's natural-language question.
        results: Retrieved chunks in relevance order. Their order is preserved.

    Returns:
        A complete prompt string for the language model.

    Raises:
        TypeError: ``query`` is not a string, ``results`` is not a list, or an
            item in ``results`` is not a ``SearchResult``.
        ValueError: ``query`` is empty or whitespace-only.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if not query.strip():
        raise ValueError("query must be a non-empty string")

    if not isinstance(results, list):
        raise TypeError("results must be a list")

    for result in results:
        if not isinstance(result, SearchResult):
            raise TypeError("results must contain only SearchResult objects")

    knowledge_block = _build_knowledge_block(results)

    return (
        "请根据以下知识库资料回答用户问题。\n"
        "\n"
        "【知识库资料】\n"
        "\n"
        f"{knowledge_block}\n"
        "\n"
        "【用户问题】\n"
        "\n"
        f"{query}"
    )


def _build_knowledge_block(results: list[SearchResult]) -> str:
    """Return numbered chunk text while preserving the supplied order."""
    if not results:
        return "当前知识库没有检索到相关资料。"

    chunks = [
        f"[资料 {index}]\n{result.text}"
        for index, result in enumerate(results, start=1)
    ]
    return "\n\n".join(chunks)


__all__ = ["build_rag_prompt"]
