# Repository context — Tender Intelligence Platform

Onboarding reference for the codebase at `Smart-Tendor`. Written from a full read of
`README.md` and a file-by-file audit of the backend and frontend source.

**Source of truth.** `README.md` is the specification used throughout this document.
Code docstrings cite a PRD (`FR-xxx`, `NFR-xxx`, `§x.x`) and a `docs/decisions/`
directory; neither exists in this repository. Where code and README disagree, the
divergence is recorded in [Known drift](#known-drift), not silently reconciled.

---

## Contents

- [What the platform does](#what-the-platform-does)
- [Stack and services](#stack-and-services)
- [Architecture map](#architecture-map)
- [End-to-end tender flow](#end-to-end-tender-flow)
- [API contract inventory](#api-contract-inventory)
- [Decision logic](#decision-logic)
- [Lifecycle state machine](#lifecycle-state-machine)
- [Data model](#data-model)
- [Authentication and RBAC](#authentication-and-rbac)
- [Configuration](#configuration)
- [Deployment topology](#deployment-topology)
- [Tests](#tests)
- [Frontend](#frontend)
- [Known drift](#known-drift)
- [Open questions](#open-questions)

---

## What the platform does

Decision support for bid / no-bid analysis of construction tenders, built for
Maheshwari Computer.

The platform ingests a tender, extracts its commercial and eligibility terms, scores it
against the company's declared capacity and its own past projects, and returns a
`GO` / `REVIEW` / `NO_BID` recommendation with the reasoning attached. A manager signs
off. Every state change is written to an audit log.

Two invariants govern the design:

- **The scoring is deterministic.** The AI analyst explains a decision; it never changes
  one. The verdict, win probability and confidence are copied verbatim from the rules
  engine into the report.
- **Fail toward caution.** `UNKNOWN` over a guess, `MEDIUM` over dismissal, offline
  fallback over failure, an audit entry on every state change.

Recommendations are never persisted. Every read recomputes them from live metadata, so a
recommendation cannot go stale. A recorded human *verdict* can, and is flagged when it
predates a later correction.

---

## Stack and services

| Layer | Technology |
| --- | --- |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Web | Node 22 · Next.js 16 (App Router) · React 19 · Tailwind CSS 4 |
| Data | PostgreSQL 16 · Qdrant |
| Embeddings | fastembed · `BAAI/bge-small-en-v1.5` (384-d), with a deterministic offline hash backend |
| Extraction | pdfplumber / PyMuPDF · openpyxl for spreadsheet import |
| AI analyst | Google Gemini — optional, degrades gracefully when absent |
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
pytest                       # no live database needed
ruff check .
ruff format --check .
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
boundary holds — `domain/` imports nothing from `application/`, `infrastructure/` or
`api/`.

```
backend/src/tender_intel/
  domain/          entities, enums, decision engines, exceptions, interfaces
  application/     use-case services orchestrating the domain
  infrastructure/  SQLAlchemy repos, vector store, extraction, LLM, observability
  api/             FastAPI routers, schemas, dependencies
  core/            env-sourced settings + DI container
frontend/src/
  app/             Next.js App Router routes
  components/      screen and design-system components
  lib/             API client, auth, role and status helpers
scripts/           setup + dev launchers (PowerShell and Bash)
docker/nginx/      reverse proxy config
```

Roughly 10,300 lines of backend Python across 152 files.

### Layer inventory

| Layer | Contents |
| --- | --- |
| Domain | 9 entities, 6 enums, 3 decision engines, `thresholds.py`, repository ports, value objects, 2 domain services (`email_domain`, `staleness`) |
| Application | 13 services, 10 DTO modules |
| Infrastructure | 7 SQLAlchemy repos, Qdrant store, PDF/Excel extraction, Gemini client, observability, download worker |
| API | 14 routers, 12 schema modules, DI dependencies, centralised error mapping |
| Core | Pydantic settings with production release gates, DI container |

One seam worth knowing: `application/services/decision_service.py` imports `parse_min_value`
and `parse_days` from `infrastructure/extraction/`. That direction is legal, but the
parsing is decision logic and its siblings live in `domain/decision/clause_scan.py`.

---

## End-to-end tender flow

1. **Register.** `POST /tenders` writes a `Tender` at `REGISTERED`. Bulk import via
   `POST /tenders/import` parses an xlsx and, when a row carries a source URL, queues a
   document for download.
2. **Acquire.** A document arrives by URL (status `PENDING`) or by direct upload. The
   background worker polls every 15 seconds, downloads, SHA-256 hashes and stores it.
   First success advances the tender to `DOWNLOADED`; a direct upload advances it
   synchronously.
3. **Extract.** `POST /tenders/{id}/extract` reads the stored file, pulls text through
   pdfplumber or PyMuPDF on a worker thread, runs the rule-based extractor for the ten
   metadata fields, parses BOQ tables, and advances to `PARSED`.
4. **Match.** `MatchingService` embeds a query built from the tender title plus four
   metadata fields, searches Qdrant, and marks each candidate eligible or not against the
   minimum work value parsed from the eligibility text. Eligible candidates sort first,
   then by descending similarity.
5. **Decide.** `POST /tenders/{id}/analyze` gathers metadata, portfolio and best eligible
   similarity, then runs qualification → risk → recommendation and advances to `ANALYZED`.
6. **Narrate.** `GET /tenders/{id}/report` recomputes the decision, asks Gemini for five
   prose sections, and falls back to a deterministic offline generator on any failure or
   malformed output. Verdict, win probability and confidence are never read from the model.
7. **Review.** An employee records corrections, which rewrite metadata at confidence 1.0
   and stamp `updated_at`. A manager records a verdict, which advances to `REVIEWED`.

---

## API contract inventory

Forty-four endpoints, read from the routers. Auth column: **none** is unauthenticated,
**Auth** is any active signed-in user, a role name is the inclusive minimum via
`require_role`, and **exact** is `require_exact_roles` with no upward inheritance.

### Health, stats, observability

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| GET | `/health` | none | — | `HealthResponse` |
| GET | `/stats` | Auth | — | `OperationalStatsResponse` |
| GET | `/metrics` | HTTP Basic | — | Prometheus text; 404 when disabled |
| POST | `/observability/logs` | none | `FrontendLogBatch` | 202 `LogIngestResponse` |

### Auth

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| POST | `/auth/google` | none | `GoogleLoginRequest` | `TokenResponse` |
| POST | `/auth/register` | none | `RegisterRequest` | 201 `TokenResponse` |
| POST | `/auth/login` | none | `LoginRequest` | `TokenResponse` |
| POST | `/auth/refresh` | none | `RefreshRequest` | `TokenResponse` |
| POST | `/auth/logout` | none | `LogoutRequest` | 204 |
| GET | `/auth/me` | Auth | — | `UserResponse` |

### Tenders and documents

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| POST | `/tenders` | EMPLOYEE | `TenderCreateRequest` | 201 `TenderResponse` |
| GET | `/tenders` | Auth | `limit`, `offset`, `status`, `search` | paged `TenderResponse` |
| GET | `/tenders/{tender_id}` | Auth | — | `TenderResponse` |
| PATCH | `/tenders/{tender_id}` | EMPLOYEE | `TenderPatchRequest` | `TenderResponse` |
| DELETE | `/tenders/{tender_id}` | EMPLOYEE | — | 204 |
| POST | `/tenders/import` | EMPLOYEE | multipart file (xlsx) | `BulkImportResponse` |
| POST | `/tenders/{tender_id}/documents` | EMPLOYEE | `DocumentFromUrlRequest` | 201 `DocumentResponse` |
| POST | `/tenders/{tender_id}/documents/upload` | EMPLOYEE | multipart file | 201 `DocumentResponse` |
| GET | `/tenders/{tender_id}/documents` | Auth | — | `DocumentResponse[]`, unpaged |
| GET | `/documents/{document_id}` | Auth | — | `DocumentResponse` |
| POST | `/documents/{document_id}/retrigger` | EMPLOYEE | — | `DocumentResponse` |

### Extraction, matching, decision, analyst

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| POST | `/tenders/{tender_id}/extract` | EMPLOYEE | `document_id` query, optional | `ExtractionResponse` |
| GET | `/tenders/{tender_id}/metadata` | Auth | — | `MetadataResponse`, 404 if absent |
| GET | `/tenders/{tender_id}/boq` | Auth | — | `BOQItemResponse[]`, unpaged |
| GET | `/tenders/{tender_id}/boq/analytics` | Auth | — | `BOQAnalyticsResponse` |
| GET | `/tenders/{tender_id}/matches` | Auth | `top_k` 1–50, default 10 | `MatchResponse` |
| POST | `/tenders/{tender_id}/analyze` | EMPLOYEE | — | `DecisionResponse` |
| GET | `/tenders/{tender_id}/recommendation` | Auth | — | `DecisionResponse` |
| GET | `/tenders/{tender_id}/report` | Auth | — | `AnalystReportResponse` |

### Past projects

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| POST | `/projects` | EMPLOYEE | `PastProjectCreateRequest` | 201 `PastProjectResponse` |
| POST | `/projects/from-document` | EMPLOYEE | multipart file | 201 `PastProjectResponse` |
| GET | `/projects` | Auth | `limit`, `offset` | paged `PastProjectResponse` |
| GET | `/projects/{project_id}` | Auth | — | `PastProjectResponse` |
| PATCH | `/projects/{project_id}` | EMPLOYEE | `PastProjectPatchRequest` | `PastProjectResponse` |
| DELETE | `/projects/{project_id}` | EMPLOYEE | — | 204 |
| POST | `/projects/backfill` | ADMIN | — | `BackfillResponse` |

### Reviews

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| POST | `/tenders/{tender_id}/corrections` | EMPLOYEE | `CorrectionCreateRequest` | 201 `ReviewResponse` |
| POST | `/tenders/{tender_id}/verdict` | MANAGER or SUPER_ADMIN, **exact** | `VerdictCreateRequest` | 201 `ReviewResponse` |
| GET | `/tenders/{tender_id}/reviews` | Auth | — | `ReviewResponse[]`, unpaged |
| GET | `/reviews/pending` | EMPLOYEE | `limit`, `offset` | paged `TenderResponse` |

### Admin

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| GET | `/admin/users` | ADMIN | `limit`, `offset` | paged `UserResponse` |
| GET | `/admin/users/{user_id}` | ADMIN | — | `UserResponse` |
| PATCH | `/admin/users/{user_id}/role` | ADMIN | `RoleUpdateRequest` | `UserResponse` |
| PATCH | `/admin/users/{user_id}/active` | ADMIN | `ActiveUpdateRequest` | `UserResponse` |
| DELETE | `/admin/users/{user_id}` | SUPER_ADMIN | — | 204 |
| GET | `/admin/role-assignments` | ADMIN | `limit`, `offset` | paged `RoleAssignmentResponse` |
| POST | `/admin/role-assignments` | ADMIN | `RoleAssignmentCreateRequest` | 201 `RoleAssignmentResponse` |
| DELETE | `/admin/role-assignments/{assignment_id}` | ADMIN | — | 204 |
| GET | `/admin/audit-logs` | ADMIN | `limit`, `offset`, `actor_id`, `entity_type`, `action`, `date_from`, `date_to` | paged `AuditLogResponse` |
| GET | `/admin/stats` | ADMIN | — | `PlatformStatsResponse` |
| GET | `/admin/system-health` | ADMIN | — | `SystemHealthResponse` |
| GET | `/admin/api-usage` | ADMIN | — | `ApiUsageResponse` |

`GET /stats` and `GET /admin/stats` are deliberately separate. The former returns tender
totals by lifecycle state, past-project count and pending reviews to any authenticated
user. The latter is ADMIN-only and carries the user and account figures `/stats` omits.

### Error mapping

Centralised in `api/errors.py`. Bodies stay generic; full detail is logged server-side.

| Domain exception | Status |
| --- | --- |
| `EntityNotFoundError` | 404 |
| `LiveUserExistsError`, `AssignmentConsumedError`, `DuplicateEntityError`, `InvalidStatusTransitionError` | 409 |
| `AuthenticationError`, `InvalidTokenError` | 401 with `WWW-Authenticate: Bearer` |
| `InactiveUserError`, `ForbiddenDomainError`, `PermissionDeniedError` | 403 |
| `DomainValidationError` | 422 |
| unmapped `DomainError` | 500 |

There is no 400 anywhere in the map. **422 is overloaded**: it is FastAPI's
request-validation status *and* the mapping for `DomainValidationError`, which is what a
caller gets for asking an unparsed tender to analyse. Callers that can distinguish the two
should pass a context override rather than rely on generic wording.

---

## Decision logic

Three deterministic engines in `backend/src/tender_intel/domain/decision/`. They read
every constant from `thresholds.py` and never inline a numeric literal, so the values can
later become administrator-managed configuration. All arithmetic is exact `Decimal`
constructed from strings.

### Risk

Six categories, each scored `NONE` / `LOW` / `MEDIUM` / `HIGH` and mapped onto a 0–10 scale.

| Category | What it flags |
| --- | --- |
| `PERFORMANCE_GUARANTEE` | Guarantee demanded as a percentage of tender value |
| `LIQUIDATED_DAMAGES` | Penalty exposure for delay |
| `OEM_DEPENDENCY` | Reliance on a single original manufacturer |
| `SHORT_COMPLETION_TIME` | Delivery window too tight for the value |
| `HIGH_EMD` | Earnest money deposit disproportionate to tender value |
| `SPECIAL_CLAUSES` | Non-standard terms needing a human read |

Severity scores: `HIGH` 8.5, `MEDIUM` 5.0, `LOW` 2.0, `NONE` 0.0.

Bands. Performance guarantee and liquidated damages share a percentage band: above 10
percent `HIGH`, 5 to 10 inclusive `MEDIUM`, below 5 `LOW`. EMD uses its own: above 5
percent `HIGH`, 2 to 5 inclusive `MEDIUM`, below 2 `LOW`. Short completion is `HIGH` only
when days are under 90 **and** tender value is above 50 lakh — a strict conjunction, never
an OR — then `MEDIUM` under 180 days.

A keyword detected but with an unparseable magnitude falls back to `MEDIUM`. High EMD is
the single documented exception, where an unparseable clause is `LOW`.

Aggregation is `max`, and the overall category is the category of the highest-scoring
finding. One consequence to know: a single `HIGH` at 8.5 alone routes a tender to `REVIEW`,
while six `MEDIUM` findings at 5.0 route nowhere. `thresholds.py` marks the choice
`INFERRED` and acknowledges it as lossy but acceptable for v1.

### Qualification

Three eligibility rules checked against the company's declared capacity. A figure the
company has not declared **fails** the rule rather than passing it silently.

| Rule | Test |
| --- | --- |
| `work_value` | Highest-value single past project meets the required value |
| `average_annual_turnover` | Turnover at or above 150 percent of tender value |
| `net_worth` | Non-negative, or at or above a supplied required percentage |

The required work value comes from the tender's own eligibility text when parseable;
otherwise a configurable percentage of tender value, currently defaulting to 80 percent
and tagged in-code as an unconfirmed product placeholder.

`qualified` requires all three rules to pass.

### Recommendation

Ordered rules, first match wins.

| Rule | Outcome |
| --- | --- |
| Qualification failed | `NO_BID` |
| Overall risk score above 8.0 | `REVIEW` |
| Similarity above 0.85 | `GO` |
| Eligibility rules supplied, similarity at or above 0.40 | `REVIEW` |
| Eligibility rules supplied, similarity below 0.40 | `NO_BID` |
| Qualified, risk acceptable, no eligibility rules | `GO` |

Alongside the verdict the engine returns:

- **Win probability** — base 70, plus 15 above similarity 0.75, minus 20 below 0.55, linear
  interpolation between those anchors, minus 3 per risk point, plus 10 when turnover
  exceeds 3× tender value, plus 5 when net worth exceeds 30 percent of tender value.
  Clamped 10 to 95 inclusive, and 0 for `NO_BID`.
- **Confidence** — base 1.0 less 0.1 for each of exactly three missing fields (completion
  period, EMD, tender value), then capped by the mean of those three extraction
  confidences, bounded 0.1 to 1.0.
- **Pros, cons and a document checklist**, derived from the passing rules and the elevated
  risk categories.

### Constant provenance

`thresholds.py` tags every value. Three are marked `INFERRED` against rulings in a
`docs/decisions/` directory that is not in this repository:

| Constant | Value | Ruling |
| --- | --- | --- |
| `RISK_AGGREGATION` | `max` | C1 |
| `WIN_INTERMEDIATE_SLOPE` | 175.0 | C2 |
| `NET_WORTH_MINIMUM` | 0 | C3 |

One is an explicit placeholder: `WORK_VALUE_REQUIRED_PCT_DEFAULT` at 80 percent.

---

## Lifecycle state machine

Nothing is analysed before it is parsed, and no recommendation exists before the engines
have run. The lifecycle enforces that ordering.

```
REGISTERED → DOWNLOADED → PARSED → ANALYZED → REVIEWED
```

| State | Meaning |
| --- | --- |
| `REGISTERED` | Tender recorded; source documents not yet fetched |
| `DOWNLOADED` | Documents retrieved and stored |
| `PARSED` | Text and fields extracted from those documents |
| `ANALYZED` | Risk, qualification and recommendation engines have run |
| `REVIEWED` | A manager has recorded a verdict |
| `ARCHIVED` | Closed. Terminal — nothing transitions out of it |

Transitions as implemented in `domain/enums/tender_status.py`:

| From | Allowed targets |
| --- | --- |
| `REGISTERED` | `DOWNLOADED`, `ARCHIVED` |
| `DOWNLOADED` | `PARSED`, `ARCHIVED` |
| `PARSED` | `ANALYZED`, `ARCHIVED` |
| `ANALYZED` | `REVIEWED`, `PARSED`, `ARCHIVED` |
| `REVIEWED` | `ANALYZED`, `ARCHIVED` |
| `ARCHIVED` | none |

The `REVIEWED → ANALYZED` edge is what makes re-analysis after a correction possible. The
`ANALYZED → PARSED` edge is reachable by re-extracting an analysed tender.

Documents carry their own status, independent of the tender:
`PENDING` → `DOWNLOADING` → `DOWNLOADED`, or `FAILED`. There is no transition guard on
this one.

### Which stage each operation admits

| Operation | Admitted from |
| --- | --- |
| Extraction | any status; the advance to `PARSED` silently no-ops when illegal |
| Analysis | `PARSED`, `ANALYZED`, `REVIEWED` |
| Correction | `PARSED`, `ANALYZED`, `REVIEWED` |
| Verdict | `ANALYZED`, `REVIEWED` |

### Human review

A review record is explicitly one of two kinds, never inferred:

- **`CORRECTION`** — someone fixed an extracted field. No decision was made and the tender
  does not move. Corrected values are written back at confidence 1.0 with source
  `review:correction`, so later analysis operates on the corrected data.
- **`VERDICT`** — a manager decided (`APPROVED` / `REJECTED`). This is the bid decision. It
  may carry corrections, applied first, and it advances the tender.

Keeping the distinction explicit means review history and audit diffs never have to guess
what a row meant, and a correction can never be misread as a decision.

The pending queue is the `ANALYZED` bucket. A verdict advances a tender out of it; a
correction deliberately does not, so a corrected tender stays queued until somebody
actually decides on it.

### Staleness

A verdict recorded before a later correction is marked stale rather than silently trusted.
The comparison is `metadata.updated_at > latest_verdict.created_at`, strict, so an equal
pair reads as current. `TenderMetadata.touch()` stamps the timestamp explicitly on the
Python clock rather than leaving it to the ORM, because a database-sourced timestamp
(second-granular on SQLite, transaction-start on PostgreSQL) could make a correction read
as *older* than the verdict it invalidated.

`verdict_is_stale` rides on `DecisionResponse`, `AnalystReportResponse` and every
`ReviewResponse`. It is a warning only — nothing is recomputed, invalidated or hidden.

---

## Data model

Ten tables. All primary keys are UUID. Money is `Numeric(20,2)`, quantities and rates
`Numeric(20,4)` — exact decimal end to end, never float. Enums are stored as their string
value for portability across PostgreSQL and the SQLite used in tests.

| Table | Key relationships |
| --- | --- |
| `users` | unique `email`, unique `google_sub`, nullable `hashed_password` |
| `role_assignments` | `assigned_by` and `consumed_user_id` → `users`, `SET NULL`; unique `email` |
| `user_sessions` | `user_id` → `users`, `CASCADE`; unique `refresh_token_hash` |
| `tenders` | unique `tender_number`; indexed `status` |
| `tender_documents` | `tender_id` → `tenders`, `CASCADE` |
| `tender_metadata` | `tender_id` → `tenders`, `CASCADE`, **unique** (one row per tender); ten fields in a single JSON column |
| `boq_items` | `tender_id` → `tenders`, `CASCADE` |
| `past_projects` | standalone; indexed `work_value` and `category` |
| `tender_reviews` | `tender_id` → `tenders` `CASCADE`; `reviewer_id` → `users`, no delete rule |
| `audit_logs` | standalone; `actor_id` is a bare `Uuid` with no foreign key, so a deleted user never cascades away their audit trail |

### The ten metadata fields

`work_name`, `estimated_value`, `emd_amount`, `tender_fee`, `closing_date`,
`completion_period`, `location`, `department`, `eligibility_criteria`, `scope_of_work`.

Each is an `ExtractedField` carrying a value, a confidence and a source. Absent values are
`UNKNOWN`, never guessed. Rule-based extraction assigns 0.8 confidence to parsed amounts
and dates and 0.7 to free text; a manual correction assigns 1.0.

### Migration chain

Single head, no branches. The DSN comes from application settings, never from
`alembic.ini`, so migrations need `backend/.env` present.

```
df21fab595ca  initial schema
  → a1c4e07b91d2  collapse ANALYST and VIEWER into EMPLOYEE
  → b7f39d5a2e60  drop password authentication
  → c2d8b6f4173a  create role_assignments
  → d4a1e9c5b872  bootstrap the first SUPER_ADMIN
  → e7c3a5d18f92  split correction from verdict
  → 7690fc277a01  restore password authentication   (head)
```

Two migrations cancel out: `b7f39d5a2e60` drops `hashed_password` and `7690fc277a01` adds
it back nullable, so a fresh database creates, drops and recreates the column.

`d4a1e9c5b872` reads `BOOTSTRAP_SUPER_ADMIN_EMAIL` from application settings at migration
time and seeds a `SUPER_ADMIN` role assignment. It is idempotent, guarded on the normalised
email, skips when the account already exists, and is a no-op when the variable is unset.
**Set it before running the first migration** — changing it afterwards does not rerun the
migration.

Every schema-altering migration uses `batch_alter_table` so the same chain runs against the
SQLite database the migration tests use.

**No tables exist for recommendations, risk assessments or qualification results.** That is
deliberate; see [What the platform does](#what-the-platform-does).

---

## Authentication and RBAC

### Roles

Four roles, hierarchical and inclusive — an endpoint requiring level *N* admits every role
at or above it.

| Role | Level | Scope |
| --- | --- | --- |
| `EMPLOYEE` | 20 | The floor every account is born with. Read tenders, run analysis, record corrections |
| `MANAGER` | 30 | Everything above, plus recording bid verdicts |
| `ADMIN` | 40 | Everything above, plus user management and audit logs |
| `SUPER_ADMIN` | 50 | Full control, including role assignment and user deletion |

`EMPLOYEE` is the floor, not a rejection. Level 10 and the gaps between tiers are
deliberately free for future insertion — **do not renumber**.

**One capability is not inherited upward.** `POST /tenders/{id}/verdict` uses
`require_exact_roles(MANAGER, SUPER_ADMIN)`. An `ADMIN` outranks a `MANAGER` on level but
owns user administration, not the bid decision, so an `ADMIN` is refused. The frontend
mirrors this in `lib/roles.ts` via `canDecideVerdict`.

### Sign-in

Two independent methods, both ending in the same `TokenPair` from the same issuer:
Google Identity Services (optional) and email/password. Neither requires the other. There
is no password-reset flow. Passwords are salted PBKDF2 hashes, never stored in plain text.

Both paths pass the same two gates in order:

1. **Admission** — fail-closed. The address must sit on a domain in
   `ALLOWED_EMAIL_DOMAINS`, or be named individually in `ALLOWED_EMAIL_EXCEPTIONS`. An
   empty domain list rejects everyone. For Google, a `hd` hosted-domain claim must also
   match; an individually excepted address short-circuits both checks.
2. **Elevation** — a `RoleAssignment` row for the normalised address decides the role the
   account is born with; without one it is `EMPLOYEE`.

Elevation is evaluated at account creation only. A returning user's role is read from their
`User` row and never re-derived, so a later assignment cannot silently change a live
account. Live users are changed with `PATCH /admin/users/{id}/role` instead.

Manual sign-up refuses a duplicate email outright rather than attaching a password to an
existing Google-only account. Login returns one generic failure for "no such user", "wrong
password" and "this account is Google-only" alike, so an attacker cannot enumerate
addresses or discover which method an account uses.

### Tokens and sessions

Access tokens are 15 minutes, refresh tokens 7 days. Refresh rotates: the presented
session is revoked and a fresh pair issued. Deactivation revokes every active session.
On the frontend the access token lives in memory only and the refresh token is persisted
to `localStorage`; refresh is deduplicated so concurrent 401s do not race each other into
invalidating a rotated token.

### Administration guards

An actor may not modify a user more privileged than themselves, nor assign a role above
their own. The same rule applies to the pre-provisioning list — without it, an `ADMIN`
could pre-provision a `SUPER_ADMIN` address and sign in as it. Self-deactivation and
self-deletion are refused. A consumed role assignment cannot be revoked, because the
account it created already carries its role on the `User` record.

---

## Configuration

All configuration comes from the environment. Three templates, all created by setup:

| Template | Copy to | Read by |
| --- | --- | --- |
| `.env.backend.example` | `backend/.env` | the API and Alembic |
| `.env.frontend.example` | `frontend/.env.local` | `next dev` / `next build` on the host |
| `.env.example` | `.env` | Docker Compose only, for its substitutions |

Every backend setting has a default, so nothing crashes on a missing variable in local
mode. These matter in practice:

| Variable | Why |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Optional Google sign-in. Must match `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — the backend verifies the token audience |
| `ALLOWED_EMAIL_DOMAINS` | Empty rejects every sign-in |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | Read by migration `d4a1e9c5b872`. Set it *before* migrating |
| `JWT_SECRET` | Generated by setup. Must be 32+ characters and not the template default |
| `DATABASE_URL` | Host is `postgres` under Compose, `localhost` natively |
| `GEMINI_API_KEY` | Optional. Without it the AI analyst degrades rather than failing |
| `EMBEDDING_BACKEND` | `fastembed` downloads a model on first boot; `hash` is deterministic and fully offline |
| `QDRANT_API_KEY` | Required with Qdrant Cloud; blank for local Qdrant |
| `METRICS_PASSWORD` | Separate Basic Auth secret for `/metrics` |
| `COMPANY_TURNOVER`, `COMPANY_NET_WORTH` | Feed the qualification engine. Unset means those rules fail — see [Known drift](#known-drift) |

`NEXT_PUBLIC_*` is inlined by `next build`, so under Compose it arrives as a **build arg**
from the root `.env`. Changing one needs `docker compose up -d --build frontend`, not a
restart.

Provider `postgres://` and `postgresql://` URLs are normalised to SQLAlchemy's asyncpg
scheme at startup.

### Production release gates

Enforced at startup when `ENVIRONMENT=production`, in `core/config.py`:

- `JWT_SECRET` must be strong (32+ chars, not the template default)
- `DATABASE_URL` must be explicitly supplied and PostgreSQL
- `CORS_ALLOW_ORIGINS` must be explicitly supplied and cannot contain `*`
- `ALLOWED_EMAIL_DOMAINS` must contain at least one domain
- enabled metrics must use a separate password of at least 16 characters

Failure raises at startup rather than degrading at runtime.

### Pre-provisioning roles

To give someone a role above `EMPLOYEE` before their first sign-in, copy
`scripts/seed_role_assignments.example.sql`, put the addresses in it, and run it once
after migrating. The list is consulted once, at account creation, and never again.

---

## Deployment topology

### Local production-shaped

```bash
docker compose up -d --build --wait
curl http://localhost:8080/health
```

The backend container applies `alembic upgrade head` before uvicorn starts and fails fast
if the migration fails, so the error appears in the deploy log rather than as a runtime
500 with no CORS headers. Entry point is nginx on `:8080`. Uploaded documents and both
data stores use named volumes. `docker compose down` without `-v` preserves them.

For multi-replica paid deployments, move migrations into the platform's single pre-deploy
job before scaling out.

### No-cost split deployment

Checked-in configuration exists for a split topology:

| Piece | Platform | Config |
| --- | --- | --- |
| Frontend | Netlify Free | `netlify.toml` (base `frontend`, publish `.next`) |
| API | Render Free | `render.yaml` + `backend/Dockerfile` |
| PostgreSQL | Neon Free | — |
| Vector search | Qdrant Cloud Free | — |

The Render blueprint disables public metrics on the constrained free service, uses hash
embeddings to stay inside 512 MB, runs migrations during container startup, and checks
`/health`.

The README documents a verified free-tier comparison across Netlify, Render, Koyeb, Vercel
Hobby and Railway, dated 8 September 2026, with the reasoning for each choice. Vercel Hobby
is excluded because it is restricted to personal non-commercial use.

**Document durability caveat.** The application stores tender documents on the API
filesystem. On a free Render service those files disappear on restart, redeploy or
spin-down. Rows remain in Neon and vectors in Qdrant, but file durability needs a paid
persistent disk or a future object-storage adapter. Do not treat the no-cost topology as
production for irreplaceable tenders.

A `backend/vercel.json` and `backend/index.py` also exist, exporting the FastAPI app with
an `/api` prefix-stripping middleware and the worker and embedding warmup disabled.

### Rollback

Frontend rolls back by republishing a previous Netlify deploy. API rolls back through
Render Events. Database prefers a Neon restore or branch from before the migration — do
not run an Alembic downgrade against production until its data-loss behaviour has been
reviewed and a backup exists. Keep application and schema changes backward compatible for
at least one release so an application-only rollback stays safe.

---

## Tests

321 test functions across 5,264 lines. Backend tests need no external services: the
integration suite runs against in-memory SQLite, an in-memory Qdrant and a deterministic
hash embedding provider. `tests/integration/test_migrations.py` drives the real Alembic
chain over a throwaway database.

### Unit suites

| Suite | Covers |
| --- | --- |
| `test_decision_risk` (16) | Every band and boundary, unparseable fallbacks, max aggregation, mitigations |
| `test_decision_recommendation` (19) | All five rules including boundary values, win-probability curve and clamps, confidence penalty, cap and floor |
| `test_decision_qualification` (9) | Each rule, parsed-requirement precedence, the all-three requirement |
| `test_email_domain` (18) | Admission, exceptions, normalisation, subdomain rejection, empty-allowlist rejection |
| `test_security` (14) | PBKDF2 round-trip, token type and tamper rejection, both role gates |
| `test_rate_limit` (14) | Windowing, cost accounting, key capping, context truncation |
| `test_foundations` (12) | Every production release gate |
| `test_roles` (8) | Exact levels, strict ordering, inclusive-upward-only comparison |
| Others | BOQ analytics and parser, constraints, domain invariants, Excel import, extraction parsing, hash embeddings, rule metadata, storage traversal, Vercel entrypoint |

### Integration suites

| Suite | Covers |
| --- | --- |
| `test_auth_api` (29) | Google and password paths, linking, admission, deactivation, refresh rotation, logout |
| `test_reviews` (22) | Correction/verdict split, role gates including ADMIN refusal, stage guards, audit diffs |
| `test_role_assignments` (15) | Birth role, consumption, case-insensitivity, every admin guard |
| `test_migrations` (14) | Role collapse, password drop and restore, verdict backfill, bootstrap idempotency |
| `test_observability` (14) | Metrics auth, anonymous ingestion, rate limiting, truncation |
| `test_admin` (11) | Privilege guards, session revocation, stats, health, usage |
| `test_staleness` (9) | The correct → reanalyse → decide flow, and that a verdict carrying corrections never flags itself |
| Others | Analyst fallback, decision pipeline, document pipeline, extraction, ingestion, projects, repositories, semantic matching, stats, tenders |

### Frontend verification

Playwright scripts in `frontend/scripts/`, run directly with `node scripts/<name>.mjs`.
**Not part of CI.** All except `check-contrast.mjs` need `npm run start` on `:3000`; the
`e2e-*` scripts also need a seeded backend on `:8000`. Requires
`npx playwright install chromium`.

| Script | What it proves |
| --- | --- |
| `screenshot.mjs` | Deterministic capture; warns on horizontal overflow |
| `compare-screenshots.mjs` | Pixel diff at threshold 0 |
| `verify-tokens.mjs` | Every `@theme` token resolves to the exact literal it replaced |
| `check-contrast.mjs` | Every required colour pairing meets WCAG AA |
| `measure-lcp.mjs` | LCP with every candidate in order |
| `smoke-screens.mjs` | Every authenticated screen renders against mocked fixtures |
| `conformance-{static,runtime,states}.mjs` | Source structure, rendered-DOM contrast, loading/empty/error states |
| `e2e-{live,roles,crud,lifecycle}.mjs` | The app and a real backend agree |
| `test-hero-fallback.mjs` | The landing page survives the hero video failing to load |

Captures are deterministic because the script freezes CSS and Framer animation *and*
pauses every `<video>` at frame 0. Without the video freeze, two captures of an unchanged
build differ by roughly 6 percent of pixels.

---

## Frontend

### Routes

| Route | Purpose |
| --- | --- |
| `/` | Landing page |
| `/login`, `/register` | Email/password access with optional Google sign-in |
| `/dashboard` | Portfolio overview and pending work |
| `/tenders`, `/tenders/[id]`, `/tenders/upload` | List, full analysis detail, ingestion |
| `/projects` | Past-project corpus that similarity matching scores against |
| `/reviews` | Pending verdicts queue |
| `/admin`, `/admin/audit-logs`, `/admin/role-assignments` | Administration |
| `/profile` | The signed-in user's account |
| `/design/tokens`, `/design/primitives` | Live theme and component reference. `noindex`, but publicly served |

### API client

`lib/api.ts` is a typed fetch wrapper with transparent refresh-on-401 and exactly one
retry — a 15-minute access token means expiry is routine, and if the refreshed token also
401s the session is genuinely finished. `NEXT_PUBLIC_API_BASE_URL` is required and the
module throws at import time when it is unset. `describeError` maps status codes to
user-facing wording and accepts per-call context overrides for the overloaded 422.

`lib/telemetry.ts` batches browser diagnostics to `POST /observability/logs`, flushing at
most 50 entries every 10 seconds and using `keepalive` on page-hide.

### Theme

Design tokens live in `src/app/globals.css` under Tailwind v4's `@theme`. The palette is
defined once on bare `:root` and redefined for dark under both a media query and an
explicit `[data-theme]` attribute. Contrast ratios are annotated inline per token, with
explicit warnings where a colour fails AA as text (`--color-brand` at 2.88:1 and
`--color-state-go` at 2.52:1 both have dedicated `-ink` variants for that reason).
`npm run lint` fails the build on a raw hex, `rgb()` or `hsl()`.

The landing hero video is the only asset on that page fetched over the network, so it is
the only thing that can fail. `HeroVisual.tsx` swaps in a self-hosted DOM panel when it
does. `onError` alone is insufficient — the `<video>` is server-rendered, so a failure
fires before hydration and media errors do not bubble; the component checks `el.error` and
`networkState` on mount as well.

---

## Known drift

Divergences between `README.md`, in-code documentation and the running implementation.
Recorded, not fixed. Ordered by operational severity.

1. **Company financials default to unset, so every tender scores `NO_BID`.**
   `COMPANY_TURNOVER` and `COMPANY_NET_WORTH` are `None` by default and blank in
   `.env.backend.example`. The turnover and net-worth rules each fail on a missing figure,
   `qualified` requires all three rules, and an unqualified tender is `NO_BID` with win
   probability 0. On a default installation this applies to every tender ever analysed.
   The fail-toward-caution behaviour is correct; the default configuration is what makes
   it total. There is no admin surface for these values and no startup warning.

2. **Re-extraction destroys manual corrections.** `ExtractionService.extract` builds a
   fresh `TenderMetadata` and upserts it, overwriting every field. Corrections written at
   confidence 1.0 are erased with no warning and no audit note. The correction rows survive
   in `tender_reviews`, so history is intact, but the data the engines read reverts. This
   works against the correct → reanalyse → decide flow the review service is built around.

3. **`COMPANY_TURNOVER=` empty in the template may crash startup.** The field is typed
   `Decimal | None`; an empty string satisfies neither branch. Unverified — there is no
   usable virtual environment in the repo to execute against.

4. **Two `.env` template values fail the production release gates.**
   `JWT_SECRET=change-me-in-production` and `METRICS_PASSWORD=change-me-in-production` are
   both rejected in production, and `METRICS_ENABLED` defaults to `true`. Copying the
   template and setting `ENVIRONMENT=production` produces a hard startup failure. The
   fail-fast is intentional; the templates carry no inline signal.

5. **`ARCHIVED` is specified but unreachable.** Six transition edges lead to it and nothing
   calls `transition_to(ARCHIVED)`. There is no archive endpoint and no status field on
   `TenderPatchRequest`.

6. **The README's lifecycle description omits the `ANALYZED → PARSED` edge.** It is present
   in code and reachable by re-extracting an analysed tender.

7. **The README describes the role hierarchy as uniformly inclusive.** One endpoint is not:
   `POST /tenders/{id}/verdict` refuses `ADMIN`. The code documents and tests this
   deliberately in three places; the README's summary does not mention the exception.

8. **`frontend/docs/api-map.md` contradicts the running API.** It states `/auth/register`
   and `/auth/login` "were removed" and that Google is the only way an account is created.
   Both endpoints exist, the README documents them, `setup.md` instructs users to use them,
   and 15 integration tests cover them. The doc was not updated when migration
   `7690fc277a01` restored password auth.

9. **The README cites a CI workflow that does not exist.** It links
   `.github/workflows/ci.yml` and states CI runs pytest, ruff, mypy and the frontend checks
   on every push and pull request. There is no `.github` directory, so nothing is enforced
   automatically.

10. **`docs/decisions/` is missing.** `thresholds.py` points every `INFERRED` tag at it. The
    C1 max-aggregation ruling, the C2 slope of 175.0 and the C3 net-worth floor cite
    reasoning that cannot be retrieved from this repository.

11. **The work-value qualification rule ignores similarity.** `DecisionService` loads past
    projects by plain pagination and the rule takes the single highest-value project
    regardless of category, location or embedding similarity, despite the parameter being
    named `similar_works`.

12. **Qualification silently truncates the portfolio at 200 projects.** The lookup uses
    `PageRequest(limit=MAX_LIMIT)` with `MAX_LIMIT = 200`, with no ordering guarantee that
    the highest-value projects fall in the first page.

13. **`TenderReview.reviewer_id` has no delete rule.** Every other user-referencing foreign
    key specifies `CASCADE` or `SET NULL`. Deleting a manager who has recorded verdicts
    will raise a raw integrity error surfacing as an unhandled 500.

14. **Anonymous log ingestion collapses to one bucket behind the shipped nginx.** The
    limiter keys anonymous callers on the socket address, which behind the reverse proxy is
    the proxy. `observability.py` documents this candidly and states it is not a security
    boundary.

---

## Open questions

Decisions a human must make. Not resolved here.

1. **Where is the PRD?** Code cites `docs/PRD-Tender-Intelligence-Platform.pdf` v1.0
   throughout; it is not in the repository. This document uses the README instead, which
   covers behaviour but not requirement-level intent.
2. **Where is `docs/decisions/`?** Three shipped constants cite rulings from a directory
   that does not exist. Reconstruct, or re-derive from the PRD?
3. **What is the real work-value required percentage?** 80 percent is tagged an unconfirmed
   placeholder and needs bid-team confirmation.
4. **What are the company's turnover and net-worth figures, and where should they live?**
   Currently environment variables with no default, which makes every out-of-box analysis
   `NO_BID`. In-code comments mark admin-managed configuration as post-v1.
5. **Should re-extraction preserve corrections?** Three defensible answers: preserve
   corrected fields, overwrite with a warning, or refuse re-extraction on a corrected
   tender. A product call about whose judgement wins.
6. **Is "similar works" meant literally in the qualification rule?** It currently matches on
   value alone, while the recommendation context already computes a similarity score.
7. **Should `ARCHIVED` be reachable?** Fully specified, completely unreachable. Either an
   endpoint is missing or the state is aspirational.
8. **Is `ADMIN`'s exclusion from bid verdicts intended?** The code asserts and tests it; the
   README describes a uniformly inclusive hierarchy. One of the two is wrong.
9. **Is anonymous log ingestion acceptable in production behind the shipped nginx?** The
   collapsed rate-limit bucket is a documented known limitation someone has to accept.
10. **Should CI be restored?** The README documents a workflow that is not in the repo.
11. **Should `frontend/docs/api-map.md` stay authoritative?** It contradicts the API on
    authentication. Regenerate from the routers, or retire it.
