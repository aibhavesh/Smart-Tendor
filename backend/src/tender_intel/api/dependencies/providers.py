"""Provider adapters (downloader, storage) resolved from settings."""

from __future__ import annotations

from fastapi import Depends, Request

from tender_intel.api.dependencies.db import get_app_settings, get_container
from tender_intel.core.config import Settings
from tender_intel.domain.interfaces.providers import (
    DocumentTextExtractor,
    EmbeddingProvider,
    LLMProvider,
    VectorStore,
)
from tender_intel.infrastructure.downloader import HttpxDownloader
from tender_intel.infrastructure.extraction.pdf_backends import (
    PdfPlumberBOQExtractor,
    resolve_text_extractor,
)
from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor
from tender_intel.infrastructure.storage import LocalFileStorage


def get_downloader() -> HttpxDownloader:
    return HttpxDownloader()


def get_storage(settings: Settings = Depends(get_app_settings)) -> LocalFileStorage:
    return LocalFileStorage(settings.storage_dir)


def get_text_extractor(
    settings: Settings = Depends(get_app_settings),
) -> DocumentTextExtractor:
    return resolve_text_extractor(settings.extraction_text_backend)


def get_table_extractor() -> PdfPlumberBOQExtractor:
    return PdfPlumberBOQExtractor()


def get_metadata_backend() -> RuleBasedMetadataExtractor:
    return RuleBasedMetadataExtractor()


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    return get_container(request).embedding_provider()


def get_vector_store(request: Request) -> VectorStore:
    return get_container(request).vector_store()


def get_llm_provider(settings: Settings = Depends(get_app_settings)) -> LLMProvider:
    from tender_intel.infrastructure.llm.factory import resolve_llm_provider

    return resolve_llm_provider(settings)
