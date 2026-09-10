"""Parse and validate the work-type seed file (feature spec §6).

Pure: it turns a decoded JSON payload into typed records, or refuses it. Nothing
here reaches a database, so the whole file can be checked before a single row is
written.

Validation reports **every** problem it finds rather than the first, because a
seed file is fixed in one editing pass and being told about one collision at a
time turns that into ten runs.

The global alias-uniqueness check is the important one. Two work types behind a
single normalised alias would make stage 1 of the match cascade
non-deterministic, so a collision fails the load and names both sides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tender_intel.domain.decision.normalise import normalise_alias
from tender_intel.domain.enums.work_type import AliasKind, WorkTypeCategory
from tender_intel.domain.exceptions import DomainValidationError


class SeedValidationError(DomainValidationError):
    """The seed file is not loadable. Carries every problem found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n  - ".join(problems)
        super().__init__(f"work-type seed is invalid ({len(problems)} problem(s)):\n  - {joined}")


@dataclass(frozen=True, slots=True)
class SeedAlias:
    alias: str
    kind: AliasKind
    normalised: str


@dataclass(frozen=True, slots=True)
class SeedWorkType:
    code: str
    name: str
    category: WorkTypeCategory
    description: str | None
    aliases: tuple[SeedAlias, ...]
    #: LOA references verbatim from the workbook, newlines and trailing spaces
    #: included. Normalisation happens at reconciliation, not here, so the
    #: source string stays visible in any report.
    project_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkTypeSeed:
    version: str
    source: str
    work_types: tuple[SeedWorkType, ...]

    @property
    def alias_count(self) -> int:
        return sum(len(w.aliases) for w in self.work_types)

    @property
    def link_count(self) -> int:
        return sum(len(w.project_refs) for w in self.work_types)

    @property
    def distinct_project_refs(self) -> tuple[str, ...]:
        """Every referenced project, deduplicated on the raw string.

        Deliberately *not* deduplicated on the normalised form: two raw strings
        that collapse to one key is a defect the caller needs to see, not one to
        silently absorb.
        """
        seen: dict[str, None] = {}
        for work_type in self.work_types:
            for ref in work_type.project_refs:
                seen.setdefault(ref, None)
        return tuple(seen)

    def normalisation_collisions(self) -> dict[str, list[str]]:
        """Distinct raw references that normalise to the same key.

        ``NTPC Vindhyachal`` and ``NTPC\\nVindhyachal `` are the known instance.
        Either they name one project, in which case the count of distinct
        projects is wrong, or they name two and the discriminator is lost.
        """
        by_key: dict[str, list[str]] = {}
        for ref in self.distinct_project_refs:
            by_key.setdefault(normalise_alias(ref), []).append(ref)
        return {key: refs for key, refs in by_key.items() if len(refs) > 1}


def load_seed_file(path: Path) -> WorkTypeSeed:
    """Read and validate the seed file at ``path``."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SeedValidationError([f"seed file not found: {path}"]) from exc
    except json.JSONDecodeError as exc:
        raise SeedValidationError([f"seed file is not valid JSON: {exc}"]) from exc
    return parse_seed(payload)


def parse_seed(payload: Any) -> WorkTypeSeed:
    """Validate a decoded payload, raising with every problem at once."""
    problems: list[str] = []

    if not isinstance(payload, dict):
        raise SeedValidationError(["seed payload is not a JSON object"])
    raw_types = payload.get("work_types")
    if not isinstance(raw_types, list) or not raw_types:
        raise SeedValidationError(["seed payload has no 'work_types' array"])

    work_types: list[SeedWorkType] = []
    seen_codes: dict[str, int] = {}
    alias_owners: dict[str, list[str]] = {}

    for index, entry in enumerate(raw_types):
        label = f"work_types[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{label} is not an object")
            continue

        code = str(entry.get("code") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not code:
            problems.append(f"{label} has no code")
            continue
        label = f"{code}"
        if not name:
            problems.append(f"{label}: has no name")

        if code in seen_codes:
            problems.append(f"{label}: duplicate code (also at work_types[{seen_codes[code]}])")
        seen_codes[code] = index

        category = _parse_enum(WorkTypeCategory, entry.get("category"), label, "category", problems)
        aliases = _parse_aliases(entry.get("aliases"), label, alias_owners, problems)
        refs = tuple(str(r) for r in entry.get("projects") or [] if str(r).strip())

        if category is not None and name:
            work_types.append(
                SeedWorkType(
                    code=code,
                    name=name,
                    category=category,
                    description=(str(entry["description"]) if entry.get("description") else None),
                    aliases=aliases,
                    project_refs=refs,
                )
            )

    for normalised, owners in sorted(alias_owners.items()):
        if len(owners) > 1:
            problems.append(
                f"alias {normalised!r} is claimed by {len(owners)} work types "
                f"({', '.join(sorted(owners))}); normalised aliases must be globally unique"
            )

    if problems:
        raise SeedValidationError(problems)

    return WorkTypeSeed(
        version=str(payload.get("version") or "unknown"),
        source=str(payload.get("source") or "unknown"),
        work_types=tuple(work_types),
    )


def _parse_aliases(
    raw: Any, label: str, alias_owners: dict[str, list[str]], problems: list[str]
) -> tuple[SeedAlias, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        problems.append(f"{label}: 'aliases' is not an array")
        return ()

    parsed: list[SeedAlias] = []
    for position, item in enumerate(raw):
        where = f"{label}.aliases[{position}]"
        if not isinstance(item, dict):
            problems.append(f"{where} is not an object")
            continue
        text = str(item.get("alias") or "").strip()
        if not text:
            problems.append(f"{where}: alias is blank")
            continue
        normalised = normalise_alias(text)
        if not normalised:
            problems.append(f"{where}: alias {text!r} is empty once normalised")
            continue
        kind = _parse_enum(AliasKind, item.get("kind"), where, "kind", problems)
        if kind is None:
            continue
        alias_owners.setdefault(normalised, []).append(label)
        parsed.append(SeedAlias(alias=text, kind=kind, normalised=normalised))
    return tuple(parsed)


def _parse_enum(enum_cls: Any, value: Any, label: str, field: str, problems: list[str]) -> Any:
    try:
        return enum_cls(str(value))
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        problems.append(f"{label}: {field} {value!r} is not one of ({allowed})")
        return None
