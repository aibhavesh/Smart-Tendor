"""Backfill work-type links onto past projects that have none.

    cd backend
    python scripts/backfill_work_type_tags.py --dry-run    # report, write nothing
    python scripts/backfill_work_type_tags.py --apply      # write the tags

**Always dry-run first.** Read the report before committing: a project linked to
the wrong work type looks exactly like one linked to the right work type, and
stage B would pool both without complaint.

Why this exists
---------------

A past project is counted as eligibility evidence only when it carries a work-type
link, a work value, and a completion certificate date. Links are written at import
time by the stage A cascade, and that cascade has nothing to match against when the
taxonomy is empty.

Migrations create the ``work_types`` tables but none of their rows, and no deploy
step populates them. A database created that way therefore imports projects
successfully, indexes every embedding, and links **zero** work types — silently,
because an absent candidate set and a project that genuinely matches nothing look
identical from inside the importer. Stage A then has no candidates and stage B has
no links, so every tender screens ``INDETERMINATE``, which reads as "awaiting a
human" rather than "never configured".

Re-importing the workbook does **not** fix it. ``_import_row`` matches on the LOA
reference and returns ``SKIPPED`` before it ever reaches the tagging step, so a
second upload reports "already imported" for every row and links nothing. Note
also that the duplicate check only fires when ``loa_reference`` is set: a workbook
without one would not be skipped, it would create a second copy of every project.

That is why this script exists, and why it reads existing projects rather than
re-importing anything. It also cannot create projects, so it cannot duplicate them.

What it writes
--------------

Exactly what the importer would have written at the time: ``INFERRED`` source, the
match score as confidence, and the same evidence string, by way of the same
``WorkTypeTagger``. A backfilled link and an imported link are indistinguishable
downstream, which is the point — stage B must not be able to tell which path ran.

Projects that already carry links are skipped and reported, so the script is safe
to re-run. The portfolio counter is bumped once at the end, which is what makes
existing screening results report themselves stale.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

from tender_intel.application.services.work_type_seed_service import WorkTypeSeedService
from tender_intel.application.services.work_type_service import WorkTypeService
from tender_intel.application.services.work_type_tagger import WorkTypeTagger
from tender_intel.core.config import get_settings
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest
from tender_intel.infrastructure.db.orm import PastProjectWorkTypeModel, UserModel
from tender_intel.infrastructure.db.session import create_engine, create_session_factory
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyPortfolioVersionRepository,
)
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.work_type_repo import SqlAlchemyWorkTypeRepository

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="report what would happen, write nothing"
    )
    mode.add_argument("--apply", action="store_true", help="write the links")
    parser.add_argument(
        "--actor",
        type=str,
        default=None,
        help="email of the account recorded as the actor on each link's audit entry",
    )
    parser.add_argument(
        "--retag",
        action="store_true",
        help="also re-evaluate projects that already carry links (adds only; never removes)",
    )
    return parser.parse_args()


async def _actor_id(session, email: str | None) -> UUID | None:
    """Look up the named actor. ``None`` records a system action."""
    if not email:
        return None
    result = await session.execute(select(UserModel).where(UserModel.email == email.lower()))
    user = result.scalars().first()
    if user is None:
        print(f"No account with email {email!r}.", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    return user.id


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            work_type_repo = SqlAlchemyWorkTypeRepository(session)
            project_repo = SqlAlchemyPastProjectRepository(session)
            versions = SqlAlchemyPortfolioVersionRepository(session)
            audits = SqlAlchemyAuditLogRepository(session)
            seed = WorkTypeSeedService(
                work_types=work_type_repo,
                projects=project_repo,
                versions=versions,
                audits=audits,
            )
            work_types = WorkTypeService(
                work_types=work_type_repo, projects=project_repo, versions=versions, audits=audits
            )
            tagger = WorkTypeTagger(work_types=work_type_repo, service=work_types)

            provisioned = await seed.ensure_taxonomy()
            if provisioned is not None:
                print(
                    f"Taxonomy was empty; provisioned "
                    f"{provisioned.work_types_created} work types and "
                    f"{provisioned.aliases_created} aliases."
                )

            candidates = await tagger.candidates()
            if not candidates:
                print(
                    "No active work types. Nothing can be linked until the taxonomy is populated.",
                    file=sys.stderr,
                )
                return EXIT_REFUSED

            actor_id = await _actor_id(session, args.actor)
            tagged_rows = (
                (await session.execute(select(PastProjectWorkTypeModel.project_id))).scalars().all()
            )
            already = set(tagged_rows)

            # Paged rather than one big scan: the portfolio can outgrow a single
            # result set, and every page is read before anything is written.
            projects = []
            offset = 0
            while True:
                page = await project_repo.list(PageRequest(limit=MAX_LIMIT, offset=offset))
                if not page.items:
                    break
                projects.extend(page.items)
                offset += len(page.items)
                if len(page.items) < MAX_LIMIT:
                    break

            print(f"\nActive work types available: {len(candidates)}")
            print(f"Past projects: {len(projects)}")
            print(f"Already linked: {len(already)}")
            print("")

            todo = [p for p in projects if args.retag or p.id not in already]
            skipped = len(projects) - len(todo)
            print(f"Will evaluate: {len(todo)}   (skipping {skipped} already linked)\n")

            total_linked = 0
            needs_review: list[tuple[str, tuple[str, ...]]] = []
            for project in todo:
                tagging = await tagger.tag(project, candidates, actor_id)  # type: ignore[arg-type]
                total_linked += tagging.linked
                marker = "RE" if project.id in already else "TAG"
                detail = (
                    f"{tagging.linked} link(s)"
                    if tagging.linked
                    else ("already linked" if project.id in already else "no match")
                )
                print(f"  [{marker}] {project.name[:58]:<58} {detail}")
                if tagging.considered:
                    needs_review.append((project.name, tagging.considered))

            if needs_review:
                print("\nNeeds review (matched only in the review band, so NOT linked):")
                for name, codes in needs_review:
                    print(f"  {name[:60]:<60} {', '.join(codes)}")

            print(f"\nTotal links that would be written: {total_linked}")

            if args.dry_run:
                await session.rollback()
                print("\nDry run: nothing was written.")
                return EXIT_OK

            if total_linked:
                # One bump for the batch, matching the importer's own convention.
                await versions.bump()
            await session.commit()
            print(f"\nApplied: {total_linked} link(s) written.")
            if total_linked:
                print(
                    "Existing screening results are now stale. Re-screen the tenders "
                    "to recompute them."
                )
            return EXIT_OK
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
