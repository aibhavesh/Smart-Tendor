"""Provider ports — external capabilities the domain depends on abstractly.

Concrete adapters live in ``infrastructure`` (Qdrant, bge embeddings, Gemini,
httpx downloader, local file storage). The domain and application layers know
only these Protocols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from tender_intel.domain.value_objects.extracted_field import ExtractedField


@dataclass(frozen=True, slots=True)
class DownloadResult:
    content: bytes
    mime_type: str | None
    suggested_name: str | None


@runtime_checkable
class Downloader(Protocol):
    async def download(self, url: str) -> DownloadResult: ...


@runtime_checkable
class FileStorage(Protocol):
    async def save(self, relative_path: str, content: bytes) -> str:
        """Persist bytes, returning the stored path."""
        ...

    async def read(self, relative_path: str) -> bytes: ...

    async def delete(self, relative_path: str) -> None: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class VectorMatch:
    id: UUID
    score: float
    payload: dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    async def ensure_collection(self, name: str, dimension: int) -> None: ...

    async def upsert(
        self, collection: str, id: UUID, vector: list[float], payload: dict[str, Any]
    ) -> None: ...

    async def search(
        self, collection: str, vector: list[float], limit: int
    ) -> list[VectorMatch]: ...

    async def delete(self, collection: str, id: UUID) -> None: ...

    async def health(self) -> bool: ...


@runtime_checkable
class LLMProvider(Protocol):
    async def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Return schema-valid JSON, or raise on malformed/unavailable output."""
        ...


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str  # Google 'sub' — the stable per-user identifier
    email: str
    full_name: str
    #: Google's 'hd' (hosted domain) claim, present only for Google Workspace
    #: accounts. It is a stronger admission signal than the address string
    #: because Google asserts it; ``None`` means the caller must fall back to
    #: checking the address domain.
    hosted_domain: str | None = None


@runtime_checkable
class GoogleTokenVerifier(Protocol):
    async def verify(self, id_token: str) -> GoogleIdentity:
        """Verify a Google ID token, or raise on an invalid token."""
        ...


# A table is a list of rows; each row is a list of (possibly empty) cells.
Table = list[list[str | None]]


@runtime_checkable
class DocumentTextExtractor(Protocol):
    def extract_text(self, content: bytes) -> str:
        """Extract plain text from a document (PDF)."""
        ...


@runtime_checkable
class BOQTableExtractor(Protocol):
    def extract_tables(self, content: bytes) -> list[Table]:
        """Extract tabular data from a document (PDF)."""
        ...


@runtime_checkable
class MetadataExtractionBackend(Protocol):
    def extract(self, text: str) -> dict[str, ExtractedField[Any]]:
        """Map raw document text to the ten metadata fields (UNKNOWN if absent)."""
        ...
