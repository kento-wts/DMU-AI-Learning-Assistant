"""Tests for the PDF-to-Chroma command-line import wrapper."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.knowledge.chroma_store import ChromaVectorStore
from backend.knowledge.ingest_document import ingest_document


class IngestDocumentTests(unittest.TestCase):
    def test_ingest_document_delegates_to_ingest_pdf_to_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "notes.pdf"
            store = ChromaVectorStore(persist_directory=Path(temp_dir) / "chroma")
            try:
                with patch(
                    "backend.knowledge.ingest_document.ingest_pdf_to_store",
                    return_value=2,
                ) as ingest_mock:
                    result = ingest_document(
                        str(pdf_path),
                        {
                            "year": 2026,
                            "major": "软件工程",
                            "document_type": "管理办法",
                        },
                        store=store,
                    )

                ingest_mock.assert_called_once_with(
                    str(pdf_path),
                    {
                        "year": 2026,
                        "major": "软件工程",
                        "document_type": "管理办法",
                    },
                    store,
                )
                self.assertEqual(result["chunk_count"], 2)
                self.assertEqual(result["filename"], "notes.pdf")
                self.assertEqual(
                    result["metadata"]["source"],
                    "notes.pdf",
                )
            finally:
                store.close()

    def test_import_is_idempotent_and_saves_metadata(self) -> None:
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

            store = ChromaVectorStore(persist_directory=Path(temp_dir) / "chroma")
            try:
                store.add(
                    "existing chunk",
                    [0.1, 0.2, 0.3],
                    {"kind": "existing"},
                )
                initial_count = len(store)

                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    first_result = ingest_document(
                        str(pdf_path),
                        {
                            "year": 2026,
                            "major": "软件工程",
                            "document_type": "管理办法",
                        },
                        store=store,
                    )
                    count_after_first_import = len(store)
                    second_result = ingest_document(
                        str(pdf_path),
                        {
                            "year": 2026,
                            "major": "软件工程",
                            "document_type": "管理办法",
                        },
                        store=store,
                    )

                self.assertGreater(first_result["chunk_count"], 0)
                self.assertEqual(
                    first_result["chunk_count"],
                    second_result["chunk_count"],
                )
                self.assertEqual(
                    count_after_first_import,
                    initial_count + first_result["chunk_count"],
                )
                self.assertEqual(len(store), count_after_first_import)

                results = store.search([0.1, 0.2, 0.3], top_k=len(store))
                imported_results = [
                    item
                    for item in results
                    if item.metadata.get("kind") != "existing"
                ]

                self.assertEqual(
                    len(imported_results),
                    first_result["chunk_count"],
                )
                document_id = os.path.normcase(str(pdf_path.resolve()))
                for item in imported_results:
                    self.assertEqual(
                        {
                            key: item.metadata[key]
                            for key in (
                                "year",
                                "major",
                                "document_type",
                                "source",
                            )
                        },
                        {
                            "year": 2026,
                            "major": "软件工程",
                            "document_type": "管理办法",
                            "source": "course-notes.pdf",
                        },
                    )
                    self.assertEqual(item.metadata["document_id"], document_id)
                    self.assertIsInstance(item.metadata["chunk_index"], int)
                    self.assertEqual(len(item.metadata["chunk_hash"]), 64)
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
