# Repository context — Tender Eligibility Screening Platform

Onboarding reference for the codebase at `Smart-Tendor`. Written from a full read
of the backend and frontend source, and verified against a running stack and a
live PostgreSQL database.

**Source of truth.** `README.md` is the specification used throughout this
document. Where code and README disagree, the divergence is recorded in
[Known limitations](#known-limitations), not silently reconciled.

---

## Contents

- [What the platform does](#what-the-platform-does)
- [Stack and services](#stack-and-services)
- [Architecture map](#architecture-map)
- [End-to-end tender flow](#end-to-end-tender-flow)
- [API contract inventory](#api-contract-inventory)
- [The screening engine](#the-screening-engine)
- [Lifecycle state machine](#lifecycle-state-machine)
- [Data model](#data-model)
- [Authentication and RBAC](#authentication-and-rbac)
- [Observability](#observability)
- [Configuration](#configuration)
- [Tests](#tests)
- [Frontend](#frontend)
- [Known limitations](#known-limitations)
- [Open questions](#open-questions)

---

## What the platform does

The platform ingests a tender, extracts its commercial and eligibility terms, and
screens it against the company's declared financial capacity and its own past
projects. It answers *can we bid this?* as `ELIGIBLE` / `NOT_ELIGIBLE` /
`INDETERMINATE`, with the reasoning attached.

Two invariants govern the design:

- **The scoring is deterministic.** There is no model in the decision path. All
  arithmetic is exact `Decimal`.
- **Fail toward caution.** `UNKNOWN` over a guess, `INDETERMINATE` over a
  refusal, offline fallback over failure, an audit entry on every state change.

### The single most important thing to know

**This is not the bid-recommendation platform the older documentation described.**

It was one. It computed a risk score across six categories, derived a win
probability and a confidence figure, generated a prose analyst narrative via
Gemini, and collected human APPROVE/REJECT verdicts through a review queue.
Migration `f0e1d2c3b4a5` — "reduce to eligibility workflow", 2026-09-26 — removed
that surface: the `reviews` router, the `tender_reviews` and
`eligibility_notifications` tables, the audit-log read surface, the
notification sender, and the risk and recommendation engines themselves. The
frontend was migrated to eligibility screening at the same time.

What was left behind, and has since been dealt with:

| Left behind | Resolution |
| --- | --- |
| `RiskEngine`, `RecommendationEngine` fully implemented, unit-tested, zero callers | Deleted, with their 37 passing tests |
| `SmtpEmailSender`, `GeminiLLMProvider`, `AnalystReport` — orphaned | Deleted |
| `require_exact_roles`, `User.is_exactly` — zero call sites | Deleted |
| `BOQAnalytics` endpoint and DTO — zero callers | Deleted |
| `get_audit_repo` returning a no-op sink, so ~20 audit writes across 11 services were silently discarded | **Restored.** Table re-created by `b1a4c7e2d903`, real repository wired in |
| `/admin/audit-logs`, `/admin/stats`, `/admin/system-health`, `/admin/api-usage` — service methods and schemas intact, routers missing | **Restored** |
| `/observability/logs`, `/metrics` — client still shipped logs to a 404 | **Restored**; `ObservabilityMiddleware` was never registered, so `/admin/api-usage` always reported 0 |
| `reviews_pending` / `reviews_total` hard-coded to `0` | Replaced with real screening figures |
| 6 test modules importing deleted services; 62 failing tests | Retargeted or deleted; suite is green |

If you are evaluating this codebase, read that table before reading anything
else. The tests and the older docs were the last things updated, and both were
substantially wrong about what the system does.

---

## Stack and services

| Layer | Technology |
| --- | --- |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Web | Node 22 · Next.js 16 (App Router) · React 19 · Tailwind CSS 4 |
| Data | PostgreSQL 16 · Qdrant |
| Embeddings | fastembed · `BAAI/bge-small-en-v1.5` (384-d), with a deterministic offline hash backend |
| Extraction | pdfplumber / PyMuPDF · openpyxl for spreadsheet import |
| Observability | structlog · Prometheus · OpenTelemetry · Sentry |
| Edge | nginx on `:8080` → web on `:3000`, `/api/` → API on `:8000` |

| Service | Port | Notes |
| --- | --- | --- |
| `nginx` | 8080 | The entry point. Use this one. |
| `frontend` | 3000 | Next.js |
| `backend` | 8000 | FastAPI; OpenAPI at `/docs` |
| `postgres` | 5432 | Healthchecked; setup waits on it |
| `qdrant` | 6333 | Vector store for past-project matching |

### Commands

```bash
# One-command bootstrap from a fresh clone
./scripts/setup.ps1          # Windows
./scripts/setup.sh           # macOS / Linux / Git Bash
# then open http://localhost:8080

# Native mode (reload on save): Postgres and Qdrant in Docker, API and web on the host
./scripts/setup.sh --mode native
./scripts/dev.sh             # API :8000 + web :3000

# Backend, from backend/
pytest                       # 555 tests, no live database needed
ruff check src tests
ruff format --check src tests
mypy src                     # strict
alembic upgrade head

# Frontend, from frontend/
npm run lint                 # raw hex / rgb() / hsl() fail the build
npm run typecheck
npm run build
```

Re-running setup is safe: a value already set is never overwritten.

---

## Architecture map

Clean Architecture. Dependencies point inward; the domain depends on nothing. The
boundary holds — `domain/` imports nothing from `application/`, `infrastructure/`
or `api/`.

```
backend/src/tender_intel/
  domain/          entities, enums, decision engines, exceptions, interfaces
  application/     use-case services orchestrating the domain
  infrastructure/  SQLAlchemy repos, vector store, extraction, observability
  api/             FastAPI routers, schemas, dependencies
  core/            env-sourced settings + DI container
frontend/src/
  app/             Next.js App Router routes
  components/      screen and design-system components
  lib/             API client, auth, role and status helpers
scripts/           setup + dev launchers (PowerShell and Bash)
docker/nginx/      reverse proxy config
```

151 Python source files; 47 test files.

### Layer inventory

| Layer | Contents |
| --- | --- |
| Domain | 13 entities, 9 enum modules, the screening engine plus `work_type_match`, `duration`, `fingerprint`, `normalise`, `thresholds`, repository ports, value objects, 3 domain services (`email_domain`, `financial_year`, `retirement`) |
| Application | 13 services, 8 DTO modules |
| Infrastructure | 7 SQLAlchemy repos, Qdrant store, PDF/Excel extraction, two async polling workers, observability, storage, downloader |
| API | 14 routers, 12 schema modules, DI dependencies, centralised error mapping |
| Core | Pydantic settings with production release gates, DI container |

---

## End-to-end tender flow

1. **Register.** `POST /tenders` writes a `Tender` at `REGISTERED`. Bulk import via
   `POST /tenders/import` parses an xlsx and, when a row carries a source URL,
   queues a document for download.
2. **Acquire.** A document arrives by URL (status `PENDING`) or by direct upload.
   `DocumentDownloadWorker` polls every 15 seconds, downloads, SHA-256 hashes and
   stores it. First success advances the tender to `DOWNLOADED`; a direct upload
   advances it synchronously.
3. **Extract.** `POST /tenders/{id}/extract` reads the stored file, pulls text
   through pdfplumber or PyMuPDF on a worker thread, runs the rule-based extractor
   for the ten metadata fields, parses BOQ tables, and advances to `PARSED`.
4. **Screen.** `EligibilityWorkflowWorker` picks up `DOWNLOADED` tenders and runs
   extraction then screening in one transaction. `POST /api/v1/tenders/{id}/eligibility`
   does the same on demand.

There is no separate "analyze" step. Screening *is* the analysis.

---

## API contract inventory

47 paths. Auth column: **none** is unauthenticated, **Auth** is any active
signed-in user, a role name is the inclusive minimum via `require_role`.

### Health, stats, observability

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/health` | none | |
| GET | `/stats` | Auth | Tenders by status, eligibility breakdown, past projects, screening backlog |
| GET | `/metrics` | HTTP Basic | Prometheus exposition; 404 when disabled |
| POST | `/observability/logs` | none | Browser log batches, rate-limited per entry |

### Auth

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/auth/register` | none | 201; refuses a duplicate email |
| POST | `/auth/login` | none | One generic failure for every cause |
| POST | `/auth/google` | none | Optional GIS path |
| POST | `/auth/refresh` | none | Rotates |
| POST | `/auth/logout` | none | 204 |
| GET | `/auth/me` | Auth | |

### Tenders and documents

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/tenders` | EMPLOYEE |
| GET | `/tenders` | Auth — `limit`, `offset`, `status`, `eligibility`, `search` |
| GET | `/tenders/{id}` | Auth |
| PATCH | `/tenders/{id}` | EMPLOYEE |
| DELETE | `/tenders/{id}` | EMPLOYEE |
| DELETE | `/tenders` | MANAGER — bulk |
| POST | `/tenders/import` | EMPLOYEE — multipart xlsx |
| POST | `/tenders/{id}/documents` | EMPLOYEE — from URL |
| POST | `/tenders/{id}/documents/upload` | EMPLOYEE — multipart |
| GET | `/tenders/{id}/documents` | Auth |
| GET | `/documents/{id}` | Auth |
| POST | `/documents/{id}/retrigger` | EMPLOYEE |

### Extraction and screening

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/tenders/{id}/extract` | EMPLOYEE — optional `document_id` |
| GET | `/tenders/{id}/metadata` | Auth — 404 if absent |
| GET | `/tenders/{id}/boq` | Auth — unpaged |
| POST | `/api/v1/tenders/{id}/eligibility` | EMPLOYEE |
| GET | `/api/v1/tenders/{id}/eligibility` | Auth |

### Past projects, turnover, work types

| Method | Path | Auth |
| --- | --- | --- |
| POST/GET | `/projects` | EMPLOYEE / Auth |
| GET/PATCH/DELETE | `/projects/{id}` | Auth / EMPLOYEE / EMPLOYEE |
| DELETE | `/projects` | MANAGER — bulk |
| POST | `/projects/backfill` | ADMIN |
| POST | `/api/v1/projects/import` | EMPLOYEE |
| GET | `/api/v1/work-types`, `/work-types/{id}` | Auth |
| POST/PATCH/DELETE | work-type mutations, aliases, deactivation | ADMIN |
| POST/DELETE | `/api/v1/projects/{id}/work-types[/{id}]` | ADMIN |
| GET | `/api/v1/company-turnover` | **MANAGER** — including the read |
| POST | `/api/v1/company-turnover` | MANAGER |
| PATCH | `/api/v1/company-turnover/{financial_year}` | MANAGER |
| POST | `/api/v1/company-turnover/import` | MANAGER — extracts candidates, never writes |

### Retirement

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/api/v1/tenders/retirement/preview` | ADMIN |
| POST | `/api/v1/tenders/retirement` | ADMIN — the only route that archives |

### Admin

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/admin/users`, `/admin/users/{id}` | ADMIN |
| PATCH | `/admin/users/{id}/role`, `/admin/users/{id}/active` | ADMIN |
| DELETE | `/admin/users/{id}` | **SUPER_ADMIN** |
| GET/POST | `/admin/role-assignments` | ADMIN |
| DELETE | `/admin/role-assignments/{id}` | ADMIN |
| GET | `/admin/audit-logs` | ADMIN — `actor_id`, `entity_type`, `action`, `date_from`, `date_to` |
| GET | `/admin/stats`, `/admin/system-health`, `/admin/api-usage` | ADMIN |

### Error mapping

Centralised in `api/errors.py`. Bodies stay generic; full detail is logged
server-side.

| Domain exception | Status |
| --- | --- |
| `EntityNotFoundError` | 404 |
| `LiveUserExistsError`, `AssignmentConsumedError`, `DuplicateEntityError`, `InvalidStatusTransitionError` | 409 |
| `AuthenticationError`, `InvalidTokenError` | 401 with `WWW-Authenticate: Bearer` |
| `InactiveUserError`, `ForbiddenDomainError`, `PermissionDeniedError` | 403 |
| `DomainValidationError` | 422 |
| unmapped `DomainError` | 500 |

There is no 400 anywhere in the map. **422 is overloaded**: it is FastAPI's
request-validation status *and* the mapping for `DomainValidationError`, which is
what a caller gets for screening an unparsed tender.

---

## The screening engine

`domain/decision/eligibility.py`, plus `work_type_match.py`, `duration.py`,
`fingerprint.py` and `normalise.py`. Every constant comes from `thresholds.py`
and no numeric literal is inlined. All arithmetic is exact `Decimal` built from
strings.

### The three rules

| Rule | Test |
| --- | --- |
| Financial | Required capital is `min(V/N, V)` against the average certified turnover over the last **3 completed** financial years. |
| Stage A — work type | Scope-of-work text against the taxonomy: `EXACT` → `LEXICAL` → `SEMANTIC`, first hit wins, graded `MATCHED` ≥ 0.70, `REVIEW` ≥ 0.50. |
| Stage B — similar work | Projects completed within **7 years**, work-type-matched, valued at 60% / 40% / 30% of tender value for one / two / three projects. |

### Status resolution

`_status` folds the rule results:

- any **definite `False`** → `NOT_ELIGIBLE`
- otherwise any **`None`** → `INDETERMINATE`
- otherwise → `ELIGIBLE`

So a missing input can never produce a pass, and can never produce a failure
either. Fewer than three completed turnover years is `INDETERMINATE`, which is
the single most consequential behaviour in the engine: an unconfigured
installation reaches a person with every tender rather than refusing all of them.

### Thresholds

`thresholds.py` is now 14 constants, down from about 60. Everything risk- and
win-probability-related was removed with its engine.

| Constant | Value | Provenance |
| --- | --- | --- |
| `WORK_TYPE_MATCHED_MIN_INCLUSIVE` | 0.70 | Spec §3 |
| `WORK_TYPE_REVIEW_MIN_INCLUSIVE` | 0.50 | Spec §3 |
| `EXACT_MATCH_SCORE` | 1.0 | Spec §3 |
| `SIMILAR_WORK_LOOKBACK_YEARS` | 7 | Spec §3 |
| `SIMILAR_WORK_1_PCT` / `_2_PCT` / `_3_PCT` | 60 / 40 / 30 | Spec §3 |
| `TURNOVER_AVERAGING_YEARS` | 3 | Spec §2 |
| `CONFIDENCE_MIN` / `CONFIDENCE_MAX` | 0.1 / 1.0 | Spec §7 |
| `DAYS_PER_YEAR` | 365 | Spec §1 |

The three constants previously tagged `INFERRED` against rulings in a
`docs/decisions/` directory that is not in this repository — `RISK_AGGREGATION`,
`WIN_INTERMEDIATE_SLOPE`, `NET_WORTH_MINIMUM` — are gone with their engines, so
that dangling citation is closed. The `WORK_VALUE_REQUIRED_PCT_DEFAULT`
placeholder is gone too.

---

## Lifecycle state machine

```
REGISTERED → DOWNLOADED → PARSED → ARCHIVED
```

| State | Meaning |
| --- | --- |
| `REGISTERED` | Tender recorded; source documents not yet fetched |
| `DOWNLOADED` | Documents retrieved and stored |
| `PARSED` | Text and fields extracted from those documents |
| `ARCHIVED` | Closed. Terminal — nothing transitions out of it |

The enum also still defines `ANALYZED` and `REVIEWED`, and the edges
`ANALYZED ⇄ REVIEWED` plus `ANALYZED → PARSED`, but **no code path reaches
either state**. They are retained so existing rows stay readable and filterable,
and so a future bid-decision feature has somewhere to attach. Only three
`transition_to` call sites exist in the source:

| Caller | Target |
| --- | --- |
| `document_service` | `DOWNLOADED` |
| `extraction_service` | `PARSED` |
| `retirement_service` | `ARCHIVED` |

Documents carry their own status, independent of the tender:
`PENDING` → `DOWNLOADING` → `DOWNLOADED`, or `FAILED`. No transition guard.

### Staleness

`TenderEligibility` stores a fingerprint of its inputs. `compute_fingerprint`
hashes the canonical inputs plus a `portfolio_version` counter that every
work-type, alias, tag and project mutation bumps. `is_stale` recomputes and
compares — never a stored flag, so nothing has to remember to clear it.

`TenderMetadata.touch()` stamps `updated_at` from the Python clock rather than
letting the ORM do it, because a database-sourced timestamp could make an edit
read as *older* than the row that should invalidate it.

---

## Data model

Seventeen tables at head. All primary keys are UUID. Money is `Numeric`, never
float. Enums are stored as their string value for portability across PostgreSQL
and the SQLite the tests use. JSON columns use `sa.JSON`, not JSONB, for the same
reason.

| Table | Key relationships |
| --- | --- |
| `users` | unique `email`, unique `google_sub`, nullable `hashed_password` |
| `role_assignments` | `assigned_by` and `consumed_user_id` → `users`, `SET NULL`; unique `email` |
| `user_sessions` | `user_id` → `users`, `CASCADE`; unique `refresh_token_hash` |
| `tenders` | unique `tender_number`; indexed `status` |
| `tender_documents` | `tender_id` → `tenders`, `CASCADE`; `purged_at` distinguishes reclaimed from never-fetched |
| `tender_metadata` | `tender_id` → `tenders`, `CASCADE`, **unique**; ten fields in one JSON column |
| `boq_items` | `tender_id` → `tenders`, `CASCADE` |
| `past_projects` | standalone; indexed `work_value`, `category`, `embedding_indexed` |
| `work_types` / `work_type_aliases` | alias `alias_normalised` is **globally** unique |
| `past_project_work_types` | join table, carries a `source` |
| `company_turnover` | unique `financial_year`; `recorded_by` → `users`, `SET NULL`; `certificate_document_id` is a bare UUID with no FK |
| `tender_eligibility` | one row per tender, `tender_id` as PK |
| `tender_eligibility_work_types` / `_projects` | evidence tables, replaced on re-screen |
| `portfolio_version` | single counter row, bumped on every portfolio mutation |
| `audit_logs` | **no foreign keys at all** — see below |

### `audit_logs`

`actor_id` is a bare `Uuid` with no foreign key, deliberately. Every other
user-referencing column cascades or nulls on delete; an audit row that vanishes
with the user who caused it cannot answer "who did this", which is the only
question the table exists to answer. The trade-off is that orphan rows outlive
their actor, which is the correct direction for an append-only record.

The ORM registers no update or delete path. Verified live: a tender create, update
and delete through the real API produced three rows with a real before/after diff
on the update.

### The ten metadata fields

`work_name`, `estimated_value`, `emd_amount`, `tender_fee`, `closing_date`,
`completion_period`, `location`, `department`, `eligibility_criteria`,
`scope_of_work`. Each is an `ExtractedField` carrying a value, a confidence and a
source. Absent values are `UNKNOWN`, never guessed. Rule-based extraction assigns
0.8 confidence to parsed amounts and dates, 0.7 to free text.

### Migration chain

Single head, no branches. The DSN comes from application settings, never
`alembic.ini`.

```
df21fab595ca  initial schema
  → a1c4e07b91d2  collapse ANALYST and VIEWER into EMPLOYEE
  → b7f39d5a2e60  drop password authentication
  → c2d8b6f4173a  create role_assignments
  → d4a1e9c5b872  bootstrap the first SUPER_ADMIN
  → e7c3a5d18f92  split correction from verdict
  → 7690fc277a01  restore password authentication
  → a3f81b6c9d24  eligibility screening
  → b8e2c47f1a93  document purge marker for tender retirement
  → c9f5d38b2e71  eligibility notification ledger
  → f0e1d2c3b4a5  reduce to eligibility workflow   ← drops reviews, audit, notifications
  → b1a4c7e2d903  restore the audit trail         (head)
```

Two migrations cancel out: `b7f39d5a2e60` drops `hashed_password` and
`7690fc277a01` adds it back nullable.

`d4a1e9c5b872` reads `BOOTSTRAP_SUPER_ADMIN_EMAIL` from application settings at
migration time. It is idempotent, guarded on the normalised email, skips when the
account exists, and is a no-op when unset. **Set it before the first migration.**

**`f0e1d2c3b4a5` makes its `downgrade` raise `NotImplementedError`.** A downgrade
past it is not a supported operation, which is why several migration tests drive
the revisions that bracket a change rather than starting from `head`.

Every schema-altering migration uses `batch_alter_table` so the chain runs against
the SQLite the migration tests use. The CI `migrations` job additionally applies
the whole chain to an empty PostgreSQL 16 database.

**No tables exist for risk assessments or qualification results.** There is no
recommendation to persist.

---

## Authentication and RBAC

### Roles

| Role | Level | Scope |
| --- | --- | --- |
| `EMPLOYEE` | 20 | The floor every account is born with |
| `MANAGER` | 30 | Plus recording and amending certified turnover |
| `ADMIN` | 40 | Plus users and roles, work types, retirement, audit trail |
| `SUPER_ADMIN` | 50 | Plus deleting users |

Level 10 and the gaps between tiers are deliberately free — **do not renumber**.

**Every gate is inclusive.** The one exception that existed — `require_exact_roles`
on the bid-verdict endpoint, refusing `ADMIN` — was removed with the endpoint.
`User.is_exactly` and the frontend's `isExactly`/`canDecideVerdict` went with it.

### Sign-in

Two independent methods, both ending in the same `TokenPair` from the same issuer:
email/password and Google Identity Services (optional). Neither requires the
other. There is no password-reset flow. Passwords are PBKDF2-hashed.

Both paths pass the same two gates in order:

1. **Admission** — fail-closed. The address must sit on a domain in
   `ALLOWED_EMAIL_DOMAINS`, or be named individually in
   `ALLOWED_EMAIL_EXCEPTIONS`. An empty domain list rejects everyone. For Google a
   `hd` hosted-domain claim must also match; an individually excepted address
   short-circuits both checks.
2. **Elevation** — a `RoleAssignment` row for the normalised address decides the
   role the account is born with; without one it is `EMPLOYEE`.

Elevation is evaluated at account creation only. A returning user's role is read
from their `User` row and never re-derived.

Login returns one generic failure for "no such user", "wrong password" and "this
account is Google-only" alike, so an attacker cannot enumerate addresses or
discover which method an account uses.

### Tokens and sessions

Access tokens 15 minutes, refresh 7 days. Refresh rotates: the presented session
is revoked and a fresh pair issued. Deactivation revokes every active session. On
the frontend the access token lives in memory only and the refresh token in
`localStorage`; refresh is deduplicated so concurrent 401s cannot race each other
into invalidating a rotated token.

### How a role is actually assigned

**Automatically, and always at the floor.** `AuthService._create_account` runs on
every registration and every Google first sign-in:

```python
assignment = await self._assignments.get_by_email(normalized)
role = assignment.role if assignment is not None else UserRole.EMPLOYEE
```

So a new account always arrives as `EMPLOYEE`. Nothing needs configuring, and
nobody is promoted by signing up. This matters more than it looks: registration is
open to anyone who can receive mail at an allowed domain, so a default above the
floor would let any colleague self-promote. `test_the_floor_role_needs_no_configuration`
registers three accounts and asserts all three are `EMPLOYEE`;
`test_register_creates_an_employee_and_signs_in` and
`test_sign_in_creates_an_employee` pin the same thing on each path. Lifting the
floor fails all three.

**Two ways to change a role, and they are not interchangeable:**

| | Changes the role an account *has* | Changes the role an account is *born* with |
|---|---|---|
| Where | `/admin` → User management | `/admin/role-assignments` |
| When | any time, immediately | read once at creation, never again |
| Who | anyone already signed in | somebody who has **not** signed in yet |
| Audited | yes, with before/after diff | yes |

The `/admin` screen is the one you want in practice. It was the missing piece: the
`PATCH /admin/users/{id}/role` endpoint had existed and been tested since the
reviews work was removed, but no UI called it — so the only routes to promote
anyone were a hand-written database script or the elevation list. `UserRoleControl`
now does it, and hides rather than disables what the server would refuse (your own
row, or anyone above your own role), so the screen never implies an action that
would fail with 403.

**There is a third route: `backend/scripts/manage.py`.** For an operator without a
browser session, every role operation is available from the command line. Each
subcommand takes the services built by
`infrastructure/operator.build_operator_services` — the same composition the API
uses — and calls the same service methods, so the guards and audit entries are
identical rather than reimplemented. `scripts/create_default_user.py` shares that
same builder, so the two scripts cannot drift from the API.

```
bootstrap  list-users  set-role  pre-provision  revoke-pre-provision  deactivate
```

`bootstrap` is the only one without a required `--actor`: it creates the *first*
administrator, so there is nobody to name. It records a null actor, the same
convention as migration `d4a1e9c5b872`, and refuses the moment any SUPER_ADMIN
exists. `test_bootstrap_refuses_when_a_super_admin_exists` pins that, and
`test_an_admin_cannot_grant_super_admin` /
`test_an_admin_cannot_modify_a_super_admin` pin the inherited guards. The handlers
take injected services rather than opening their own connection, which is what makes
them testable against the suite's `StaticPool` in-memory SQLite — going through
`main()` would build a second engine and reach a different database.

⚠️ Promoting an existing account through `/admin/role-assignments` **silently does
nothing** — the list is consulted once, at creation, and skips addresses that
already have an account. That is deliberate, not a bug.

### Administration guards

An actor may not modify a user more privileged than themselves, nor assign a role
above their own — the same rule applies to the pre-provisioning list, or an
`ADMIN` could pre-provision a `SUPER_ADMIN` address and sign in as it. Nobody may
edit their own row, which would sidestep that rule. Self-deactivation and
self-deletion are refused. A consumed role assignment cannot be revoked, because
the account it created already carries its role.

---

## Observability

| Piece | State |
| --- | --- |
| structlog JSON logging | Live, request-scoped via `ObservabilityMiddleware` |
| `ObservabilityMiddleware` | **Now registered.** Was imported but never added, so `x-request-id` and the Prometheus counters were dead code |
| `GET /metrics` | Live behind Basic Auth; 404 when `METRICS_ENABLED=false` |
| `GET /admin/api-usage` | Live and reporting real numbers — verified 29 requests with a status and method breakdown |
| `POST /observability/logs` | Live, anonymous, rate-limited per entry; the limiter lives on `app.state`, not a module global, so a test or reload with a different budget is not served the first one |
| Rate limiter | `FixedWindowRateLimiter`, in-process, not durable, explicitly **not a security boundary** |
| Sentry / OpenTelemetry | Live, opt-in by DSN / endpoint |

The browser client batches at most 50 entries every 10 seconds, caps its queue at
200, uses `keepalive` on page-hide, and permanently disables itself on 404 —
correctly reading a disabled endpoint as a configuration answer rather than a
transient error.

---

## Configuration

| Template | Copy to | Read by |
| --- | --- | --- |
| `.env.backend.example` | `backend/.env` | the API and Alembic |
| `.env.frontend.example` | `frontend/.env.local` | `next dev` / `next build` on the host |
| `.env.example` | `.env` | Docker Compose only |

Every backend setting has a default. Settings that matter:

| Variable | Why |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Must match `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — the backend verifies token audience |
| `ALLOWED_EMAIL_DOMAINS` | Empty rejects every sign-in |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | Read by migration `d4a1e9c5b872`. Set before migrating |
| `JWT_SECRET` | 32+ characters, not the template default |
| `DATABASE_URL` | Host is `postgres` under Compose, `localhost` natively |
| `EMBEDDING_BACKEND` | `fastembed` downloads a model on first boot; `hash` is deterministic and offline |
| `METRICS_PASSWORD` | Separate Basic Auth secret, 16+ characters in production |
| `ENABLE_DOCUMENT_WORKER` | The background workers. `false` on serverless, where there is no long-running process |
| `WARM_EMBEDDINGS_ON_STARTUP` | `false` on constrained deployments |

`NEXT_PUBLIC_*` is inlined by `next build`, so under Compose it arrives as a
**build arg** from the root `.env`. Changing one needs
`docker compose up -d --build frontend`, not a restart.

### Production release gates

Enforced at startup when `ENVIRONMENT=production`, in `core/config.py`, all
aggregated into one `RuntimeError`:

- `JWT_SECRET` 32+ chars and not the template default
- `CORS_ALLOW_ORIGINS` explicitly supplied, non-empty, no `*`
- `DATABASE_URL` explicitly supplied and PostgreSQL
- `ALLOWED_EMAIL_DOMAINS` non-empty
- enabled metrics use a separate password of 16+ characters

---

## Tests

**555 tests pass.** Backend tests need no external services: the integration suite
runs against in-memory SQLite, an in-memory Qdrant and a deterministic hash
embedding provider.

### Unit suites

| Suite | Covers |
| --- | --- |
| `test_eligibility_financial` (19) | Turnover averaging, `min(V/N, V)`, insufficient-years handling |
| `test_eligibility_technical` (18) | Work-type cascade and the similar-work value rules |
| `test_eligibility_precedence` (13) | Status resolution when rules disagree |
| `test_eligibility_fingerprint` (14) | Fingerprint stability and staleness detection |
| `test_work_type_cascade` (15) | EXACT → LEXICAL → SEMANTIC, grading bands |
| `test_work_type_seed` (14) | Seed-file parsing, alias counts, normalisation collisions |
| `test_project_workbook` (23) | Portfolio workbook parsing |
| `test_email_domain` (19) | Admission, exceptions, normalisation, fail-closed |
| `test_security` (13) | PBKDF2 round-trip, token type and tamper rejection, role gates |
| `test_rate_limit` (14) | Windowing, cost accounting, key capping, payload bounding |
| `test_foundations` (11) | Every production release gate |
| `test_retirement_selection` (14) | Which tenders are retirable and why |
| `test_roles` (8) | Exact levels, strict ordering, inclusive comparison |
| Others | BOQ parser, constraints, extraction parsing, hash embeddings, storage traversal, financial years, durations, Vercel entrypoint |

### Integration suites

| Suite | Covers |
| --- | --- |
| `test_auth_api` (29) | Both sign-in paths, admission, deactivation, refresh rotation, logout |
| `test_project_import_api` (19) | Multi-workbook import, per-row outcomes, one audit entry per batch |
| `test_eligibility_api` (13) | Screening over HTTP, staleness, role gates, the indeterminate invariant |
| `test_role_assignments` (15) | Birth role, consumption, every admin guard |
| `test_retirement_api` (21) | Preview, batch retire, audit |
| `test_migrations` (17) | Role collapse, password drop/restore, review backfill, bootstrap idempotency, the audit restore, and a check that `tender_reviews` is *gone* at head |
| `test_observability` (14) | Metrics auth, anonymous ingestion, rate limiting, truncation |
| `test_admin` (11) | Privilege guards, session revocation, stats, health, usage, audit reads |
| Others | Analyst-free decision pipeline, document pipeline, extraction, ingestion, projects, repositories, stats, tenders, work types, seed load |

### Frontend verification

Playwright scripts in `frontend/scripts/`, run with `node scripts/<name>.mjs`.
**Not part of CI** — they need a browser and a running stack.

---

## Frontend

### Routes

| Route | Purpose |
| --- | --- |
| `/` | Landing page (server component, prerendered) |
| `/login`, `/register` | Email/password with optional Google sign-in |
| `/dashboard` | Portfolio overview, eligibility breakdown, screening backlog |
| `/tenders`, `/tenders/[id]`, `/tenders/upload` | List, screening detail, ingestion |
| `/projects` | Past-project corpus |
| `/turnover` | Certified turnover, MANAGER+ |
| `/admin`, `/admin/role-assignments`, `/admin/audit-logs` | Administration |
| `/profile` | The signed-in user's account |
| `/design/tokens`, `/design/primitives` | Theme and component reference |

No `middleware.ts`, no route handlers. Every route is a client component behind
`RequireAuth`.

### API client

`lib/api.ts` resolves its base URL in three steps: `NEXT_PUBLIC_API_BASE_URL`,
then a `localStorage["ti.apiBase"]` runtime override, then same-origin. It
normalises a trailing `/api` back to bare origin except for the local Docker
gateway, and rejects a non-http(s) scheme so a literal `"undefined"` cannot become
a same-origin request. It **no longer throws at import time** — that previously
broke the whole build with a misleading prerender error; failure is deferred to a
user-actionable `ApiError`.

`apiRequest` sends the bearer token and on 401 makes **exactly one** retry after
refreshing. The access token is memory-only; the refresh token is persisted.

### Theme

Tokens live in `src/app/globals.css` under Tailwind v4's `@theme`, redefined for
dark under `html[data-theme="dark"]`. `npm run lint` fails on a raw hex, `rgb()`
or `hsl()` anywhere in `src`.

### Auth guards

Entirely client-side in `components/layout/RequireAuth.tsx`. It reads
`useAuth()`, redirects only when `status === "anonymous"`, renders a skeleton
while `status === "loading"` — which is what stops a reload flashing the login
screen — and renders an explanatory empty state when `minRole` is not met.

**`minRole` is presentation only.** A hidden route is not a secured one. The
backend enforces every check.

---

## Known limitations

Ordered by operational severity.

1. **`ANALYZED` and `REVIEWED` are unreachable.** Defined, transitionable, and
   never entered. `ARCHIVED` is reachable through exactly one ADMIN route.
2. **Re-extraction destroys manual corrections.** `ExtractionService.extract`
   builds a fresh `TenderMetadata` and upserts all ten fields, and deletes the
   BOQ outright. Since no correction endpoint exists this is latent, but any
   future correction feature must handle it first.
3. **`GEMINI_API_KEY` is inert.** The setting exists, the LLM port exists, and no
   service constructs a provider. The `AnalystReport` DTO was removed. Remove the
   setting or the feature.
4. **`COMPANY_NET_WORTH` is gone** (FR-303 retired). `thresholds.py` does not
   define it and no code reads net worth.
5. **`SMTP_*` and `NOTIFICATION_*` settings are dead.** `SmtpEmailSender` was
   deleted with the notification ledger; the settings remain in `config.py`.
6. **The qualification rule that ignores similarity is gone** with the
   recommendation engine, so that whole class of drift closed with it.
7. **`tender_metadata.fields` is one JSON column.** Field-level correction is not
   supported at the API level.
8. **Anonymous log ingestion collapses to one bucket behind the shipped nginx.**
   The limiter keys on socket address, which behind the proxy is the proxy.
   `observability.py` documents this candidly and states it is not a security
   boundary.
9. **Playwright verification is not in CI.** The workflows that lint, typecheck,
   build and migrate are; the browser scripts are not.
10. **`next.config.ts` is seven lines** and sets only `reactStrictMode`. There is
    no rewrite, so all API traffic is cross-origin and CORS is load-bearing.

---

## Open questions

Decisions a human must make.

1. **Is the bid-recommendation product being revived?** If yes, `f0e1d2c3b4a5` was
   the wrong direction and the deleted engines need restoring from git. If no,
   `ANALYZED` and `REVIEWED` should be retired from the enum so the lifecycle stops
   advertising states the product does not have.
2. **Should re-extraction preserve corrections?** Currently it cannot, because
   there is nothing to preserve. Answer before adding a correction feature.
3. **What is the real N in the financial rule?** `min(V/N, V)` implies a required
   number of years that no current source states. `TURNOVER_AVERAGING_YEARS = 3`
   is the averaging window, not N.
4. **Should `INDETERMINATE` be resolvable in-app?** It currently routes out of the
   system entirely. A "supply the missing figures" affordance is the obvious next
   feature.
5. **Are the retired settings worth removing?** `GEMINI_API_KEY`, `SMTP_*` and
   `NOTIFICATION_*` are documented in `.env.backend.example` and do nothing.
6. **Where do tender documents live in production?** The API filesystem is
   ephemeral on every free tier. Object storage is the real fix.
7. **Should `/tenders/{id}/boq/analytics` come back?** BOQ items are readable but
   not summarised.
