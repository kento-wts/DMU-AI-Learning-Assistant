"""Derive metadata filters from constraints written literally in a question.

Design rules, in order of importance:

1. **Never guess.** Only a year that appears in the question text is used.
   ``major``, grade and applicable scope are *not* derived: inferring them would
   silently hide documents the user actually asked about.
2. **Only one year is a constraint.** A question like "2025 年和 2026 年的名单
   有什么区别" mentions two years on purpose; filtering it to one of them would
   drop half the evidence, so it stays unfiltered and the prompt is told why.
3. **A year must read as a document year.** "2026 年" and "2026 年度" qualify.
   A year that describes the user rather than the material ("2023 年入学",
   "2023 级") is ignored - it is a cohort marker, not a document year.

The returned :class:`RetrievalScope` carries both the Chroma filter and an
optional note for the prompt, so the answer can state which scope was used.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# A 4-digit year immediately followed by 年, not embedded in a longer number.
_YEAR_WITH_MARKER = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年")

# "2023 年入学" / "2023 年级" describe the student, not the material.
_COHORT_SUFFIXES = ("入学", "入校", "毕业", "级")


def normalise_question(question: str) -> str:
    """Return the question with compatibility forms folded (full-width digits etc.)."""
    return unicodedata.normalize("NFKC", question)


def extract_years(question: str) -> tuple[int, ...]:
    """Return the distinct document years mentioned in the question, in order.

    ``"2026年有哪些竞赛"`` -> ``(2026,)``
    ``"2023年入学，现在有哪些竞赛"`` -> ``()`` (cohort marker, not a document year)
    """
    text = normalise_question(question)
    years: list[int] = []

    for match in _YEAR_WITH_MARKER.finditer(text):
        suffix = text[match.end() : match.end() + 2]
        if any(suffix.startswith(marker) for marker in _COHORT_SUFFIXES):
            continue
        year = int(match.group(1))
        if year not in years:
            years.append(year)

    return tuple(years)


@dataclass(frozen=True)
class RetrievalScope:
    """What the retrieval call should be limited to, if anything."""

    years: tuple[int, ...] = ()
    metadata_filter: dict[str, Any] | None = field(default=None)
    note: str | None = field(default=None)

    def describe_years(self) -> str:
        """Return the years as a human-readable string."""
        return "、".join(str(year) for year in self.years)


def build_retrieval_scope(question: str) -> RetrievalScope:
    """Return the retrieval scope implied by ``question``.

    * exactly one document year -> filter on ``{"year": <year>}`` plus a note
    * two or more years -> no filter, plus a note explaining why
    * no year -> no filter, no note (the previous behaviour)
    """
    years = extract_years(question)

    if len(years) == 1:
        year = years[0]
        return RetrievalScope(
            years=years,
            metadata_filter={"year": year},
            note=(
                f"本次检索已按年份过滤，只使用 {year} 年的资料。"
                f"若这些资料不足以回答，请明确说明 {year} 年的资料不足，"
                f"不要用其他年份的资料代替。"
            ),
        )

    if len(years) > 1:
        listed = "、".join(str(year) for year in years)
        return RetrievalScope(
            years=years,
            metadata_filter=None,
            note=(
                f"问题里提到了多个年份（{listed}），本次检索未按年份过滤，"
                f"回答时请分别标明每条资料属于哪一年。"
            ),
        )

    return RetrievalScope()


__all__ = [
    "RetrievalScope",
    "build_retrieval_scope",
    "extract_years",
    "normalise_question",
]
