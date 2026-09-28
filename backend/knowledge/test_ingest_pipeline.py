"""End-to-end tests for the PDF-to-Chroma ingestion pipeline."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.knowledge.chroma_store import ChromaVectorStore
from backend.knowledge.chunker import chunk_text
from backend.knowledge.ingest import ingest_pdf_to_store
from backend.knowledge.pdf_loader import load_pdf_text


class IngestPdfToStoreTests(unittest.TestCase):
    def test_full_pipeline_persists_chunks_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "course-notes.pdf"
            pdf_path.write_bytes(
                _create_minimal_pdf(
                    [
                        _long_text("alpha"),
                        _long_text("beta"),
                    ]
                )
            )

            expected_chunks = chunk_text(load_pdf_text(str(pdf_path)))
            self.assertGreater(len(expected_chunks), 1)

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                # Keep the pipeline test independent from local or remote models.
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ) as embed_mock:
                    written_count = ingest_pdf_to_store(
                        str(pdf_path),
                        {
                            "course": "航海英语",
                            "level": "本科",
                            "source": "should-be-replaced.pdf",
                        },
                        store,
                    )

                self.assertEqual(written_count, len(expected_chunks))
                self.assertEqual(embed_mock.call_count, len(expected_chunks))
                self.assertEqual(len(store), len(expected_chunks))

                results = store.search(
                    [0.1, 0.2, 0.3],
                    top_k=len(expected_chunks),
                )

                self.assertEqual(len(results), len(expected_chunks))
                self.assertEqual(
                    {result.text for result in results},
                    set(expected_chunks),
                )
                for result in results:
                    self.assertEqual(
                        result.metadata,
                        {
                            "course": "航海英语",
                            "level": "本科",
                            "source": "course-notes.pdf",
                        },
                    )
            finally:
                store.close()


def _long_text(marker: str) -> str:
    """Return text long enough to force the default chunker to split it."""
    return f"{marker} " * 220


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
