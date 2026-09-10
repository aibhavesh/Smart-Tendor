"""Phase 3 bulk-import and document API tests."""

from __future__ import annotations

import io

from openpyxl import Workbook

from tests.integration.helpers import auth_headers


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_bulk_import_reports_per_row_outcomes(client, app_db):
    headers = await auth_headers(client, app_db)
    # Pre-existing tender to force a SKIP.
    await client.post(
        "/tenders", json={"tender_number": "T-EXIST", "title": "Old"}, headers=headers
    )

    content = _xlsx(
        [
            ["tender_number", "title", "estimated_value", "closing_date"],
            ["T-NEW", "New road", 2500000, "2026-09-01"],
            ["T-EXIST", "Dup", None, None],  # skipped
            [None, "Missing number", None, None],  # error
        ]
    )
    resp = await client.post(
        "/tenders/import",
        files={
            "file": (
                "tenders.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 1
    assert body["errors"] == 1

    created = await client.get("/tenders", params={"search": "T-NEW"}, headers=headers)
    item = created.json()["items"][0]
    assert item["estimated_value"] == "2500000.00"  # money quantised to 2 dp
    assert item["closing_date"] == "2026-09-01"


async def test_add_document_from_url_creates_pending(client, app_db):
    headers = await auth_headers(client, app_db)
    tender = (
        await client.post("/tenders", json={"tender_number": "T-D", "title": "T"}, headers=headers)
    ).json()

    resp = await client.post(
        f"/tenders/{tender['id']}/documents",
        json={"source_url": "https://example.com/doc.pdf"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "PENDING"

    listing = await client.get(f"/tenders/{tender['id']}/documents", headers=headers)
    assert len(listing.json()) == 1


async def test_direct_upload_via_api(client, app_db):
    headers = await auth_headers(client, app_db)
    tender = (
        await client.post("/tenders", json={"tender_number": "T-U", "title": "T"}, headers=headers)
    ).json()

    resp = await client.post(
        f"/tenders/{tender['id']}/documents/upload",
        files={"file": ("boq.pdf", b"BYTES", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "DOWNLOADED"
    assert body["file_size"] == 5

    # Tender advanced to DOWNLOADED.
    refreshed = await client.get(f"/tenders/{tender['id']}", headers=headers)
    assert refreshed.json()["status"] == "DOWNLOADED"
