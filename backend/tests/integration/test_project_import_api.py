"""Bulk past-project import over HTTP.

Covers the three things the feature exists to get right: many files in one
operation, a failed file that does not abort the batch, and imported projects
that are actually visible to the eligibility engine's stage B rather than
silently inert.
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from openpyxl import Workbook

from tender_intel.domain.entities import WorkType, WorkTypeAlias
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.work_type import AliasKind, WorkTypeCategory, WorkTypeLinkSource
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.work_type_repo import SqlAlchemyWorkTypeRepository

from .helpers import auth_headers

IMPORT_URL = "/api/v1/projects/import"


def workbook_bytes(rows: list[dict]) -> bytes:
    """Build an xlsx shaped like the portfolio workbook."""
    wb = Workbook()
    sheet = wb.active
    sheet.append(
        ["Name of Work", "Client", "Order Value", "LOA No", "Completion Certificate", "Location"]
    )
    for row in rows:
        sheet.append(
            [
                row.get("name"),
                row.get("client"),
                row.get("value"),
                row.get("loa"),
                row.get("certificate"),
                row.get("location"),
            ]
        )
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def seed_work_type(app, *, code: str, name: str, alias: str) -> WorkType:
    factory = app.state.test_session_factory
    async with factory() as session:
        repo = SqlAlchemyWorkTypeRepository(session)
        created = await repo.add(
            WorkType(
                code=code,
                name=name,
                category=WorkTypeCategory.TELECOM_NETWORKING,
                description=name,
            )
        )
        await repo.add_alias(
            WorkTypeAlias(work_type_id=created.id, alias=alias, kind=AliasKind.SYNONYM)
        )
        await session.commit()
        return created


async def list_tags(app):
    factory = app.state.test_session_factory
    async with factory() as session:
        return await SqlAlchemyWorkTypeRepository(session).list_tags()


async def audit_actions(app, action: str):
    factory = app.state.test_session_factory
    async with factory() as session:
        page = await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=100))
        return [a for a in page.items if a.action == action]


# --- the happy path -------------------------------------------------------


async def test_a_workbook_imports_every_row(client, app_db):
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [
            {"name": "OFC laying Mumbai", "value": "1.13CR", "certificate": "2024-03-31"},
            {"name": "OFC laying Surat", "value": "2.91CR", "certificate": "2023-06-30"},
        ]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("portfolio.xlsx", content, "application/vnd.ms-excel")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["errors"] == 0
    assert len(body["files"]) == 1
    assert body["files"][0]["created"] == 2


async def test_money_survives_the_import_exactly(client, app_db):
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [{"name": "OFC laying", "value": "1,13,00,000", "certificate": "2024-03-31"}]
    )
    await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    listed = await client.get("/projects", headers=headers)
    # Serialised as a string by the Decimal-safe encoder, never as a float.
    assert listed.json()["items"][0]["work_value"] == "11300000.00"


async def test_many_files_in_one_operation(client, app_db):
    headers = await auth_headers(client, app_db)
    first = workbook_bytes([{"name": "Alpha", "value": "100", "certificate": "2024-01-01"}])
    second = workbook_bytes([{"name": "Beta", "value": "200", "certificate": "2024-01-02"}])
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files=[
            ("files", ("one.xlsx", first, "application/vnd.ms-excel")),
            ("files", ("two.xlsx", second, "application/vnd.ms-excel")),
        ],
    )
    body = resp.json()
    assert body["created"] == 2
    assert [f["filename"] for f in body["files"]] == ["one.xlsx", "two.xlsx"]


# --- failure isolation ----------------------------------------------------


async def test_a_corrupt_file_does_not_abort_the_batch(client, app_db):
    headers = await auth_headers(client, app_db)
    good = workbook_bytes([{"name": "Alpha", "value": "100", "certificate": "2024-01-01"}])
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files=[
            ("files", ("broken.xlsx", b"not a workbook at all", "application/vnd.ms-excel")),
            ("files", ("good.xlsx", good, "application/vnd.ms-excel")),
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["files_failed"] == 1
    assert body["created"] == 1
    broken, good_result = body["files"]
    assert broken["outcome"] == "error"
    assert broken["message"]
    assert good_result["created"] == 1


async def test_an_unsupported_extension_is_reported_not_raised(client, app_db):
    headers = await auth_headers(client, app_db)
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["files"][0]["outcome"] == "error"
    assert "unsupported file type" in resp.json()["files"][0]["message"]


async def test_a_row_without_a_name_fails_alone(client, app_db):
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [
            {"name": None, "value": "100", "certificate": "2024-01-01"},
            {"name": "Beta", "value": "200", "certificate": "2024-01-02"},
        ]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    body = resp.json()
    assert body["created"] == 1
    assert body["errors"] == 1
    rows = body["files"][0]["rows"]
    assert rows[0]["outcome"] == "error"
    assert rows[0]["message"] == "name is required"


# --- the silent-inertness problem this feature exists to prevent ----------


async def test_an_imported_project_is_linked_to_a_matching_work_type(client, app_db):
    await seed_work_type(
        app_db, code="OFC_LAYING", name="Optical fibre cable laying", alias="ofc laying"
    )
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [{"name": "OFC laying", "value": "1.13CR", "certificate": "2024-03-31"}]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    row = resp.json()["files"][0]["rows"][0]
    assert row["work_types_linked"] == 1
    assert row["eligibility_visible"] is True
    assert row["missing_for_eligibility"] == []

    tags = await list_tags(app_db)
    assert len(tags) == 1
    # Derived evidence must stay distinguishable from curated evidence.
    assert tags[0].source is WorkTypeLinkSource.INFERRED


async def test_a_project_with_no_matching_work_type_is_reported_invisible(client, app_db):
    await seed_work_type(app_db, code="AV_ROOM", name="Audio visual room", alias="av room")
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [{"name": "Bridge girder launching", "value": "500", "certificate": "2024-03-31"}]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    row = resp.json()["files"][0]["rows"][0]
    assert row["work_types_linked"] == 0
    assert row["eligibility_visible"] is False
    assert "work_type_link" in row["missing_for_eligibility"]


async def test_running_leaves_a_project_invisible_and_says_why(client, app_db):
    await seed_work_type(
        app_db, code="OFC_LAYING", name="Optical fibre cable laying", alias="ofc laying"
    )
    headers = await auth_headers(client, app_db)
    content = workbook_bytes([{"name": "OFC laying", "value": "1.13CR", "certificate": "Running"}])
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    row = resp.json()["files"][0]["rows"][0]
    assert row["eligibility_visible"] is False
    assert row["missing_for_eligibility"] == ["completion_certificate_date"]

    listed = await client.get("/projects", headers=headers)
    # The reason the work is not yet evidence survives the import verbatim.
    assert listed.json()["items"][0]["completion_certificate_note"] == "Running"


async def test_an_ambiguous_amount_leaves_the_project_invisible(client, app_db):
    headers = await auth_headers(client, app_db)
    content = workbook_bytes([{"name": "Delhi OFC", "value": "76LC", "certificate": "2024-03-31"}])
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    row = resp.json()["files"][0]["rows"][0]
    assert "work_value" in row["missing_for_eligibility"]


async def test_auto_tag_can_be_turned_off(client, app_db):
    await seed_work_type(
        app_db, code="OFC_LAYING", name="Optical fibre cable laying", alias="ofc laying"
    )
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [{"name": "OFC laying", "value": "1.13CR", "certificate": "2024-03-31"}]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        data={"auto_tag": "false"},
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    row = resp.json()["files"][0]["rows"][0]
    assert row["work_types_linked"] == 0
    assert row["eligibility_visible"] is False
    assert await list_tags(app_db) == []


# --- dirty data end to end ------------------------------------------------


async def test_an_loa_reference_with_an_embedded_newline_is_stored_cleaned(client, app_db):
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [
            {
                "name": "NTPC work",
                "value": "100",
                "loa": "NTPC\nVindhyachal ",
                "certificate": "2024-03-31",
            }
        ]
    )
    await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    listed = await client.get("/projects", headers=headers)
    assert listed.json()["items"][0]["loa_reference"] == "NTPC Vindhyachal"


async def test_a_real_date_cell_imports(client, app_db):
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [{"name": "Dated work", "value": "100", "certificate": date(2024, 3, 31)}]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    assert resp.json()["created"] == 1
    listed = await client.get("/projects", headers=headers)
    assert listed.json()["items"][0]["completion_certificate_date"] == "2024-03-31"


# --- access and audit -----------------------------------------------------


async def test_anonymous_is_refused(client, app_db):
    resp = await client.post(
        IMPORT_URL, files={"files": ("p.xlsx", workbook_bytes([]), "application/vnd.ms-excel")}
    )
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "role", [UserRole.EMPLOYEE, UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN]
)
async def test_every_role_at_employee_and_above_may_import(client, app_db, role):
    headers = await auth_headers(
        client, app_db, email=f"{role.value.lower()}@example.com", role=role
    )
    content = workbook_bytes([{"name": "Alpha", "value": "100", "certificate": "2024-01-01"}])
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    assert resp.status_code == 200


async def test_the_batch_writes_one_audit_entry_naming_every_file(client, app_db):
    headers = await auth_headers(client, app_db)
    good = workbook_bytes([{"name": "Alpha", "value": "100", "certificate": "2024-01-01"}])
    await client.post(
        IMPORT_URL,
        headers=headers,
        files=[
            ("files", ("one.xlsx", good, "application/vnd.ms-excel")),
            ("files", ("bad.txt", b"x", "text/plain")),
        ],
    )
    entries = await audit_actions(app_db, "past_project.bulk_import")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.actor_id is not None
    assert entry.diff["actor_role"] == UserRole.EMPLOYEE.value
    assert entry.diff["created"] == 1
    assert entry.diff["files_failed"] == 1
    assert [f["filename"] for f in entry.diff["files"]] == ["one.xlsx", "bad.txt"]


async def test_a_repeated_loa_reference_is_skipped_not_an_error(client, app_db):
    """The real workbook names one LOA under several work types.

    A duplicate must be SKIPPED, matching the tender import's handling of a
    tender number it already holds. It must also not be allowed to reach the
    unique index: a failed INSERT leaves the session needing a rollback, which
    would take every later row of the workbook with it.
    """
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [
            {"name": "First award", "value": "100", "loa": "TELE 22", "certificate": "2024-01-01"},
            {"name": "Same award", "value": "200", "loa": "TELE 22", "certificate": "2024-02-02"},
            {"name": "Later row", "value": "300", "loa": "TELE 24", "certificate": "2024-03-03"},
        ]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped"] == 1
    assert body["errors"] == 0

    rows = body["files"][0]["rows"]
    assert rows[1]["outcome"] == "skipped"
    assert "already imported" in rows[1]["message"]
    # The row after the duplicate still succeeded — the session was never poisoned.
    assert rows[2]["outcome"] == "created"


async def test_the_two_ntpc_spellings_collide_on_one_reference(client, app_db):
    """The dirty pair from the real seed must not create two projects."""
    headers = await auth_headers(client, app_db)
    content = workbook_bytes(
        [
            {
                "name": "NTPC one",
                "value": "100",
                "loa": "NTPC Vindhyachal",
                "certificate": "2024-01-01",
            },
            {
                "name": "NTPC two",
                "value": "200",
                "loa": "NTPC\nVindhyachal ",
                "certificate": "2024-02-02",
            },
        ]
    )
    resp = await client.post(
        IMPORT_URL,
        headers=headers,
        files={"files": ("p.xlsx", content, "application/vnd.ms-excel")},
    )
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 1
