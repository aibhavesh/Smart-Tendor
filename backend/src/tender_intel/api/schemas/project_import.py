"""Bulk past-project import contracts.

Mirrors the tender import response (``BulkImportResponse``) so the two read the
same way, with one added level: a batch holds files, and a file holds rows.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from tender_intel.application.dto.project_import import (
    FileImportResult,
    ProjectImportResult,
    ProjectRowResult,
)


class ProjectImportRowResponse(BaseModel):
    row: int
    name: str | None
    outcome: str
    message: str | None
    project_id: UUID | None
    work_types_linked: int
    #: False when this project will not count as eligibility evidence.
    eligibility_visible: bool
    #: The fields whose absence keeps it invisible. Empty when it is visible.
    missing_for_eligibility: list[str]

    @classmethod
    def from_dto(cls, r: ProjectRowResult) -> ProjectImportRowResponse:
        return cls(
            row=r.row,
            name=r.name,
            outcome=r.outcome.value,
            message=r.message,
            project_id=r.project_id,
            work_types_linked=r.work_types_linked,
            eligibility_visible=r.eligibility_visible,
            missing_for_eligibility=list(r.missing_for_eligibility),
        )


class ProjectImportFileResponse(BaseModel):
    filename: str
    outcome: str
    message: str | None
    created: int
    skipped: int
    errors: int
    rows: list[ProjectImportRowResponse]

    @classmethod
    def from_dto(cls, f: FileImportResult) -> ProjectImportFileResponse:
        return cls(
            filename=f.filename,
            outcome=f.outcome.value,
            message=f.message,
            created=f.created,
            skipped=f.skipped,
            errors=f.errors,
            rows=[ProjectImportRowResponse.from_dto(r) for r in f.rows],
        )


class ProjectImportResponse(BaseModel):
    created: int
    skipped: int
    errors: int
    files_failed: int
    work_types_linked: int
    #: How many of the created projects will actually count as stage B evidence.
    eligibility_visible: int
    #: Work types available to match against during this batch. Zero means the
    #: taxonomy was empty and nothing could be tagged — a system fault, not a
    #: fault in the uploaded rows.
    taxonomy_work_types: int
    #: Work types this batch created first, because the taxonomy was missing.
    taxonomy_provisioned: int
    files: list[ProjectImportFileResponse]

    @classmethod
    def from_dto(cls, result: ProjectImportResult) -> ProjectImportResponse:
        return cls(
            created=result.created,
            skipped=result.skipped,
            errors=result.errors,
            files_failed=result.files_failed,
            work_types_linked=result.work_types_linked,
            eligibility_visible=result.eligibility_visible,
            taxonomy_work_types=result.taxonomy_work_types,
            taxonomy_provisioned=result.taxonomy_provisioned,
            files=[ProjectImportFileResponse.from_dto(f) for f in result.files],
        )
