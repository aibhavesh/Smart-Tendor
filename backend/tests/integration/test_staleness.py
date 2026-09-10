"""Correct → re-analyse → decide, and the staleness flag that guards it.

Recommendations on this platform are never stored — every read recomputes them
from live metadata — so a recommendation cannot go stale. What can is a
*recorded verdict*: a decision on file whose evidence has since been corrected.
That is what ``verdict_is_stale`` reports, and what these tests pin down.
"""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers

DOC = b"Name of Work: Road widening\nEstimated Cost: Rs. 50 lakh\nEMD: Rs. 1,00,000\n"


async def _analyzed_tender(client, headers, number="T-STALE") -> str:
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
    await client.post(f"/tenders/{tid}/analyze", headers=headers)
    return tid


async def _recommendation(client, headers, tid) -> dict:
    return (await client.get(f"/tenders/{tid}/recommendation", headers=headers)).json()


# --------------------------------------------------------------------------- #
# The sequence the split exists to make possible
# --------------------------------------------------------------------------- #
async def test_correct_then_reanalyse_then_decide(client, app_db):
    """The point of the task, end to end.

    The correction is recorded by an employee, the recommendation is recomputed
    from the corrected data, and only then does a manager decide — so the
    verdict in the audit log rests on evidence that existed when it was cast.
    """
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    admin = await auth_headers(client, app_db, email="admin@example.com", role=UserRole.ADMIN)
    tid = await _analyzed_tender(client, employee)

    # 1. Correct — no decision is recorded.
    correction = await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "80000000"}},
        headers=employee,
    )
    assert correction.status_code == 201
    assert (await client.get(f"/tenders/{tid}", headers=employee)).json()["status"] == "ANALYZED"

    # 2. Re-analyse — the engines read the corrected value.
    reanalysed = await client.post(f"/tenders/{tid}/analyze", headers=employee)
    assert reanalysed.status_code == 200
    meta = (await client.get(f"/tenders/{tid}/metadata", headers=employee)).json()
    assert meta["fields"]["estimated_value"]["value"] == "80000000"

    # 3. Only now decide.
    verdict = await client.post(
        f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager
    )
    assert verdict.status_code == 201

    # The audit trail shows the correction strictly before the verdict, by
    # different people.
    logs = (
        await client.get(
            "/admin/audit-logs", params={"entity_type": "Tender", "limit": 100}, headers=admin
        )
    ).json()["items"]
    correction_entry = next(e for e in logs if e["action"] == "tender.correction")
    verdict_entry = next(e for e in logs if e["action"] == "tender.review")
    assert correction_entry["created_at"] <= verdict_entry["created_at"]
    assert correction_entry["actor_id"] != verdict_entry["actor_id"]


# --------------------------------------------------------------------------- #
# Staleness
# --------------------------------------------------------------------------- #
async def test_verdict_then_correction_is_stale(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)
    assert (await _recommendation(client, employee, tid))["verdict_is_stale"] is False

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "80000000"}},
        headers=employee,
    )

    assert (await _recommendation(client, employee, tid))["verdict_is_stale"] is True

    history = (await client.get(f"/tenders/{tid}/reviews", headers=employee)).json()
    verdict_row = next(r for r in history if r["kind"] == "VERDICT")
    assert verdict_row["is_stale"] is True


async def test_verdict_after_the_correction_is_not_stale(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "80000000"}},
        headers=employee,
    )
    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)

    assert (await _recommendation(client, employee, tid))["verdict_is_stale"] is False


async def test_verdict_carrying_corrections_does_not_flag_itself(client, app_db):
    """Corrections are applied before the record is written, so it cannot self-stale."""
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, manager)

    await client.post(
        f"/tenders/{tid}/verdict",
        json={"verdict": "APPROVED", "corrections": {"estimated_value": "80000000"}},
        headers=manager,
    )

    assert (await _recommendation(client, manager, tid))["verdict_is_stale"] is False


async def test_no_verdict_is_never_stale(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    tid = await _analyzed_tender(client, employee)

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "80000000"}},
        headers=employee,
    )

    # Nothing has been decided, so there is nothing to supersede.
    assert (await _recommendation(client, employee, tid))["verdict_is_stale"] is False


async def test_stale_recommendation_payload_is_unchanged(client, app_db):
    """The flag is additive. Nothing is suppressed, altered or withheld.

    A manager may still need to read the recommendation in order to judge
    whether the correction actually changes anything.
    """
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, manager)

    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)
    before = await _recommendation(client, manager, tid)

    # Correct a field the engines do not read, so the recommendation itself
    # cannot move and any difference must come from the flag alone.
    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"location": "Indore"}},
        headers=manager,
    )
    after = await _recommendation(client, manager, tid)

    assert after["verdict_is_stale"] is True
    assert before["verdict_is_stale"] is False
    assert after["recommendation"] == before["recommendation"]
    assert after["risk"] == before["risk"]
    assert after["qualification"] == before["qualification"]


async def test_analyst_report_carries_the_same_flag(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)
    fresh = (await client.get(f"/tenders/{tid}/report", headers=employee)).json()
    assert fresh["verdict_is_stale"] is False

    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "80000000"}},
        headers=employee,
    )

    stale = (await client.get(f"/tenders/{tid}/report", headers=employee)).json()
    assert stale["verdict_is_stale"] is True
    assert stale["sections"]  # prose still returned in full


async def test_analyze_response_carries_the_flag(client, app_db):
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)
    await client.post(
        f"/tenders/{tid}/corrections",
        json={"corrections": {"estimated_value": "80000000"}},
        headers=employee,
    )

    reanalysed = await client.post(f"/tenders/{tid}/analyze", headers=employee)
    assert reanalysed.json()["verdict_is_stale"] is True


# --------------------------------------------------------------------------- #
# The misleading combination, named
# --------------------------------------------------------------------------- #
async def test_confidence_rises_while_the_verdict_goes_stale(client, app_db):
    """Confidence inverts against trustworthiness — §13.5 caps the score by the
    mean extraction confidence of tender value, EMD and completion period, and
    corrections write back at 1.0. So the number *rises* at the very moment the
    recorded decision stops being reliable. Both halves are asserted together
    because it is the combination that misleads.
    """
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    manager = await auth_headers(client, app_db, email="m@example.com", role=UserRole.MANAGER)
    tid = await _analyzed_tender(client, employee)

    await client.post(f"/tenders/{tid}/verdict", json={"verdict": "APPROVED"}, headers=manager)
    before = await _recommendation(client, employee, tid)
    confidence_before = before["recommendation"]["confidence"]
    assert before["verdict_is_stale"] is False

    # Correct all three fields the confidence cap reads, each to confidence 1.0.
    await client.post(
        f"/tenders/{tid}/corrections",
        json={
            "corrections": {
                "estimated_value": "80000000",
                "emd_amount": "1600000",
                "completion_period": "12 months",
            }
        },
        headers=employee,
    )

    after = await _recommendation(client, employee, tid)
    assert after["recommendation"]["confidence"] > confidence_before, (
        "corrections write back at 1.0, so the §13.5 cap must rise"
    )
    assert after["verdict_is_stale"] is True, (
        "and the recorded verdict is now superseded — the rising number is the trap"
    )
