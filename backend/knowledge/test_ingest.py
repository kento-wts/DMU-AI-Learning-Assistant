"""Tests for the PDF-to-chunk ingestion pipeline."""

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from backend.knowledge.ingest import ingest_pdf


class IngestPdfTests(unittest.TestCase):
    def test_valid_pdf_is_loaded_and_chunked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "valid.pdf"
            pdf_path.write_bytes(_create_minimal_pdf(["Alpha page.", "Beta page."]))

            chunks = ingest_pdf(str(pdf_path), max_chars=15)

            self.assertEqual(chunks, ["Alpha page.", "Beta page."])

    def test_pdf_without_text_returns_no_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "blank.pdf"

            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with pdf_path.open("wb") as pdf_file:
                writer.write(pdf_file)

            self.assertEqual(ingest_pdf(str(pdf_path)), [])

    def test_missing_pdf_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.pdf"

            with self.assertRaisesRegex(FileNotFoundError, "PDF file not found"):
                ingest_pdf(str(missing_path))


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
