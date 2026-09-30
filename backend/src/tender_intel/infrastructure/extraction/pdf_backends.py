"""PDF text and table extraction backends (pdfplumber, PyMuPDF).

Both are synchronous/CPU-bound; the extraction service runs them in a worker
thread so the event loop is not blocked.
"""

from __future__ import annotations

import io

from tender_intel.domain.interfaces.providers import Table


class PdfPlumberTextExtractor:
    def extract_text(self, content: bytes) -> str:
        import pdfplumber

        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)


class PyMuPDFTextExtractor:
    def extract_text(self, content: bytes) -> str:
        import fitz  # PyMuPDF

        parts: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                parts.append(page.get_text())
        return "\n".join(parts)


class OcrPdfTextExtractor:
    """Extract text from an image-only PDF using the local Tesseract engine.

    Certificates are frequently scanned.  PDF text extractors correctly return
    an empty string for those files, so OCR is deliberately a fallback rather
    than the default path for every document.
    """

    def extract_text(self, content: bytes) -> str:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image

        parts: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                # 2x is a good balance for small certificate text and upload time.
                image_bytes = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
                with Image.open(io.BytesIO(image_bytes)) as image:
                    parts.append(pytesseract.image_to_string(image, config="--psm 6"))
        return "\n".join(parts)


class PdfPlumberBOQExtractor:
    def extract_tables(self, content: bytes) -> list[Table]:
        import pdfplumber

        tables: list[Table] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for raw in page.extract_tables():
                    tables.append([list(row) for row in raw])
        return tables


def resolve_text_extractor(backend: str) -> PdfPlumberTextExtractor | PyMuPDFTextExtractor:
    if backend.lower() in ("pymupdf", "fitz"):
        return PyMuPDFTextExtractor()
    return PdfPlumberTextExtractor()
