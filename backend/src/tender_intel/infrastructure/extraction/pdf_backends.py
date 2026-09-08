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
