"""Exercise the standalone serverless entrypoint without a database connection."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_vercel_exports_fastapi_and_preserves_native_and_legacy_routes():
    backend = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "ENVIRONMENT": "ci",
        "ENABLE_DOCUMENT_WORKER": "false",
        "WARM_EMBEDDINGS_ON_STARTUP": "false",
    }
    check = """
import asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from index import app, BACKEND_SRC
from pathlib import Path

assert isinstance(app, FastAPI)
assert Path(BACKEND_SRC) == Path.cwd() / 'src'

async def verify():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for path in ('/health', '/api/health'):
            response = await client.get(path)
            assert response.status_code == 200, response.text
            assert response.json()['status'] == 'ok'
        docs = await client.get('/api/docs')
        assert docs.status_code == 200
        assert '/api/openapi.json' in docs.text
        assert (await client.get('/api/openapi.json')).status_code == 200
        assert (await client.get('/apiculture/health')).status_code == 404

asyncio.run(verify())
"""
    result = subprocess.run(
        [sys.executable, "-c", check],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
