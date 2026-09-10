"""Gemini LLM provider (implements the LLMProvider port) via the REST API.

Returns schema-constrained JSON. Any failure — missing key, network error,
non-200, unparseable body — raises :class:`AIProviderError`; the AnalystService
catches it and falls back to the deterministic generator so the report endpoint
never fails (NFR-405).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class AIProviderError(Exception):
    """The AI provider is unavailable or returned unusable output."""


class GeminiLLMProvider:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http = http_client
        self._timeout = timeout

    async def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        if not self._api_key:
            raise AIProviderError("Gemini API key not configured")

        url = f"{_BASE_URL}/models/{self._model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        client = self._http or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(url, params={"key": self._api_key}, json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Gemini request failed: {exc}") from exc
        finally:
            if self._http is None:
                await client.aclose()

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"Gemini returned unusable output: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AIProviderError("Gemini output is not a JSON object")
        return parsed
