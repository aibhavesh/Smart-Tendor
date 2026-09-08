"""Human review & correction tests — the two split endpoints.

The point of the split is that a field can be corrected without a decision
being recorded, so most of what is asserted here is about what does *not*
happen: no verdict, no status change, no premature entry in the audit log.
"""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers

DOC = b"Name of Work: Road widening\nEstimated Cost: Rs. 50 lakh\nEMD: Rs. 1,00,000\n"


async def _parsed_tender(client, headers, number="T-REV") -> str:
    """Registered, uploaded and extracted — but not analysed."""
    tender = (
        await client.post(
            "/tenders", json={"tender_number": number, "title": "Road"}, headers=headers
        )
    ).json()
    tid = tender["id"]
    await client.post(
        f"/tenders/{tid}/documents/upload",
        files={"file": ("t.txt", DOC, "text/plain")},
        headers=headers,
    )
    await client.post(f"/tenders/{tid}/extract", headers=headers)
    return tid


async def _analyzed_tender(client, headers, number="T-REV") -> str:
    tid = await _parsed_tender(client, headers, number)
    await client.post(f"/tenders/{tid}/analyze", headers=headers)
    return tid


# --------------------------------------------------------------------------- #
# Corrections
# --------------------------------------------------------------------------- #
async def test_employee_can_correct_and_values_persist_verified(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, headers)

    before_meta = (await client.get(f"/tenders/{tid}/metadata", headers=headers)).json()
    old_value = before_meta["fields"]["estimated_value"]["value"]

    resp = await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "9999999", "closing_date": "2026-12-31"}},
        headers=headers,
    )
    assert resp.status_code == 201
    review = resp.json()
    assert review["before_snapshot"]["estimated_value"] == old_value
    assert review["after_snapshot"]["estimated_value"] == "9999999"
    assert review["after_snapshot"]["closing_date"] == "2026-12-31"

    meta = (await client.get(f"/tenders/{tid}/metadata", headers=headers)).json()
    assert meta["fields"]["estimated_value"]["value"] == "9999999"
    assert meta["fields"]["estimated_value"]["confidence"] == 1.0
    assert meta["fields"]["estimated_value"]["source"] == "review:correction"


async def test_correction_does_not_change_status(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, headers)

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "12345"}},
        headers=headers,
    )

    tender = await client.get(f"/tenders/{tid}", headers=headers)
    assert tender.json()["status"] == "ANALYZED"  # not REVIEWED


async def test_correction_record_has_kind_and_no_verdict(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, headers)

    resp = await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "12345"}},
        headers=headers,
    )
    body = resp.json()
    assert body["kind"] == "CORRECTION"
    assert body["verdict"] is None
    # A correction is not a decision, so it can never be "superseded".
    assert body["is_stale"] is False


async def test_empty_corrections_rejected(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, headers)
    resp = await client.post(
        f"/tenders/{tid}/corrections", json={"corrections": {}}, headers=headers
    )
    assert resp.status_code == 422


async def test_correction_writes_an_audit_diff(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, employee)
    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "9999999"}},
        headers=employee,
    )

    admin = await auth_headers(client, app_db, email="admin@example.com", role=UserRole.ADMIN)
    logs = await client.get(
        "/admin/audit-logs", params={"action": "tender.correction"}, headers=admin
    )
    assert logs.json()["total"] == 1
    entry = logs.json()["items"][0]
    assert entry["diff"]["estimated_value"]["after"] == "9999999"
    assert "verdict" not in entry["diff"]  # nothing was decided


async def test_manager_can_also_correct(client, app_db):
    headers = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, headers)
    resp = await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "12345"}},
        headers=headers,
    )
    assert resp.status_code == 201


async def test_correction_allowed_from_parsed(client, app_db):
    """Fixing the extraction before analysing is the normal order."""
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _parsed_tender(client, headers)
    assert (await client.get(f"/tenders/{tid}", headers=headers)).json()["status"] == "PARSED"

    resp = await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "12345"}},
        headers=headers,
    )
    assert resp.status_code == 201


