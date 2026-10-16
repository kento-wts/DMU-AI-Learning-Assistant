"""Build a DeepSeek-ready RAG prompt from retrieved knowledge chunks.

Every retrieved chunk carries the metadata that documents its provenance
(``source`` file name, ``year``, ``document_type``, ``document_id``). The
prompt includes the fields that are present so the model can tell a 2026
notice from a 2025 one and can name the document it relied on. Missing or
empty metadata is simply omitted, so callers that pass bare ``SearchResult``
objects keep the previous prompt shape.
"""

from __future__ import annotations

from typing import Any

from .vector_store import SearchResult

# Metadata keys copied into the prompt, in this order. ``chunk_index`` and
# ``chunk_hash`` are internal bookkeeping and are intentionally left out.
PROVENANCE_KEYS: tuple[tuple[str, str], ...] = (
    ("source", "来源文件"),
    ("document_type", "文档类型"),
    ("year", "适用年份"),
    ("document_id", "文档标识"),
)


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
        "回答时请说明资料出处，并注意资料的适用年份与适用范围；"
        "如果资料中没有答案，请明确说明知识库中没有相关内容，不要编造。\n"
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
    """Return numbered chunk text with any available provenance."""
    if not results:
        return "当前知识库没有检索到相关资料。"

    blocks = []
    for index, result in enumerate(results, start=1):
        provenance = _format_provenance(result.metadata)
        header = f"[资料 {index}]"
        if provenance:
            header = f"{header} {provenance}"
        blocks.append(f"{header}\n{result.text}")

    return "\n\n".join(blocks)


def _format_provenance(metadata: dict[str, Any]) -> str:
    """Render the known provenance fields as one bracketed label."""
    if not isinstance(metadata, dict):
        return ""

    parts = []
    for key, label in PROVENANCE_KEYS:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        parts.append(f"{label}: {text}")

    if not parts:
        return ""

    return "(" + "；".join(parts) + ")"


__all__ = ["PROVENANCE_KEYS", "build_rag_prompt"]
