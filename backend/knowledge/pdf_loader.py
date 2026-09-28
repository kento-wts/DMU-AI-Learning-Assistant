"""PDF text extraction for knowledge-base documents."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfLoadError(RuntimeError):
    """Raised when an existing PDF cannot be parsed or read."""


def load_pdf_text(pdf_path: str) -> str:
    """Extract and return all readable text from a PDF.

    Pages are processed in document order. Extracted page text is stripped,
    non-empty pages are separated by a blank line, and blank pages are kept
    out of the result.

    Args:
        pdf_path: Path to the source PDF file.

    Returns:
        The combined text from all readable pages, or an empty string when no
        text can be extracted.

    Raises:
        FileNotFoundError: The path does not exist.
        IsADirectoryError: The path is not a regular file.
        PdfLoadError: The PDF exists but cannot be parsed or read.
    """
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if not path.is_file():
        raise IsADirectoryError(f"PDF path is not a file: {pdf_path}")

    try:
        reader = PdfReader(str(path))
        page_texts: list[str] = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                raise PdfLoadError(
                    f"Unable to extract text from PDF page {page_number}: {pdf_path}"
                ) from exc

            normalized_text = page_text.replace("\r\n", "\n").replace("\r", "\n").strip()
            if normalized_text:
                page_texts.append(normalized_text)

    except PdfReadError as exc:
        raise PdfLoadError(f"Unable to read PDF: {pdf_path}") from exc
    except OSError as exc:
        raise PdfLoadError(f"Unable to read PDF: {pdf_path}") from exc

    return "\n\n".join(page_texts)


__all__ = ["PdfLoadError", "load_pdf_text"]
