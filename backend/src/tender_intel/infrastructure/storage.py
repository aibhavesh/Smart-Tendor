"""Local filesystem storage (implements the FileStorage port).

File IO runs in a worker thread so it does not block the event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


class LocalFileStorage:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir).resolve()

    def _resolve(self, relative_path: str) -> Path:
        # Prevent path traversal outside the storage root.
        target = (self._base / relative_path).resolve()
        if not target.is_relative_to(self._base):
            raise ValueError(f"path escapes storage root: {relative_path!r}")
        return target

    async def save(self, relative_path: str, content: bytes) -> str:
        target = self._resolve(relative_path)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        await asyncio.to_thread(_write)
        return str(target.relative_to(self._base)).replace("\\", "/")

    async def read(self, relative_path: str) -> bytes:
        target = self._resolve(relative_path)
        return await asyncio.to_thread(target.read_bytes)

    async def delete(self, relative_path: str) -> None:
        target = self._resolve(relative_path)
        await asyncio.to_thread(lambda: target.unlink(missing_ok=True))
