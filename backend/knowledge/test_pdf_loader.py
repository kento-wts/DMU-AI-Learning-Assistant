"""Tests for PDF text extraction."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.knowledge.pdf_loader import PdfLoadError, load_pdf_text


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    """Stands in for ``PdfReader`` so PDF output character sets can be forced."""

    def __init__(self, _path: str, page_texts: list[str]) -> None:
        self.pages = [_FakePage(text) for text in page_texts]


class LoadPdfTextTests(unittest.TestCase):
    def test_module_exposes_loader_function(self) -> None:
        self.assertTrue(callable(load_pdf_text))

    def test_missing_pdf_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.pdf"

            with self.assertRaisesRegex(FileNotFoundError, "PDF file not found"):
                load_pdf_text(str(missing_path))

    def test_invalid_pdf_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.pdf"
            invalid_path.write_bytes(b"not a valid PDF")

            with self.assertRaisesRegex(PdfLoadError, "Unable to read PDF"):
                load_pdf_text(str(invalid_path))

    def test_extracts_text_from_multiple_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "two-pages.pdf"
            pdf_path.write_bytes(_create_minimal_pdf(["First page", "Second page"]))

            extracted_text = load_pdf_text(str(pdf_path))

            self.assertEqual(extracted_text, "First page\n\nSecond page")


class CompatibilityCharacterTests(unittest.TestCase):
    """PDFs that emit Kangxi radicals must not poison the extracted text.

    The 2026 competition list in this repository extracts ``U+2F24`` (⼤)
    instead of ``U+5927`` (大). Those forms must be normalised before chunking
    and embedding, otherwise the canonical word never matches.
    """

    # Kangxi-radical spellings of: 大连海事大学 / 工业大学 / 生日
    _DAMAGED = "\u2f24连海事\u2f24学 \u2f2f业\u2f24学 \u2f63\u2f47"

    def _load_with_page_text(self, page_text: str) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "compat.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            with patch(
                "backend.knowledge.pdf_loader.PdfReader",
                side_effect=lambda path: _FakeReader(path, [page_text]),
            ):
                return load_pdf_text(str(pdf_path))

    def test_kangxi_radicals_are_normalised_to_canonical_characters(self) -> None:
        extracted = self._load_with_page_text(self._DAMAGED)

        self.assertEqual(extracted, "大连海事大学 工业大学 生日")
        self.assertNotIn("\u2f24", extracted)
        self.assertNotIn("\u2f2f", extracted)

    def test_extracted_text_contains_a_canonical_search_term(self) -> None:
        extracted = self._load_with_page_text(self._DAMAGED)

        self.assertIn("大连海事大学", extracted)

    def test_nbsp_is_normalised_to_a_plain_space(self) -> None:
        extracted = self._load_with_page_text("大连海事大学\u00a0教务处")

        self.assertEqual(extracted, "大连海事大学 教务处")

    def test_ordinary_text_is_unchanged(self) -> None:
        extracted = self._load_with_page_text("普通中文内容 ABC 123")

        self.assertEqual(extracted, "普通中文内容 ABC 123")


def _create_minimal_pdf(page_texts: list[str]) -> bytes:
    """Create a small valid PDF without adding a PDF-generation dependency."""
    page_object_numbers = [4 + index * 2 for index in range(len(page_texts))]
    content_object_numbers = [number + 1 for number in page_object_numbers]
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Kids [{kids}] /Count {len(page_texts)} >>"
        ).encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    for index, (page_text, content_number) in enumerate(
        zip(page_texts, content_object_numbers),
        start=1,
    ):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode("ascii")
        )

        encoded_text = page_text.encode("ascii")
        content_stream = (
            f"BT /F1 12 Tf 72 {720 - index * 20} Td ({encoded_text.decode()}) Tj ET"
        ).encode("ascii")
        objects.append(
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"\nendstream"
        )

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for object_number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )

    return bytes(pdf)


if __name__ == "__main__":
    unittest.main()
