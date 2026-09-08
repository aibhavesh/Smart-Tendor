"""HTTP document downloader (implements the Downloader port)."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

import httpx

from tender_intel.domain.interfaces.providers import DownloadResult

_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)


def _filename_from(response: httpx.Response, url: str) -> str | None:
    disposition = response.headers.get("content-disposition", "")
    match = _FILENAME_RE.search(disposition)
    if match:
        return unquote(match.group(1)).strip()
    path = urlparse(url).path
    tail = path.rsplit("/", 1)[-1]
    return unquote(tail) or None


class HttpxDownloader:
    def __init__(self, timeout: float = 30.0, max_bytes: int = 100 * 1024 * 1024) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes

    async def download(self, url: str) -> DownloadResult:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
        if len(content) > self._max_bytes:
            raise ValueError(f"document exceeds max size ({len(content)} bytes)")
        mime = (response.headers.get("content-type") or "").split(";")[0].strip() or None
        return DownloadResult(
            content=content,
            mime_type=mime,
            suggested_name=_filename_from(response, url),
        )
