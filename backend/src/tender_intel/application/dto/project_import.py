"""Bulk past-project import DTOs.

Deliberately the same shape as :mod:`tender_intel.application.dto.ingestion`:
``ImportOutcome`` is reused verbatim and :class:`ProjectRowResult` mirrors
``RowResult``, so a caller that already renders the tender import can render this
one without learning a second convention.

The one addition is a file layer. A tender import is one workbook of many rows;
a project import is many files, and one of those files may itself be a workbook
of many rows. So outcomes nest: each file carries its own outcome plus the row
results it produced.

:class:`ProjectRowResult` also carries ``eligibility_visible``. A past project is
counted as evidence by the eligibility engine's stage B only when it has a work
value, a completion certificate date, and at least one work-type link. A project
missing any of the three imports successfully and is silently ignored by every
later eligibility screen, so the importer reports the distinction rather than
leaving it to be discovered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from tender_intel.application.dto.ingestion import ImportOutcome

__all__ = [
    "FileImportResult",
    "ImportOutcome",
    "ProjectImportResult",
    "ProjectRowResult",
]


@dataclass(frozen=True, slots=True)
class ProjectRowResult:
    """One past project attempted from one row (or one whole document)."""

    #: 1 for a single-document file; the worksheet row number for a workbook.
    row: int
    name: str | None
    outcome: ImportOutcome
    message: str | None = None
    project_id: UUID | None = None
    #: Work-type links written by the automatic tagging cascade.
    work_types_linked: int = 0
    #: True only when this project will actually count as stage B evidence.
    eligibility_visible: bool = False
    #: Why it will not count, when it will not. Empty when it will.
    missing_for_eligibility: tuple[str, ...] = ()


@dataclass(slots=True)
class FileImportResult:
    """Every project attempted from one uploaded file."""

    filename: str
    outcome: ImportOutcome
    message: str | None = None
    rows: list[ProjectRowResult] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for r in self.rows if r.outcome is ImportOutcome.CREATED)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.rows if r.outcome is ImportOutcome.SKIPPED)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.rows if r.outcome is ImportOutcome.ERROR)


@dataclass(slots=True)
class ProjectImportResult:
    """The whole batch."""

    files: list[FileImportResult] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(f.created for f in self.files)

    @property
    def skipped(self) -> int:
        return sum(f.skipped for f in self.files)

    @property
    def errors(self) -> int:
        return sum(f.errors for f in self.files)

    @property
    def files_failed(self) -> int:
        """Files rejected whole, before any row was attempted."""
        return sum(1 for f in self.files if f.outcome is ImportOutcome.ERROR)

    @property
    def work_types_linked(self) -> int:
        return sum(r.work_types_linked for f in self.files for r in f.rows)

    @property
    def eligibility_visible(self) -> int:
        return sum(1 for f in self.files for r in f.rows if r.eligibility_visible)
