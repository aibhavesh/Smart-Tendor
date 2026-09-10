"""Load the work-type taxonomy from the seed file.

Run this once the seed file exists, against the same database the app uses
(``DATABASE_URL`` from your existing settings):

    cd backend
    python scripts/load_work_types.py --dry-run          # report, write nothing
    python scripts/load_work_types.py --types-only       # first pass only
    python scripts/load_work_types.py                    # full load

**Always dry-run first.** The report shows which past project each LOA reference
resolved to, and one reference naming the wrong project looks exactly like one
naming the right project. That pairing is the only place a mis-attribution is
visible, and no later check will catch it.

Two passes, blocked on different things:

* ``--types-only`` loads the 40 work types and 131 aliases. These key on ``code``
  and reconcile against nothing, so they load as soon as the seed file exists.
* The full run additionally creates the project tags, which reconcile each LOA
  reference against ``past_projects.loa_reference``. That needs the portfolio
  loaded with its references first.

Safe to re-run. Work types are matched by code and aliases by normalised form,
so a second run creates nothing it already created. The whole load is one
transaction, one portfolio-counter bump and one audit entry.

The loader never guesses. A reference matching no project aborts the run and
names it rather than dropping the tag, because a silently missing tag is a
capability the company can no longer evidence and nothing downstream reports it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from tender_intel.application.services.work_type_seed_service import WorkTypeSeedService
from tender_intel.core.config import get_settings
from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.infrastructure.db.session import create_engine, create_session_factory
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyPortfolioVersionRepository,
)
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.work_type_repo import SqlAlchemyWorkTypeRepository
from tender_intel.infrastructure.seed.work_type_seed import SeedValidationError, load_seed_file

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "work_types_seed.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--seed",
        type=Path,
        default=DEFAULT_SEED,
        help=f"path to the seed JSON (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen and write nothing",
    )
    parser.add_argument(
        "--types-only",
        action="store_true",
        help="load work types and aliases only, skipping the project tags",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    try:
        seed = load_seed_file(args.seed)
    except SeedValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(
        f"Seed {args.seed.name}: version {seed.version}, source {seed.source} — "
        f"{len(seed.work_types)} work types, {seed.alias_count} aliases, "
        f"{seed.link_count} project links across "
        f"{len(seed.distinct_project_refs)} distinct references."
    )

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            service = WorkTypeSeedService(
                work_types=SqlAlchemyWorkTypeRepository(session),
                projects=SqlAlchemyPastProjectRepository(session),
                versions=SqlAlchemyPortfolioVersionRepository(session),
                audits=SqlAlchemyAuditLogRepository(session),
            )
            plan = await service.plan(seed)
            print()
            print(plan.describe())

            if args.dry_run:
                print()
                print("Dry run: nothing was written.")
                return 0 if plan.can_load_tags or args.types_only else 1

            try:
                outcome = await service.load(seed, types_only=args.types_only)
            except DomainValidationError as exc:
                print(f"\nRefused: {exc}", file=sys.stderr)
                return 1

            await session.commit()
            print()
            print(
                f"Loaded: {outcome.work_types_created} work types, "
                f"{outcome.aliases_created} aliases, {outcome.tags_created} project tags."
            )
            if outcome.tags_skipped:
                print("Project tags were skipped (--types-only).")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
