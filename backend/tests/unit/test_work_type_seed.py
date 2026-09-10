"""Work-type seed parsing and validation (feature spec §6).

The fixtures below mirror the real seed's shape and its known hazards — the
hyphenated Wi-Fi pair, and the NTPC reference that carries an embedded newline
and a trailing space — so the loader is exercised against them before the real
file exists.
"""

from __future__ import annotations

import pytest

from tender_intel.domain.enums.work_type import AliasKind, WorkTypeCategory
from tender_intel.infrastructure.seed.work_type_seed import (
    SeedValidationError,
    parse_seed,
)


def work_type(code="OFC_CABLE_SUPPLY", *, aliases=None, projects=None, **overrides) -> dict:
    # The default alias is derived from the code so two fixtures never collide by
    # accident — a collision in a test should be one the test asked for.
    entry = {
        "code": code,
        "name": "Optical fibre cable supply",
        "category": "TELECOM_NETWORKING",
        "description": "Supply and installation of optical fibre cable.",
        "aliases": (
            aliases
            if aliases is not None
            else [{"alias": code.lower().replace("_", " "), "kind": "SYNONYM"}]
        ),
        "projects": projects if projects is not None else ["TELE 22"],
    }
    entry.update(overrides)
    return entry


def payload(*entries) -> dict:
    return {
        "version": "1.0",
        "source": "7_YEAR_PROJECT_DETAILS.xlsx",
        "work_types": list(entries) or [work_type()],
    }


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_parses_a_well_formed_seed():
    seed = parse_seed(payload(work_type(aliases=[{"alias": "OFC", "kind": "ABBREVIATION"}])))
    assert seed.version == "1.0"
    assert len(seed.work_types) == 1
    parsed = seed.work_types[0]
    assert parsed.code == "OFC_CABLE_SUPPLY"
    assert parsed.category is WorkTypeCategory.TELECOM_NETWORKING
    assert parsed.aliases[0].kind is AliasKind.ABBREVIATION
    assert parsed.aliases[0].normalised == "ofc"


def test_counts_across_the_whole_seed():
    seed = parse_seed(
        payload(
            work_type(aliases=[{"alias": "OFC", "kind": "ABBREVIATION"}], projects=["A", "B"]),
            work_type(
                "QUAD_CABLE",
                aliases=[
                    {"alias": "quad", "kind": "VARIANT"},
                    {"alias": "6 quad", "kind": "VARIANT"},
                ],
                projects=["B"],
            ),
        )
    )
    assert seed.alias_count == 3
    assert seed.link_count == 3
    assert seed.distinct_project_refs == ("A", "B")


def test_a_missing_description_is_allowed():
    entry = work_type()
    del entry["description"]
    assert parse_seed(payload(entry)).work_types[0].description is None


def test_project_references_keep_their_raw_form():
    # The workbook's newlines and trailing spaces survive parsing; they are
    # absorbed at reconciliation, not here, so a report can show the source.
    seed = parse_seed(payload(work_type(projects=["NTPC\nVindhyachal "])))
    assert seed.work_types[0].project_refs == ("NTPC\nVindhyachal ",)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_a_duplicate_code_is_refused_and_names_both():
    with pytest.raises(SeedValidationError) as exc:
        parse_seed(payload(work_type(), work_type()))
    assert any("duplicate code" in p for p in exc.value.problems)


def test_a_globally_colliding_alias_names_both_work_types():
    with pytest.raises(SeedValidationError) as exc:
        parse_seed(
            payload(
                work_type("OFC_CABLE_SUPPLY", aliases=[{"alias": "cable", "kind": "SYNONYM"}]),
                work_type("PIJF_CABLE", aliases=[{"alias": "CABLE", "kind": "SYNONYM"}]),
            )
        )
    problem = next(p for p in exc.value.problems if "globally unique" in p)
    assert "OFC_CABLE_SUPPLY" in problem
    assert "PIJF_CABLE" in problem


def test_the_hyphenated_wifi_pair_does_not_collide():
    # Both belong to one work type. A normaliser that stripped the hyphen would
    # collapse them and fail this load.
    seed = parse_seed(
        payload(
            work_type(
                "WIFI_PROVISION",
                aliases=[
                    {"alias": "wi-fi", "kind": "VARIANT"},
                    {"alias": "wifi", "kind": "VARIANT"},
                ],
            )
        )
    )
    assert seed.alias_count == 2


def test_every_problem_is_reported_not_just_the_first():
    with pytest.raises(SeedValidationError) as exc:
        parse_seed(
            payload(
                work_type("A", category="NOT_A_CATEGORY"),
                work_type("B", aliases=[{"alias": "x", "kind": "NOT_A_KIND"}]),
                work_type("C", name=""),
            )
        )
    assert len(exc.value.problems) >= 3


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"work_types": []},
        {"work_types": "not a list"},
        [],
        "not an object",
    ],
)
def test_a_malformed_payload_is_refused(bad):
    with pytest.raises(SeedValidationError):
        parse_seed(bad)


def test_a_blank_alias_is_refused():
    with pytest.raises(SeedValidationError) as exc:
        parse_seed(payload(work_type(aliases=[{"alias": "   ", "kind": "SYNONYM"}])))
    assert any("blank" in p for p in exc.value.problems)


def test_a_work_type_without_a_code_is_refused():
    entry = work_type()
    del entry["code"]
    with pytest.raises(SeedValidationError) as exc:
        parse_seed(payload(entry))
    assert any("has no code" in p for p in exc.value.problems)


# --------------------------------------------------------------------------- #
# Normalisation collisions — detected, not silently absorbed
# --------------------------------------------------------------------------- #
def test_the_ntpc_collision_is_detected():
    seed = parse_seed(
        payload(
            work_type("LAN_REVAMP", projects=["NTPC Vindhyachal"]),
            work_type("CONFERENCE_HALL_FITOUT", projects=["NTPC\nVindhyachal "]),
        )
    )
    collisions = seed.normalisation_collisions()
    assert "ntpc vindhyachal" in collisions
    assert set(collisions["ntpc vindhyachal"]) == {"NTPC Vindhyachal", "NTPC\nVindhyachal "}


def test_distinct_references_do_not_collide():
    seed = parse_seed(payload(work_type(projects=["TELE 22", "TELE 24"])))
    assert seed.normalisation_collisions() == {}


def test_the_same_reference_used_twice_is_not_a_collision():
    # One reference across two work types is normal: a project can evidence more
    # than one capability.
    seed = parse_seed(
        payload(work_type("A", projects=["Mumbai"]), work_type("B", projects=["Mumbai"]))
    )
    assert seed.normalisation_collisions() == {}
    assert seed.distinct_project_refs == ("Mumbai",)