async def test_correction_rejected_before_extraction(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tender = (
        await client.post(
            "/tenders", json={"tender_number": "T-RAW-C", "title": "X"}, headers=headers
        )
    ).json()
    resp = await client.post(
        f"/tenders/{tender['id']}/corrections",
        json={"corrections": {"estimated_value": "1"}},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_invalid_correction_field_rejected(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, headers)
    resp = await client.post(
        f"/tenders/{tid}/corrections", json={"corrections": {"not_a_field": "x"}}, headers=headers
    )
    assert resp.status_code == 422


async def test_invalid_decimal_correction_rejected(client, app_db):
    headers = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, headers)
    resp = await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "not-a-number"}},
        headers=headers,
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #
async def test_verdict_advances_to_reviewed(client, app_db):
    headers = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, headers)

    resp = await client.post(
        f"/tenders/{tid}/verdict",
        json={"verdict": "APPROVED", "comments": "Looks good"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "VERDICT"
    assert body["verdict"] == "APPROVED"
    assert body["comments"] == "Looks good"

    tender = await client.get(f"/tenders/{tid}", headers=headers)
    assert tender.json()["status"] == "REVIEWED"

    history = await client.get(f"/tenders/{tid}/reviews", headers=headers)
    assert len(history.json()) == 1


async def test_verdict_missing_is_rejected(client, app_db):
    headers = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, headers)
    resp = await client.post(f"/tenders/{tid}/verdict", json={"comments": "x"}, headers=headers)
    assert resp.status_code == 422


async def test_verdict_applies_corrections_before_transitioning(client, app_db):
    headers = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, headers)

    resp = await client.post(
        f"/tenders/{tid}/verdict",
        json={"verdict": "REJECTED", "corrections": {"estimated_value": "9999999"}},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["after_snapshot"]["estimated_value"] == "9999999"

    meta = (await client.get(f"/tenders/{tid}/metadata", headers=headers)).json()
    assert meta["fields"]["estimated_value"]["value"] == "9999999"
    assert (await client.get(f"/tenders/{tid}", headers=headers)).json()["status"] == "REVIEWED"


async def test_cannot_decide_an_unanalyzed_tender(client, app_db):
    headers = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _parsed_tender(client, headers, "T-RAW-V")
    resp = await client.post(
        f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=headers
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
async def test_employee_cannot_submit_verdict(client, app_db):
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, manager)
    employee = await auth_headers(client, app_db, email="a@example.com", role=UserRole.EMPLOYEE)
    resp = await client.post(
        f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=employee
    )
    assert resp.status_code == 403


async def test_admin_cannot_submit_verdict(client, app_db):
    """The verdict is an exact-role capability: outranking a MANAGER is not enough.

    ADMIN sits at level 40, above MANAGER's 30, so the ordinary inclusive gate
    would admit it. Bid approval belongs to the people accountable for the bid.
    """
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, manager)
    admin = await auth_headers(client, app_db, email="admin@example.com", role=UserRole.ADMIN)
    resp = await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=admin)
    assert resp.status_code == 403


async def test_super_admin_can_submit_verdict(client, app_db):
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, manager)
    root = await auth_headers(client, app_db, email="s@example.com", role=UserRole.SUPER_ADMIN)
    resp = await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=root)
    assert resp.status_code == 201


async def test_employee_can_view_pending_queue(client, app_db):
    # Seeing what awaits a decision is not the same as making one.
    employee = await auth_headers(client, app_db, email="a@example.com", role=UserRole.EMPLOYEE)
    assert (await client.get("/reviews/pending", headers=employee)).status_code == 200


# --------------------------------------------------------------------------- #
# The old welded endpoint is gone
# --------------------------------------------------------------------------- #
async def test_old_reviews_post_endpoint_is_removed(client, app_db):
    headers = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, headers)
    resp = await client.post(
        f"/tenders/{tid}/reviews", json={"verdict": "APPROVED"}, headers=headers
    )
    assert resp.status_code == 405  # GET still serves history; POST no longer exists


# --------------------------------------------------------------------------- #
# The pending queue — the silent failure mode
# --------------------------------------------------------------------------- #
async def test_queue_keeps_a_tender_that_has_only_a_correction(client, app_db):
    """A correction must not read as a review.

    If the queue predicate were "has no review row", a correction would drop the
    tender out of the queue and its closing date could pass with nobody having
    decided. Presence at the intermediate step is the assertion that matters.
    """
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    pending = await client.get("/reviews/pending", headers=employee)
    assert any(t["id"] == tid for t in pending.json()["items"])

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "9999999"}},
        headers=employee,
    )

    still = await client.get("/reviews/pending", headers=employee)
    assert any(t["id"] == tid for t in still.json()["items"]), (
        "a corrected tender must stay in the queue — nobody has decided on it yet"
    )

    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)

    after = await client.get("/reviews/pending", headers=employee)
    assert all(t["id"] != tid for t in after.json()["items"])


async def test_history_renders_both_kinds(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "9999999"}},
        headers=employee,
    )
    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)

    history = (await client.get(f"/tenders/{tid}/reviews", headers=employee)).json()
    assert {r["kind"] for r in history} == {"CORRECTION", "VERDICT"}
    correction = next(r for r in history if r["kind"] == "CORRECTION")
    verdict = next(r for r in history if r["kind"] == "VERDICT")
    assert correction["verdict"] is None
    assert verdict["verdict"] == "APPROVED"


async def test_platform_stats_counts_verdicts_only(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    admin = await auth_headers(client, app_db, email="admin@example.com", role=UserRole.ADMIN)
    tid = await _analyzed_tender(client, employee)

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "9999999"}},
        headers=employee,
    )

    stats = (await client.get("/admin/stats", headers=admin)).json()
    assert stats["reviews_total"] == 0, "a correction is not a review decision"
