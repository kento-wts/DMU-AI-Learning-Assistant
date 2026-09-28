"""Rule-based text chunking for knowledge-base documents."""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 1200

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
_SEMANTIC_BOUNDARY_RE = re.compile(
    r"(?P<newline>\n+)|(?P<sentence>[。！？!?；;]+|[.!?]+(?=\s|$))"
)


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split complete text into paragraph-aware chunks.

    Short paragraphs are kept together when they fit. Oversized paragraphs
    are split at sentence boundaries, with a bounded fallback only for a
    single sentence that is longer than ``max_chars``.

    Args:
        text: Complete source text.
        max_chars: Maximum number of characters in each returned chunk.

    Returns:
        A list of non-empty text chunks.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if max_chars < 1:
        raise ValueError("max_chars must be greater than zero")

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(paragraph, max_chars))
            continue

        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Normalize line endings and split text on blank lines."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    return [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_RE.split(normalized)
        if paragraph.strip()
    ]


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Pack semantic units from one paragraph into bounded chunks."""
    units = _split_semantic_units(paragraph)
    chunks: list[str] = []
    current = ""
    separator = ""

    for unit, separator_after in units:
        if len(unit) > max_chars:
            if current:
                chunks.append(current)
                current = ""

            hard_parts = _split_oversized_unit(unit, max_chars)
            chunks.extend(hard_parts[:-1])
            current = hard_parts[-1]
            separator = separator_after
            continue

        candidate = unit if not current else f"{current}{separator}{unit}"
        if len(candidate) <= max_chars:
            current = candidate
            separator = separator_after
        else:
            chunks.append(current)
            current = unit
            separator = separator_after

    if current:
        chunks.append(current)

    return chunks


def _split_semantic_units(text: str) -> list[tuple[str, str]]:
    """Return sentence-like units and the separator that follows each one."""
    units: list[tuple[str, str]] = []
    start = 0

    for boundary in _SEMANTIC_BOUNDARY_RE.finditer(text):
        unit = text[start : boundary.end()].strip()
        if unit:
            if boundary.lastgroup == "newline":
                separator = "\n"
            else:
                separator = " " if unit[-1].isascii() else ""
            units.append((unit, separator))
        start = boundary.end()

    tail = text[start:].strip()
    if tail:
        units.append((tail, ""))

    return units


def _split_oversized_unit(unit: str, max_chars: int) -> list[str]:
    """Bound a single unit, preferring whitespace over a hard character cut."""
    parts: list[str] = []
    start = 0

    while len(unit) - start > max_chars:
        limit = start + max_chars
        lower_bound = start + max_chars // 2
        whitespace_matches = list(re.finditer(r"\s+", unit[lower_bound:limit]))

        if whitespace_matches:
            last_match = whitespace_matches[-1]
            cut = lower_bound + last_match.start()
            if cut == start:
                cut = limit
        else:
            cut = limit

        part = unit[start:cut].strip()
        if part:
            parts.append(part)

        start = cut
        while start < len(unit) and unit[start].isspace():
            start += 1

    tail = unit[start:].strip()
    if tail:
        parts.append(tail)

    return parts
