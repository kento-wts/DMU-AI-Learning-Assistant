"""Chinese text embedding for the knowledge base.

The module keeps the embedding model lazy so importing ``backend.knowledge``
stays cheap. The default model is a small multilingual BGE model optimised
for Chinese text and runs locally without an API key.
"""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Sequence
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_MODEL_ENV = "EMBEDDING_MODEL"
EMBEDDING_CACHE_DIR_ENV = "EMBEDDING_CACHE_DIR"

_model: Any | None = None
_model_lock = threading.Lock()


class EmbeddingError(RuntimeError):
    """Raised when the embedding model cannot be loaded or used."""


def embed_text(text: str) -> list[float]:
    """Convert one text into a floating-point embedding vector.

    Args:
        text: Source text. Whitespace-only input is treated as empty.

    Returns:
        A non-empty list of floats for non-empty text, or an empty list for
        whitespace-only text.

    Raises:
        TypeError: ``text`` is not a string.
        EmbeddingError: The model cannot be loaded or fails to produce a vector.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    normalized_text = text.strip()
    if not normalized_text:
        return []

    model = _get_model()
    try:
        vectors = list(model.embed([normalized_text]))
    except Exception as exc:
        raise EmbeddingError(
            f"Unable to embed text with model {_configured_model_name()}"
        ) from exc

    if not vectors:
        raise EmbeddingError("Embedding model returned no vector for non-empty text")

    return _vector_to_floats(vectors[0])


def cosine_similarity(vector_a: Sequence[float], vector_b: Sequence[float]) -> float:
    """Return the cosine similarity between two equal-length vectors."""
    if not vector_a or not vector_b:
        raise ValueError("vectors must not be empty")
    if len(vector_a) != len(vector_b):
        raise ValueError("vectors must have the same length")

    dot_product = sum(float(a) * float(b) for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(float(value) ** 2 for value in vector_a))
    norm_b = math.sqrt(sum(float(value) ** 2 for value in vector_b))

    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("vectors must not be zero-length")

    return dot_product / (norm_a * norm_b)


def _configured_model_name() -> str:
    configured_name = os.getenv(EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL).strip()
    return configured_name or DEFAULT_EMBEDDING_MODEL


def _get_model() -> Any:
    """Load and cache the local embedding model."""
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise EmbeddingError(
                    "fastembed is required for local embeddings"
                ) from exc

            model_name = _configured_model_name()
            cache_dir = os.getenv(EMBEDDING_CACHE_DIR_ENV)
            model_kwargs: dict[str, str] = {"model_name": model_name}
            if cache_dir:
                model_kwargs["cache_dir"] = cache_dir.strip()

            try:
                _model = TextEmbedding(**model_kwargs)
            except Exception as exc:
                raise EmbeddingError(
                    f"Unable to load embedding model: {model_name}"
                ) from exc

    return _model


def _vector_to_floats(vector: Sequence[float]) -> list[float]:
    """Normalise a NumPy array or list into plain Python floats."""
    return [float(value) for value in vector]


__all__ = ["DEFAULT_EMBEDDING_MODEL", "EmbeddingError", "cosine_similarity", "embed_text"]
