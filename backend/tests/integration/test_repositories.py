"""Phase 1 repository round-trips against SQLite, exercising the mappers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tender_intel.domain.entities import (
    BOQItem,
    PastProject,
    Tender,
    TenderMetadata,
    User,
)
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.domain.value_objects.unknown import UNKNOWN, is_known
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyBOQItemRepository,
    SqlAlchemyTenderMetadataRepository,
    SqlAlchemyTenderRepository,
)
from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository


async def test_user_roundtrip_and_email_lookup(session):
    repo = SqlAlchemyUserRepository(session)
    created = await repo.add(
        User(email="Alice@Example.com", full_name="Alice", role=UserRole.EMPLOYEE)
    )
    assert created.created_at is not None

    fetched = await repo.get_by_email("alice@example.com")  # case-insensitive
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.role is UserRole.EMPLOYEE


async def test_tender_decimal_and_pagination(session):
    repo = SqlAlchemyTenderRepository(session)
    await repo.add(
        Tender(
            tender_number="T-100",
            title="Bridge construction",
            estimated_value=Decimal("15000000.50"),
            closing_date=date(2026, 9, 1),
        )
    )
    assert await repo.exists_number("T-100")
    assert not await repo.exists_number("T-999")

    fetched = await repo.get_by_number("T-100")
    assert fetched is not None
    # Exact decimal preserved through the DB round-trip.
    assert fetched.estimated_value == Decimal("15000000.50")

    page = await repo.list(PageRequest(limit=10), search="bridge")
    assert page.total == 1
    assert page.items[0].tender_number == "T-100"


async def test_metadata_extracted_fields_roundtrip(session):
    tender_repo = SqlAlchemyTenderRepository(session)
    tender = await tender_repo.add(Tender(tender_number="T-200", title="Road"))

    meta_repo = SqlAlchemyTenderMetadataRepository(session)
    metadata = TenderMetadata(
        tender_id=tender.id,
        work_name=ExtractedField.known("Road widening", 0.95, source="rule"),
        emd_amount=ExtractedField.known(Decimal("250000.00"), 0.80),
        closing_date=ExtractedField.known(date(2026, 10, 15), 0.70),
        raw_text="raw tender text",
    )
    await meta_repo.upsert(metadata)

    loaded = await meta_repo.get_for_tender(tender.id)
    assert loaded is not None
    assert loaded.work_name.value == "Road widening"
    assert loaded.work_name.confidence == 0.95
    assert loaded.emd_amount.value == Decimal("250000.00")  # exact decimal
    assert loaded.closing_date.value == date(2026, 10, 15)
    # Untouched fields stay UNKNOWN, never guessed.
    assert not loaded.location.is_known
    assert loaded.known_field_count == 3


async def test_boq_unknown_maps_to_null(session):
    tender_repo = SqlAlchemyTenderRepository(session)
    tender = await tender_repo.add(Tender(tender_number="T-300", title="Drain"))

    boq_repo = SqlAlchemyBOQItemRepository(session)
    await boq_repo.add_many(
        [
            BOQItem(
                tender_id=tender.id,
                description="Excavation",
                quantity=Decimal("120.5000"),
                unit_rate=Decimal("85.0000"),
                amount=UNKNOWN,  # not computed -> stays UNKNOWN
                confidence=0.6,
            )
        ]
    )
    items = await boq_repo.list_for_tender(tender.id)
    assert len(items) == 1
    assert items[0].quantity == Decimal("120.5000")
    assert not is_known(items[0].amount)


async def test_past_project_min_work_value_filter(session):
    repo = SqlAlchemyPastProjectRepository(session)
    await repo.add(PastProject(name="Small road", work_value=Decimal("5000000")))
    await repo.add(PastProject(name="Big highway", work_value=Decimal("50000000")))

    eligible = await repo.list_by_min_work_value(Decimal("10000000"))
    assert [p.name for p in eligible] == ["Big highway"]
