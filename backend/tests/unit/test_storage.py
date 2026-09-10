"""Phase 3 local file-storage tests."""

from __future__ import annotations

import pytest

from tender_intel.infrastructure.storage import LocalFileStorage


async def test_save_read_delete_roundtrip(tmp_path):
    storage = LocalFileStorage(str(tmp_path))
    rel = await storage.save("tenders/abc/doc.pdf", b"hello")
    assert rel == "tenders/abc/doc.pdf"
    assert await storage.read("tenders/abc/doc.pdf") == b"hello"

    await storage.delete("tenders/abc/doc.pdf")
    with pytest.raises(FileNotFoundError):
        await storage.read("tenders/abc/doc.pdf")


async def test_path_traversal_blocked(tmp_path):
    storage = LocalFileStorage(str(tmp_path))
    with pytest.raises(ValueError, match="escapes storage root"):
        await storage.save("../../etc/evil", b"x")
