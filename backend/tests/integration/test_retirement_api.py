"""Bulk retirement of expired tenders, over HTTP.

The destructive half of the feature. These tests assert as much about what
survives as about what is destroyed, because the whole design rests on the
record outliving the artefact.
"""

from __future__ import annotations

from datetime import date

import pytest

from tender_intel.domain.entities import Tender, TenderDocument
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyTenderDocumentRepository,
    SqlAlchemyTenderRepository,
)

from .helpers import auth_headers

PREVIEW_URL = "/api/v1/tenders/retirement/preview"
RETIRE_URL = "/api/v1/tenders/retirement"

PAST = date(2020, 1, 1)
FUTURE = date(2099, 1, 1)


async def seed_tender(
    app,
    *,
    number: str,
    closing: date | None,
    status: TenderStatus = TenderStatus.PARSED,
    with_document: bool = True,
    file_size: int = 5_000_000,
) -> Tender:
    factory = app.state.test_session_factory
    async with factory() as session:
        tenders = SqlAlchemyTenderRepository(session)
        created = await tenders.add(
            Tender(tender_number=number, title=f"Work {number}", closing_date=closing)
        )
        created.status = status
        await tenders.update(created)
        if with_document:
            documents = SqlAlchemyTenderDocumentRepository(session)
            doc = TenderDocument(
                tender_id=created.id,
                file_name=f"{number}.pdf",
                file_path=f"tenders/{created.id}/{number}.pdf",
                file_size=file_size,
                mime_type="application/pdf",
                sha256="a" * 64,
                status=DocumentStatus.DOWNLOADED,
                raw_text="extracted text that must survive",
            )
            await documents.add(doc)
        await session.commit()
        return created


async def documents_for(app, tender_id):
    factory = app.state.test_session_factory
    async with factory() as session:
        return await SqlAlchemyTenderDocumentRepository(session).list_for_tender(tender_id)


async def tender_by_id(app, tender_id):
    factory = app.state.test_session_factory
    async with factory() as session:
        return await SqlAlchemyTenderRepository(session).get(tender_id)


async def retire_audits(app):
    factory = app.state.test_session_factory
    async with factory() as session:
        page = await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=200))
        return [a for a in page.items if a.action == "tender.bulk_retire"]


async def admin(client, app):
    return await auth_headers(client, app, email="admin@example.com", role=UserRole.ADMIN)


# --- preview writes nothing -----------------------------------------------


