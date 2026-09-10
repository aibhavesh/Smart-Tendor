"""LLM-provider selection."""

from __future__ import annotations

from tender_intel.core.config import Settings
from tender_intel.domain.interfaces.providers import LLMProvider
from tender_intel.infrastructure.llm.gemini import GeminiLLMProvider


def resolve_llm_provider(settings: Settings) -> LLMProvider:
    # Always returns a provider; when no API key is configured it raises at call
    # time and the AnalystService falls back to the deterministic generator.
    return GeminiLLMProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
