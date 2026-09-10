"""Bulk import of past-project documents (PDF and XLSX).

One operation, many files, per-file isolation: a file that fails is reported and
the batch continues. Within a workbook the same holds per row.

Composition rather than reimplementation. Workbook rows come from
:func:`parse_project_rows`, which is the tender workbook reader with a
past-project heading map. Single documents go through
``PastProjectService.create_from_document``, the extractor that already existed.
Creation itself goes through ``PastProjectService.create``, so vector indexing
and the per-project audit entry happen exactly as they do for a hand-entered
project.

**Work-type linking is part of the import, not an afterthought.** The eligibility
engine's stage B pools a past project only when it carries at least one
work-type link, a work value, and a completion certificate date. A project
imported without links is accepted, stored, listed in the UI - and silently
ignored by every eligibility screen thereafter. So each imported project is run
through the stage A matching cascade and confidently matched types are linked as
``INFERRED``. Weaker matches are named in the row message for a human to confirm,
never linked automatically, because an asserted capability the company cannot
evidence is worse than an absent one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tender_intel.application.dto.past_project import PastProjectCreate
from tender_intel.application.dto.project_import import (
    FileImportResult,
    ImportOutcome,
    ProjectImportResult,
    ProjectRowResult,
)
from tender_intel.application.services.past_project_service import PastProjectService
from tender_intel.application.services.work_type_service import WorkTypeService
from tender_intel.domain.decision.normalise import tokenise
from tender_intel.domain.decision.work_type_match import WorkTypeCandidate, match_work_types
from tender_intel.domain.entities import AuditLog, PastProject
from tender_intel.domain.enums.eligibility import MatchGrade
from tender_intel.domain.enums.work_type import WorkTypeLinkSource
from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    PastProjectRepository,
    WorkTypeRepository,
)
from tender_intel.infrastructure.observability.logging import get_logger
from tender_intel.infrastructure.project_workbook import (
    coerce_amount,
    coerce_date,
    coerce_text,
    collapse_whitespace,
    parse_project_rows,
    reference_key,
    split_certificate,
)

_log = get_logger(__name__)

#: Extensions handled as a whole workbook of many projects.
WORKBOOK_SUFFIXES = (".xlsx", ".xlsm")
#: Extensions handled as one document describing one project.
DOCUMENT_SUFFIXES = (".pdf",)


@dataclass(frozen=True, slots=True)
class _Tagging:
    """What the cascade concluded for one project."""

    linked: int
    considered: tuple[str, ...]


class ProjectImportService:
    def __init__(
        self,
        *,
        projects: PastProjectService,
        work_types: WorkTypeService,
        work_type_repo: WorkTypeRepository,
        project_repo: PastProjectRepository,
        audits: AuditLogRepository,
    ) -> None:
        self._projects = projects
        self._project_repo = project_repo
        self._work_types = work_types
        self._work_type_repo = work_type_repo
        self._audits = audits

    async def import_files(
        self,
        files: list[tuple[str, bytes, str | None]],
        *,
        auto_tag: bool = True,
        actor_id: UUID,
        actor_role: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> ProjectImportResult:
        """Import every file, isolating failures to the file that caused them."""
        result = ProjectImportResult()
        candidates = await self._candidates() if auto_tag else []

        for filename, content, mime_type in files:
            result.files.append(
                await self._import_one(filename, content, mime_type, candidates, actor_id)
            )

        await self._audit_batch(result, actor_id, actor_role, ip, user_agent, auto_tag)
        return result

    # --- one file -----------------------------------------------------------

    async def _import_one(
        self,
        filename: str,
        content: bytes,
        mime_type: str | None,
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> FileImportResult:
        lowered = filename.lower()
        try:
            if lowered.endswith(WORKBOOK_SUFFIXES):
                return await self._import_workbook(filename, content, candidates, actor_id)
            if lowered.endswith(DOCUMENT_SUFFIXES):
                return await self._import_document(
                    filename, content, mime_type, candidates, actor_id
                )
        except Exception as exc:  # one bad file must not end the batch
            _log.warning("project_import.file_failed", filename=filename, error=str(exc))
            return FileImportResult(filename, ImportOutcome.ERROR, str(exc))
        return FileImportResult(
            filename,
            ImportOutcome.ERROR,
            "unsupported file type: expected .pdf or .xlsx",
        )

    async def _import_workbook(
        self,
        filename: str,
        content: bytes,
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> FileImportResult:
        file_result = FileImportResult(filename, ImportOutcome.CREATED)
        for row_number, record in parse_project_rows(content):
            file_result.rows.append(
                await self._import_row(row_number, record, candidates, actor_id)
            )
        if not file_result.rows:
            file_result.outcome = ImportOutcome.ERROR
            file_result.message = "no data rows found"
        return file_result

    async def _import_row(
        self,
        row_number: int,
        record: dict[str, Any],
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> ProjectRowResult:
        name = coerce_text(record.get("name"))
        if not name:
            return ProjectRowResult(row_number, None, ImportOutcome.ERROR, "name is required")

        certificate_date, certificate_note = split_certificate(
            record.get("completion_certificate_date")
        )
        loa_raw = record.get("loa_reference")
        loa_reference = collapse_whitespace(str(loa_raw))[:255] if loa_raw else None

        # An LOA reference identifies one award, and the column is unique. Check
        # before inserting rather than after: a failed INSERT leaves the session
        # needing a rollback, which would take every later row of the workbook
        # down with it. Re-importing a corrected workbook is routine, so a
        # duplicate is SKIPPED — the same outcome the tender import uses for a
        # tender number it already holds.
        if loa_reference is not None:
            existing = await self._project_repo.find_by_loa_reference(reference_key(loa_reference))
            if existing is not None:
                return ProjectRowResult(
                    row_number,
                    name,
                    ImportOutcome.SKIPPED,
                    f"LOA reference already imported as {existing.name!r}",
                    project_id=existing.id,
                )

        data = PastProjectCreate(
            name=name,
            client=coerce_text(record.get("client")),
            work_value=coerce_amount(record.get("work_value")),
            category=coerce_text(record.get("category")),
            location=coerce_text(record.get("location")),
            description=coerce_text(record.get("description")),
            completion_date=coerce_date(record.get("completion_date")),
            loa_reference=loa_reference,
            completion_certificate_date=certificate_date,
            completion_certificate_note=certificate_note,
        )
        try:
            project = await self._projects.create(data, actor_id=actor_id)
        except DomainValidationError as exc:
            # Raised while building the entity, before anything is flushed, so
            # the session is still usable and the next row can proceed. A
            # database-level failure is deliberately *not* caught here: it
            # leaves the session unusable, so it propagates and fails this file
            # rather than silently producing a run of bogus row errors.
            return ProjectRowResult(row_number, name, ImportOutcome.ERROR, str(exc))
        return await self._finish(row_number, project, candidates, actor_id)

    async def _import_document(
        self,
        filename: str,
        content: bytes,
        mime_type: str | None,
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> FileImportResult:
        file_result = FileImportResult(filename, ImportOutcome.CREATED)
        project = await self._projects.create_from_document(
            filename=filename, content=content, mime_type=mime_type, actor_id=actor_id
        )
        file_result.rows.append(await self._finish(1, project, candidates, actor_id))
        return file_result

    # --- work-type linking --------------------------------------------------

    async def _finish(
        self,
        row_number: int,
        project: PastProject,
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> ProjectRowResult:
        tagging = await self._tag(project, candidates, actor_id)
        missing = self._missing_for_eligibility(project, tagging.linked)
        message: str | None = None
        if tagging.considered:
            message = "needs review for work types: " + ", ".join(tagging.considered)
        return ProjectRowResult(
            row=row_number,
            name=project.name,
            outcome=ImportOutcome.CREATED,
            message=message,
            project_id=project.id,
            work_types_linked=tagging.linked,
            eligibility_visible=not missing,
            missing_for_eligibility=missing,
        )

    async def _tag(
        self,
        project: PastProject,
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> _Tagging:
        if not candidates:
            return _Tagging(0, ())
        scope = " ".join(
            part
            for part in (project.name, project.category, project.description)
            if part is not None and part.strip()
        )
        if not scope.strip():
            return _Tagging(0, ())

        linked = 0
        considered: list[str] = []
        for match in match_work_types(scope, candidates):
            if match.grade is MatchGrade.MATCHED:
                try:
                    await self._work_types.tag_project(
                        project.id,
                        match.work_type_id,
                        source=WorkTypeLinkSource.INFERRED,
                        confidence=match.score,
                        evidence=f"bulk import: {match.method.value} match on project name",
                        actor_id=actor_id,
                    )
                    linked += 1
                except Exception as exc:  # a tag failure is not an import failure
                    _log.warning(
                        "project_import.tag_failed",
                        project_id=str(project.id),
                        work_type=match.code,
                        error=str(exc),
                    )
            elif match.grade is MatchGrade.REVIEW:
                considered.append(f"{match.code} ({match.score})")
        return _Tagging(linked, tuple(considered))

    @staticmethod
    def _missing_for_eligibility(project: PastProject, linked: int) -> tuple[str, ...]:
        """Name every reason stage B will ignore this project."""
        missing: list[str] = []
        if project.work_value is None:
            missing.append("work_value")
        if project.completion_certificate_date is None:
            missing.append("completion_certificate_date")
        if linked == 0:
            missing.append("work_type_link")
        return tuple(missing)

    async def _candidates(self) -> list[WorkTypeCandidate]:
        """Build the stage A candidate set once for the whole batch."""
        active = await self._work_type_repo.list_active()
        if not active:
            return []
        aliases = await self._work_type_repo.list_aliases([wt.id for wt in active])
        candidates: list[WorkTypeCandidate] = []
        for work_type in active:
            own = [a for a in aliases if a.work_type_id == work_type.id]
            bags = [frozenset(tokenise(a.alias)) for a in own]
            bags.append(tokenise(work_type.embedding_text()))
            candidates.append(
                WorkTypeCandidate(
                    work_type_id=work_type.id,
                    code=work_type.code,
                    aliases=frozenset(a.normalised for a in own),
                    token_bags=tuple(bag for bag in bags if bag),
                    semantic_score=None,
                )
            )
        return candidates

    # --- audit --------------------------------------------------------------

    async def _audit_batch(
        self,
        result: ProjectImportResult,
        actor_id: UUID,
        actor_role: str | None,
        ip: str | None,
        user_agent: str | None,
        auto_tag: bool,
    ) -> None:
        await self._audits.add(
            AuditLog(
                action="past_project.bulk_import",
                entity_type="PastProject",
                entity_id=None,
                actor_id=actor_id,
                ip_address=ip,
                user_agent=user_agent,
                diff={
                    "actor_role": actor_role,
                    "auto_tag": auto_tag,
                    "files": [
                        {
                            "filename": f.filename,
                            "outcome": f.outcome.value,
                            "created": f.created,
                            "errors": f.errors,
                        }
                        for f in result.files
                    ],
                    "created": result.created,
                    "skipped": result.skipped,
                    "errors": result.errors,
                    "files_failed": result.files_failed,
                    "work_types_linked": result.work_types_linked,
                    "eligibility_visible": result.eligibility_visible,
                },
            )
        )


__all__ = ["ProjectImportService"]
