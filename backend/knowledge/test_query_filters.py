"""Tests for deriving retrieval filters from explicit question constraints."""

import unittest

from .query_filters import build_retrieval_scope, extract_years


class ExtractYearsTests(unittest.TestCase):
    def test_single_year_with_marker_is_found(self) -> None:
        self.assertEqual(extract_years("2026年大连海事大学本科生有哪些创新创业竞赛？"), (2026,))

    def test_question_without_year_yields_nothing(self) -> None:
        self.assertEqual(extract_years("有哪些创新创业竞赛？"), ())

    def test_full_width_digits_are_normalised(self) -> None:
        self.assertEqual(extract_years("２０２６年有哪些竞赛？"), (2026,))

    def test_cohort_years_are_not_treated_as_document_years(self) -> None:
        self.assertEqual(extract_years("我是2023年入学的，现在有哪些竞赛？"), ())
        self.assertEqual(extract_years("2023级学生能参加哪些竞赛？"), ())

    def test_numbers_that_are_not_years_are_ignored(self) -> None:
        self.assertEqual(extract_years("联系人 18840915361，字数 1200 字"), ())

    def test_multiple_years_are_reported_in_order(self) -> None:
        self.assertEqual(extract_years("2025年和2026年的名单有什么区别？"), (2025, 2026))


class RetrievalScopeTests(unittest.TestCase):
    def test_single_year_becomes_a_filter_with_a_note(self) -> None:
        scope = build_retrieval_scope("2026年有哪些创新创业竞赛？")

        self.assertEqual(scope.metadata_filter, {"year": 2026})
        self.assertIsNotNone(scope.note)
        self.assertIn("2026", scope.note)
        self.assertEqual(scope.describe_years(), "2026")

    def test_no_year_means_no_filter_and_no_note(self) -> None:
        scope = build_retrieval_scope("有哪些创新创业竞赛？")

        self.assertIsNone(scope.metadata_filter)
        self.assertIsNone(scope.note)

    def test_two_years_stay_unfiltered_but_are_explained(self) -> None:
        scope = build_retrieval_scope("2025年和2026年的竞赛名单有什么区别？")

        self.assertIsNone(scope.metadata_filter)
        self.assertIn("2025", scope.note)
        self.assertIn("2026", scope.note)

    def test_major_and_grade_are_never_guessed(self) -> None:
        scope = build_retrieval_scope("2026年软件工程专业大二学生能参加哪些A类竞赛？")

        self.assertEqual(scope.metadata_filter, {"year": 2026})
        self.assertEqual(list(scope.metadata_filter), ["year"])


if __name__ == "__main__":
    unittest.main()
