"""End-to-end tests for the PDF-to-Chroma ingestion pipeline."""

import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from backend.knowledge.chroma_store import ChromaVectorStore
from backend.knowledge.chunker import chunk_text
from backend.knowledge.ingest import ingest_pdf_to_store
from backend.knowledge.pdf_loader import PdfLoadError, load_pdf_text


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

                records = store.get_records()

                self.assertEqual(len(records), len(expected_chunks))
                self.assertEqual(
                    Counter(record.text for record in records),
                    Counter(expected_chunks),
                )
                self.assertEqual(
                    {record.metadata["chunk_index"] for record in records},
                    set(range(len(expected_chunks))),
                )
                expected_document_id = os.path.normcase(
                    str(pdf_path.resolve())
                )
                self.assertEqual(
                    {record.metadata["document_id"] for record in records},
                    {expected_document_id},
                )
                for record in records:
                    self.assertEqual(record.metadata["course"], "航海英语")
                    self.assertEqual(record.metadata["level"], "本科")
                    self.assertEqual(record.metadata["source"], "course-notes.pdf")
                    self.assertEqual(len(record.metadata["chunk_hash"]), 64)
            finally:
                store.close()

    def test_reimporting_same_pdf_is_idempotent(self) -> None:
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

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    first_count = ingest_pdf_to_store(
                        str(pdf_path),
                        {},
                        store,
                    )
                    first_records = store.get_records()
                    second_count = ingest_pdf_to_store(
                        str(pdf_path),
                        {},
                        store,
                    )

                second_records = store.get_records()

                self.assertEqual(first_count, second_count)
                self.assertEqual(len(store), first_count)
                self.assertEqual(
                    {record.id for record in second_records},
                    {record.id for record in first_records},
                )
                self.assertEqual(
                    Counter(record.text for record in second_records),
                    Counter(record.text for record in first_records),
                )
            finally:
                store.close()

    def test_same_text_from_different_documents_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_path = root / "first" / "shared.pdf"
            second_path = root / "second" / "shared.pdf"
            first_path.parent.mkdir()
            second_path.parent.mkdir()
            pdf_bytes = _create_minimal_pdf([_long_text("shared")])
            first_path.write_bytes(pdf_bytes)
            second_path.write_bytes(pdf_bytes)

            store = ChromaVectorStore(
                persist_directory=root / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    first_count = ingest_pdf_to_store(
                        str(first_path),
                        {"document_id": "doc-a"},
                        store,
                    )
                    second_count = ingest_pdf_to_store(
                        str(second_path),
                        {"document_id": "doc-b"},
                        store,
                    )

                records = store.get_records()
                first_records = store.get_records({"document_id": "doc-a"})
                second_records = store.get_records({"document_id": "doc-b"})

                self.assertEqual(first_count, second_count)
                self.assertEqual(len(store), first_count + second_count)
                self.assertEqual(len(first_records), first_count)
                self.assertEqual(len(second_records), second_count)
                self.assertEqual(
                    Counter(record.text for record in first_records),
                    Counter(record.text for record in second_records),
                )
                self.assertTrue(
                    {record.id for record in first_records}.isdisjoint(
                        record.id for record in second_records
                    )
                )
                self.assertEqual(
                    {record.metadata["document_id"] for record in records},
                    {"doc-a", "doc-b"},
                )
            finally:
                store.close()

    def test_duplicate_text_chunks_within_document_are_not_merged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "duplicates.pdf"
            repeated_text = _long_text("duplicate")
            pdf_path.write_bytes(
                _create_minimal_pdf([repeated_text, repeated_text])
            )
            expected_chunks = chunk_text(load_pdf_text(str(pdf_path)))

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    written_count = ingest_pdf_to_store(str(pdf_path), {}, store)

                records = store.get_records()

                self.assertEqual(written_count, len(expected_chunks))
                self.assertEqual(len(records), len(expected_chunks))
                self.assertEqual(len({record.id for record in records}), len(records))
                self.assertEqual(
                    Counter(record.text for record in records),
                    Counter(expected_chunks),
                )
                self.assertGreater(
                    max(Counter(expected_chunks).values()),
                    1,
                )
            finally:
                store.close()

    def test_same_basename_in_different_directories_does_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_path = root / "first" / "notes.pdf"
            second_path = root / "second" / "notes.pdf"
            first_path.parent.mkdir()
            second_path.parent.mkdir()
            first_path.write_bytes(_create_minimal_pdf(["same text"]))
            second_path.write_bytes(_create_minimal_pdf(["same text"]))

            store = ChromaVectorStore(
                persist_directory=root / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    ingest_pdf_to_store(str(first_path), {}, store)
                    ingest_pdf_to_store(str(second_path), {}, store)

                records = store.get_records()
                document_ids = {
                    record.metadata["document_id"] for record in records
                }

                self.assertEqual(len(store), 2)
                self.assertEqual(len(document_ids), 2)
                self.assertEqual(
                    len({record.id for record in records}),
                    len(records),
                )
            finally:
                store.close()

    def test_changed_document_replaces_old_chunks_and_handles_shrink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "evolving.pdf"
            pdf_path.write_bytes(
                _create_minimal_pdf(
                    [
                        _long_text("old-alpha"),
                        _long_text("old-beta"),
                    ]
                )
            )

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    old_count = ingest_pdf_to_store(str(pdf_path), {}, store)
                    old_records = store.get_records()

                    pdf_path.write_bytes(_create_minimal_pdf(["new only"]))
                    new_count = ingest_pdf_to_store(str(pdf_path), {}, store)

                new_records = store.get_records()

                self.assertGreater(old_count, 1)
                self.assertEqual(new_count, 1)
                self.assertEqual(len(store), 1)
                self.assertEqual([record.text for record in new_records], ["new only"])
                self.assertTrue(
                    {record.id for record in old_records}.isdisjoint(
                        record.id for record in new_records
                    )
                )
            finally:
                store.close()

    def test_metadata_update_does_not_create_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "metadata.pdf"
            pdf_path.write_bytes(_create_minimal_pdf(["stable text"]))

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    first_count = ingest_pdf_to_store(
                        str(pdf_path),
                        {"document_type": "旧版"},
                        store,
                    )
                    first_records = store.get_records()
                    second_count = ingest_pdf_to_store(
                        str(pdf_path),
                        {"document_type": "新版"},
                        store,
                    )

                second_records = store.get_records()

                self.assertEqual(first_count, second_count)
                self.assertEqual(len(store), first_count)
                self.assertEqual(
                    {record.id for record in second_records},
                    {record.id for record in first_records},
                )
                self.assertEqual(
                    {record.metadata["document_type"] for record in second_records},
                    {"新版"},
                )
            finally:
                store.close()

    def test_empty_updated_document_removes_previous_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "empty-update.pdf"
            pdf_path.write_bytes(_create_minimal_pdf([_long_text("old")]))

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    first_count = ingest_pdf_to_store(str(pdf_path), {}, store)

                    writer = PdfWriter()
                    writer.add_blank_page(width=612, height=792)
                    with pdf_path.open("wb") as pdf_file:
                        writer.write(pdf_file)

                    second_count = ingest_pdf_to_store(str(pdf_path), {}, store)

                self.assertGreater(first_count, 0)
                self.assertEqual(second_count, 0)
                self.assertEqual(len(store), 0)
            finally:
                store.close()

    def test_parse_failure_preserves_previous_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "broken.pdf"
            pdf_path.write_bytes(_create_minimal_pdf([_long_text("old")]))

            store = ChromaVectorStore(
                persist_directory=Path(temp_dir) / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    first_count = ingest_pdf_to_store(str(pdf_path), {}, store)
                    first_records = store.get_records()

                    pdf_path.write_bytes(b"not a valid PDF")
                    with self.assertRaises(PdfLoadError):
                        ingest_pdf_to_store(str(pdf_path), {}, store)

                self.assertGreater(first_count, 0)
                self.assertEqual(len(store), first_count)
                self.assertEqual(
                    {record.id for record in store.get_records()},
                    {record.id for record in first_records},
                )
            finally:
                store.close()

    def test_replacing_one_document_does_not_affect_other_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_path = root / "first.pdf"
            second_path = root / "second.pdf"
            first_path.write_bytes(_create_minimal_pdf([_long_text("first")]))
            second_path.write_bytes(_create_minimal_pdf(["second text"]))

            store = ChromaVectorStore(
                persist_directory=root / "chroma",
            )
            try:
                with patch(
                    "backend.knowledge.ingest.embed_text",
                    side_effect=lambda _text: [0.1, 0.2, 0.3],
                ):
                    ingest_pdf_to_store(str(first_path), {}, store)
                    ingest_pdf_to_store(str(second_path), {}, store)
                    second_before = store.get_records(
                        {"document_id": os.path.normcase(str(second_path.resolve()))}
                    )

                    first_path.write_bytes(_create_minimal_pdf(["first new"]))
                    ingest_pdf_to_store(str(first_path), {}, store)

                second_after = store.get_records(
                    {"document_id": os.path.normcase(str(second_path.resolve()))}
                )

                self.assertEqual(
                    [(record.id, record.text) for record in second_after],
                    [(record.id, record.text) for record in second_before],
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
