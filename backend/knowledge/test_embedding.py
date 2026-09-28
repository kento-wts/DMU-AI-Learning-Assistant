"""Tests for the local Chinese text embedding module."""

import unittest
from unittest.mock import patch

from backend.knowledge.embedding import (
    EmbeddingError,
    cosine_similarity,
    embed_text,
)


class FakeEmbeddingModel:
    """Small deterministic model used for interface-focused tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class EmbedTextTests(unittest.TestCase):
    def test_empty_text_returns_empty_vector(self) -> None:
        self.assertEqual(embed_text("  \n\t "), [])

    def test_non_string_raises_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            embed_text(123)  # type: ignore[arg-type]

    def test_normal_text_returns_list_of_floats(self) -> None:
        with patch(
            "backend.knowledge.embedding._get_model",
            return_value=FakeEmbeddingModel(),
        ):
            vector = embed_text("人工智能")

        self.assertIsInstance(vector, list)
        self.assertTrue(vector)
        self.assertTrue(all(isinstance(value, float) for value in vector))

    def test_model_failure_is_wrapped(self) -> None:
        class FailingModel:
            def embed(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("model unavailable")

        with patch(
            "backend.knowledge.embedding._get_model",
            return_value=FailingModel(),
        ):
            with self.assertRaisesRegex(EmbeddingError, "Unable to embed text"):
                embed_text("人工智能")


class CosineSimilarityTests(unittest.TestCase):
    def test_identical_vectors_have_similarity_one(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]),
            1.0,
        )

    def test_orthogonal_vectors_have_similarity_zero(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 0.0], [0.0, 1.0]),
            0.0,
        )

    def test_mismatched_lengths_raise_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "same length"):
            cosine_similarity([1.0, 2.0], [1.0])


class ChineseSemanticSimilarityTests(unittest.TestCase):
    def test_similar_sentences_are_closer_than_unrelated_sentences(self) -> None:
        maritime_sentence_a = "大连海事大学是一所以航运为特色的高校。"
        maritime_sentence_b = "大连海事大学以航海类专业闻名。"
        unrelated_sentence = "今天中午我想吃宫保鸡丁。"

        vector_a = embed_text(maritime_sentence_a)
        vector_b = embed_text(maritime_sentence_b)
        vector_unrelated = embed_text(unrelated_sentence)

        similar_score = cosine_similarity(vector_a, vector_b)
        unrelated_score = cosine_similarity(vector_a, vector_unrelated)

        self.assertGreater(similar_score, unrelated_score)


if __name__ == "__main__":
    unittest.main()