async def test_preview_selects_expired_tenders_and_changes_nothing(client, app_db):
    tender = await seed_tender(app_db, number="OLD-1", closing=PAST)
    headers = await admin(client, app_db)

    resp = await client.get(PREVIEW_URL, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["retirable_count"] == 1
    assert body["documents_to_purge"] == 1
    assert body["bytes_to_reclaim"] == 5_000_000

    # Nothing was touched.
    docs = await documents_for(app_db, tender.id)
    assert docs[0].file_path is not None
    assert docs[0].purged_at is None
    assert (await tender_by_id(app_db, tender.id)).status is TenderStatus.PARSED


async def test_preview_states_its_cutoff_and_timezone(client, app_db):
    headers = await admin(client, app_db)
    body = (await client.get(PREVIEW_URL, headers=headers)).json()
    assert body["cutoff"]
    assert body["timezone"] == "IST"


async def test_a_future_tender_is_not_selected(client, app_db):
    await seed_tender(app_db, number="FUT-1", closing=FUTURE)
    headers = await admin(client, app_db)
    body = (await client.get(PREVIEW_URL, headers=headers)).json()
    assert body["retirable_count"] == 0


async def test_an_explicit_cutoff_is_honoured(client, app_db):
    await seed_tender(app_db, number="MID-1", closing=date(2026, 6, 1))
    headers = await admin(client, app_db)

    before = (await client.get(f"{PREVIEW_URL}?cutoff=2026-01-01", headers=headers)).json()
    after = (await client.get(f"{PREVIEW_URL}?cutoff=2026-12-01", headers=headers)).json()
    assert before["retirable_count"] == 0
    assert after["retirable_count"] == 1


# --- the null closing date --------------------------------------------------


async def test_a_tender_with_no_closing_date_is_never_selected(client, app_db):
    """The hazard this feature has to get right."""
    tender = await seed_tender(app_db, number="NULL-1", closing=None)
    headers = await admin(client, app_db)

    body = (await client.get(PREVIEW_URL, headers=headers)).json()
    assert body["retirable_count"] == 0
    assert body["unknown_closing_date"] == 1
    assert all(c["tender_id"] != str(tender.id) for c in body["candidates"])

    await client.post(RETIRE_URL, headers=headers, json={})
    docs = await documents_for(app_db, tender.id)
    assert docs[0].file_path is not None
    assert (await tender_by_id(app_db, tender.id)).status is TenderStatus.PARSED


# --- execution: purge the artefact, keep the record ------------------------


async def test_retiring_purges_the_file_and_keeps_the_record(client, app_db):
    tender = await seed_tender(app_db, number="OLD-2", closing=PAST)
    headers = await admin(client, app_db)

    resp = await client.post(RETIRE_URL, headers=headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenders_archived"] == 1
    assert body["documents_purged"] == 1
    assert body["bytes_reclaimed"] == 5_000_000

    docs = await documents_for(app_db, tender.id)
    doc = docs[0]
    # The bytes are gone.
    assert doc.file_path is None
    assert doc.purged_at is not None
    # Everything that makes the document evidence survives.
    assert doc.sha256 == "a" * 64
    assert doc.file_name == "OLD-2.pdf"
    assert doc.file_size == 5_000_000
    assert doc.raw_text == "extracted text that must survive"
    # The status still says DOWNLOADED — it was downloaded, and rewriting that
    # would invite the worker to fetch it again.
    assert doc.status is DocumentStatus.DOWNLOADED


async def test_retiring_archives_the_tender(client, app_db):
    tender = await seed_tender(app_db, number="OLD-3", closing=PAST)
    headers = await admin(client, app_db)
    await client.post(RETIRE_URL, headers=headers, json={})
    assert (await tender_by_id(app_db, tender.id)).status is TenderStatus.ARCHIVED


async def test_the_tender_and_its_metadata_are_never_deleted(client, app_db):
    tender = await seed_tender(app_db, number="OLD-4", closing=PAST)
    headers = await admin(client, app_db)
    await client.post(RETIRE_URL, headers=headers, json={})

    still_there = await client.get(f"/tenders/{tender.id}", headers=headers)
    assert still_there.status_code == 200
    assert still_there.json()["tender_number"] == "OLD-4"


async def test_the_response_states_what_was_kept(client, app_db):
    await seed_tender(app_db, number="OLD-5", closing=PAST)
    headers = await admin(client, app_db)
    body = (await client.post(RETIRE_URL, headers=headers, json={})).json()
    assert "reviews" in body["retained"]
    assert "metadata" in body["retained"]


# --- the extraction bar -----------------------------------------------------


@pytest.mark.parametrize("status", [TenderStatus.REGISTERED, TenderStatus.DOWNLOADED])
async def test_an_unparsed_tender_keeps_its_file(client, app_db, status):
    """Its document may be the only copy of data never extracted."""
    tender = await seed_tender(app_db, number=f"RAW-{status.value}", closing=PAST, status=status)
    headers = await admin(client, app_db)

    preview = (await client.get(PREVIEW_URL, headers=headers)).json()
    assert preview["retirable_count"] == 0
    entry = next(c for c in preview["candidates"] if c["tender_id"] == str(tender.id))
    assert entry["skip_reason"] == "not_yet_parsed"

    await client.post(RETIRE_URL, headers=headers, json={})
    docs = await documents_for(app_db, tender.id)
    assert docs[0].file_path is not None


# --- selecting a subset -----------------------------------------------------


async def test_only_the_confirmed_subset_is_retired(client, app_db):
    keep = await seed_tender(app_db, number="OLD-6", closing=PAST)
    retire = await seed_tender(app_db, number="OLD-7", closing=PAST)
    headers = await admin(client, app_db)

    body = (
        await client.post(RETIRE_URL, headers=headers, json={"tender_ids": [str(retire.id)]})
    ).json()
    assert body["tenders_archived"] == 1

    assert (await documents_for(app_db, retire.id))[0].file_path is None
    assert (await documents_for(app_db, keep.id))[0].file_path is not None


async def test_an_id_outside_the_selection_is_ignored(client, app_db):
    """The selection rules are the authority, not the caller's list."""
    future = await seed_tender(app_db, number="FUT-2", closing=FUTURE)
    headers = await admin(client, app_db)

    body = (
        await client.post(RETIRE_URL, headers=headers, json={"tender_ids": [str(future.id)]})
    ).json()
    assert body["tenders_archived"] == 0
    assert (await documents_for(app_db, future.id))[0].file_path is not None


# --- idempotence ------------------------------------------------------------


async def test_running_twice_purges_nothing_the_second_time(client, app_db):
    await seed_tender(app_db, number="OLD-8", closing=PAST)
    headers = await admin(client, app_db)

    first = (await client.post(RETIRE_URL, headers=headers, json={})).json()
    second = (await client.post(RETIRE_URL, headers=headers, json={})).json()
    assert first["documents_purged"] == 1
    assert second["documents_purged"] == 0
    assert second["tenders_archived"] == 0


# --- access -----------------------------------------------------------------


async def test_anonymous_is_refused(client, app_db):
    assert (await client.get(PREVIEW_URL)).status_code == 401
    assert (await client.post(RETIRE_URL, json={})).status_code == 401


@pytest.mark.parametrize("role", [UserRole.EMPLOYEE, UserRole.MANAGER])
async def test_below_admin_is_refused(client, app_db, role):
    headers = await auth_headers(
        client, app_db, email=f"{role.value.lower()}@example.com", role=role
    )
    assert (await client.get(PREVIEW_URL, headers=headers)).status_code == 403
    assert (await client.post(RETIRE_URL, headers=headers, json={})).status_code == 403


async def test_super_admin_keeps_it(client, app_db):
    headers = await auth_headers(
        client, app_db, email="super@example.com", role=UserRole.SUPER_ADMIN
    )
    assert (await client.get(PREVIEW_URL, headers=headers)).status_code == 200


# --- audit ------------------------------------------------------------------


async def test_one_audit_entry_names_every_tender_and_what_was_done(client, app_db):
    retired = await seed_tender(app_db, number="OLD-9", closing=PAST)
    await seed_tender(app_db, number="RAW-9", closing=PAST, status=TenderStatus.REGISTERED)
    await seed_tender(app_db, number="NULL-9", closing=None)
    headers = await admin(client, app_db)

    await client.post(RETIRE_URL, headers=headers, json={})
    entries = await retire_audits(app_db)
    assert len(entries) == 1
    diff = entries[0].diff

    assert entries[0].actor_id is not None
    assert entries[0].ip_address is not None
    assert diff["actor_role"] == UserRole.ADMIN.value
    assert diff["timezone"] == "IST"
    assert diff["documents_purged"] == 1
    assert diff["unknown_closing_date_excluded"] == 1
    # The tenders it touched are named, not just counted.
    assert [t["tender_number"] for t in diff["tenders"]] == ["OLD-9"]
    assert str(retired.id) in [t["tender_id"] for t in diff["tenders"]]
    # And so is the one it deliberately passed over.
    assert {s["reason"] for s in diff["skipped"]} == {"not_yet_parsed"}
    assert "reviews" in diff["retained"]


async def test_a_preview_writes_no_audit_entry(client, app_db):
    await seed_tender(app_db, number="OLD-10", closing=PAST)
    headers = await admin(client, app_db)
    await client.get(PREVIEW_URL, headers=headers)
    assert await retire_audits(app_db) == []


# --- storage failure isolation ---------------------------------------------


async def test_a_file_storage_cannot_delete_leaves_the_row_untouched(client, app_db, monkeypatch):
    """A document marked purged whose bytes survive would hide the leak."""
    from tender_intel.infrastructure.storage import LocalFileStorage

    async def explode(self, relative_path: str) -> None:
        raise OSError("device busy")

    monkeypatch.setattr(LocalFileStorage, "delete", explode)

    tender = await seed_tender(app_db, number="OLD-11", closing=PAST)
    headers = await admin(client, app_db)
    body = (await client.post(RETIRE_URL, headers=headers, json={})).json()

    assert body["documents_purged"] == 0
    assert len(body["failures"]) == 1
    docs = await documents_for(app_db, tender.id)
    assert docs[0].file_path is not None
    assert docs[0].purged_at is None


async def test_a_tender_with_no_documents_still_archives(client, app_db):
    tender = await seed_tender(app_db, number="OLD-12", closing=PAST, with_document=False)
    headers = await admin(client, app_db)
    body = (await client.post(RETIRE_URL, headers=headers, json={})).json()
    assert body["tenders_archived"] == 1
    assert body["documents_purged"] == 0
    assert (await tender_by_id(app_db, tender.id)).status is TenderStatus.ARCHIVED
