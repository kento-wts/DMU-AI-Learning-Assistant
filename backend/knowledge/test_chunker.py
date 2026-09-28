"""Tests for the rule-based document chunker."""

import unittest

from backend.knowledge.chunker import chunk_text


class ChunkTextTests(unittest.TestCase):
    def test_empty_text_returns_no_chunks(self) -> None:
        self.assertEqual(chunk_text("  \n\n  "), [])

    def test_short_paragraphs_are_kept_together(self) -> None:
        text = "第一段。\n\n第二段。"

        self.assertEqual(chunk_text(text, max_chars=100), [text])

    def test_oversized_paragraph_splits_at_sentence_boundaries(self) -> None:
        first_sentence = "甲" * 120 + "。"
        second_sentence = "乙" * 120 + "。"

        chunks = chunk_text(first_sentence + second_sentence, max_chars=150)

        self.assertEqual(chunks, [first_sentence, second_sentence])

    def test_english_sentence_spacing_is_preserved(self) -> None:
        first_sentence = "A" * 60 + "."
        second_sentence = "B" * 60 + "."

        chunks = chunk_text(f"{first_sentence} {second_sentence}", max_chars=100)

        self.assertEqual(chunks, [first_sentence, second_sentence])

    def test_punctuation_free_sentence_has_bounded_fallback(self) -> None:
        chunks = chunk_text("x" * 25, max_chars=10)

        self.assertEqual([len(chunk) for chunk in chunks], [10, 10, 5])
        self.assertEqual("".join(chunks), "x" * 25)

    def test_max_chars_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            chunk_text("content", max_chars=0)


if __name__ == "__main__":
    unittest.main()
