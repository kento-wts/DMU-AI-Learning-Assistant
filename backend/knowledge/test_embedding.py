"""Tests for the local Chinese text embedding module."""

import unittest
from unittest.mock import patch

from backend.knowledge.embedding import (
    EmbeddingError,
    cosine_similarity,
    embed_text,
    normalize_for_embedding,
)


class RecordingEmbeddingModel:
    """Records every text it is asked to embed."""

    def __init__(self) -> None:
        self.received: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.received.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeEmbeddingModel:
    """Small deterministic model used for interface-focused tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class NormalizeForEmbeddingTests(unittest.TestCase):
    """Kangxi-radical compatibility forms must reach the model as canonical text."""

    def test_kangxi_radical_becomes_the_canonical_character(self) -> None:
        self.assertEqual(normalize_for_embedding("\u2f24连海事\u2f24学"), "大连海事大学")

    def test_fullwidth_forms_are_normalised(self) -> None:
        self.assertEqual(normalize_for_embedding("ＡＢＣ１２３"), "ABC123")

    def test_canonical_text_is_unchanged(self) -> None:
        text = "大连海事大学 2026 年竞赛列表"

        self.assertEqual(normalize_for_embedding(text), text)

    def test_non_string_raises_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            normalize_for_embedding(123)  # type: ignore[arg-type]


class EmbeddingInputNormalizationTests(unittest.TestCase):
    def test_damaged_and_canonical_text_reach_the_model_identically(self) -> None:
        model = RecordingEmbeddingModel()

        with patch("backend.knowledge.embedding._get_model", return_value=model):
            embed_text("\u2f24连海事\u2f24学")
            embed_text("大连海事大学")

        self.assertEqual(len(model.received), 2)
        self.assertEqual(model.received[0], model.received[1])

    def test_query_with_radicals_matches_a_canonical_chunk_exactly(self) -> None:
        model = RecordingEmbeddingModel()

        with patch("backend.knowledge.embedding._get_model", return_value=model):
            damaged_query = embed_text("中国\u2f24学\u2f63计算机设计\u2f24赛")
            canonical_chunk = embed_text("中国大学生计算机设计大赛")

        self.assertEqual(damaged_query, canonical_chunk)


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
