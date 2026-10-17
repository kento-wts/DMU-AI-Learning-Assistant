"""Corpus-level regression guards for the knowledge documents.

These tests read ``backend/knowledge/documents/`` and assert invariants that a
future document update could silently break. They never write to the Chroma
store and never call the embedding model, so they stay fast.

Checked invariants:

* every PDF still extracts to text (no scanned-only or broken file)
* no extracted text contains Kangxi-radical compatibility characters, which
  would poison retrieval (see ``test_pdf_loader.CompatibilityCharacterTests``)
* every chunk respects the default ``max_chars`` bound
* any document that mentions a competition list year also carries that year in
  a way a caller can filter on
* the document set is exactly the 10 files verified in this branch
"""

from __future__ import annotations

import hashlib
import unittest
import unicodedata
from pathlib import Path

from backend.knowledge.chunker import DEFAULT_MAX_CHARS, chunk_text
from backend.knowledge.pdf_loader import load_pdf_text

DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"

# sha256 of every document verified on this branch. A changed hash means the
# document content changed and the retrieval results must be re-verified.
VERIFIED_DOCUMENT_HASHES: dict[str, str] = {
    "2025-2中队本科生综合素质测评实施细则.pdf": (
        "c65faad29633462ca41de65960ed0d1cc15c6713dae9284c4b33613d7f7d5d00"
    ),
    "大连海事大学办公室关于印发《大连海事大学大学生创新创业竞赛管理办法》的通知.pdf": (
        "f334c2016e4cadc55f64bec1d1b7317872980c17907e2526ef42c841b7ca8f4c"
    ),
    "大连海事大学本科生奖学金评定办法.pdf": (
        "29af4410864a8e493799e03db9a82ea88d963173290047d4a4f9abcf595f3362"
    ),
    "大连海事大学大学生科技创新奖励办法（正文）.pdf": (
        "5a9b5ee81ac08af7574e08b94688ae891b8b35e506f2ead24d3c89a7a57991e3"
    ),
    "大连海事大学党政办公室关于印发《大连海事大学非航海类专业本科生学籍管理规定》的通知.pdf": (
        "bac799d986a0d27649cba3a3b8f77d9c92011775ee02fd39f21d88cd85ad6253"
    ),
    "大连海事大学党政办公室关于印发《大连海事大学推荐优秀应届本科毕业生免试攻读硕士研究生办法》的通知.pdf": (
        "5088f27ee0ef538ac7bbf43c526d6730d3b42cb3291b76056ed064aa34be361d"
    ),
    "大连海事大学学生离校请假单.pdf": (
        "6e5817629f70c8afe52bcd9c252b41f3a56cd7070748992f89f887bcc535463d"
    ),
    "大连海事大学学生违纪处分办法.pdf": (
        "d6498b123db93234099346f0b600a26ca566d483a5f0f767c4acefaa047a28e2"
    ),
    "附件.《大连海事大学本科生创新创业竞赛列表(2025年)》.pdf": (
        "e742b14fecddbbe07645fbece0267fbeb85b37b81481ddea26e1208248ff47b4"
    ),
    "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf": (
        "13c6c24a84d6b7b6bb7bfc72b5fa8f8623d9b205ae69f1ed490ae3f2512626a8"
    ),
}

# Documents whose text mentions a competition-list year.
COMPETITION_LIST_YEARS = {
    "附件.《大连海事大学本科生创新创业竞赛列表(2025年)》.pdf": "2025",
    "附件1.《大连海事大学本科生创新创业竞赛列表(2026年)》.pdf": "2026",
}

# Characters that NFKC would change. If one survives extraction, the chunk
# stored in Chroma will not match a normally typed query.
_KANGXI_RANGES = ((0x2E80, 0x2FDF), (0xF900, 0xFAFF), (0xFE30, 0xFE4F))


def _pdf_paths() -> list[Path]:
    return sorted(DOCUMENTS_DIR.glob("*.pdf"))


def _compatibility_characters(text: str) -> dict[str, int]:
    """Return compatibility characters in ``text`` that NFKC would rewrite."""
    found: dict[str, int] = {}

    for char in text:
        codepoint = ord(char)
        if not any(low <= codepoint <= high for low, high in _KANGXI_RANGES):
            continue
        if unicodedata.normalize("NFKC", char) != char:
            found[char] = found.get(char, 0) + 1

    return found


class KnowledgeDocumentSetTests(unittest.TestCase):
    def test_document_directory_is_not_empty(self) -> None:
        self.assertTrue(_pdf_paths(), "no knowledge PDFs found")

    def test_document_set_matches_the_verified_snapshot(self) -> None:
        present = {path.name for path in _pdf_paths()}

        self.assertEqual(present, set(VERIFIED_DOCUMENT_HASHES))
        self.assertEqual(len(present), 10)

    def test_no_document_content_changed_since_verification(self) -> None:
        for path in _pdf_paths():
            with self.subTest(document=path.name):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(
                    digest,
                    VERIFIED_DOCUMENT_HASHES[path.name],
                    "document changed: retrieval results must be re-verified",
                )


class ExtractedTextTests(unittest.TestCase):
    def test_every_document_yields_extractable_text(self) -> None:
        for path in _pdf_paths():
            with self.subTest(document=path.name):
                self.assertGreater(len(load_pdf_text(str(path))), 100)

    def test_no_document_extracts_compatibility_characters(self) -> None:
        """Regression guard for the 2026 list Kangxi-radical defect."""
        for path in _pdf_paths():
            with self.subTest(document=path.name):
                found = _compatibility_characters(load_pdf_text(str(path)))
                self.assertEqual(
                    found,
                    {},
                    f"compatibility characters survived extraction: {found}",
                )

    def test_competition_list_documents_mention_their_own_year(self) -> None:
        for name, year in COMPETITION_LIST_YEARS.items():
            with self.subTest(document=name):
                text = load_pdf_text(str(DOCUMENTS_DIR / name))
                self.assertIn(year, text)


class ChunkBoundTests(unittest.TestCase):
    def test_every_chunk_respects_the_default_bound(self) -> None:
        for path in _pdf_paths():
            with self.subTest(document=path.name):
                chunks = chunk_text(load_pdf_text(str(path)))
                self.assertTrue(chunks)
                too_long = [len(chunk) for chunk in chunks if len(chunk) > DEFAULT_MAX_CHARS]
                self.assertEqual(too_long, [])

    def test_no_chunk_is_blank(self) -> None:
        for path in _pdf_paths():
            with self.subTest(document=path.name):
                chunks = chunk_text(load_pdf_text(str(path)))
                self.assertTrue(all(chunk.strip() for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
