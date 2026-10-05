# Tender Eligibility Screening Platform

Decision support for **bid / no-bid eligibility screening of construction
tenders**, built for Maheshwari Computer.

The platform ingests a tender, extracts its commercial and eligibility terms, and
screens it against the company's declared financial capacity and its own past
projects. It answers one question — *can we bid this?* — as
`ELIGIBLE` / `NOT_ELIGIBLE` / `INDETERMINATE`, with the reasoning attached. A
manager acts on the result. Every state change is written to an audit log.

The scoring is deterministic. All arithmetic is exact `Decimal`.

---

## Contents

- [What this platform does](#what-this-platform-does)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [API](#api)
- [Configuration](#configuration)
- [Development](#development)
- [Frontend verification](#frontend-verification)
- [Deployment](#deployment)
- [Security](#security)

---

## What this platform does

**It screens tenders for eligibility. It does not produce a bid recommendation,
and it does not collect review verdicts.**

That distinction is load-bearing, so it is worth being explicit about what changed
and why. This system was originally built as a GO / REVIEW / NO_BID
recommendation platform with a risk engine, a win-probability model, an AI analyst
narrative, and a human sign-off queue. Migration `f0e1d2c3b4a5` ("reduce to
eligibility workflow") removed that surface: the review queue, the audit-readable
verdicts, the notification ledger, and the risk/recommendation engines all went
with it. The current product screens eligibility only.

If you are looking for a bid recommendation, a win probability, or a risk score,
none of those exist in this repository. If you are looking for "should we bid this
at all, given what we have actually done and what we actually earn", that is
exactly what this does.

---

## Quick start

One command from a fresh clone. It writes the environment files, collects the
administrator email, optionally configures Google and Gemini, generates service
secrets, builds every service, and starts the stack. Backend startup applies the
migrations.

```powershell
./scripts/setup.ps1        # Windows
```

```bash
./scripts/setup.sh         # macOS / Linux / Git Bash
```

Then open **<http://localhost:8080>**.

You are asked for the administrator email and may optionally configure integrations:

| Prompt | Why it is required |
| --- | --- |
| **Administrator email** | Seeded as the first `SUPER_ADMIN` role assignment. Register that address with email/password or use Google; the account is born `SUPER_ADMIN`. |
| **Google OAuth client ID** | Optional. Enables Google Identity Services alongside email/password. See [frontend/docs/google-sign-in.md](frontend/docs/google-sign-in.md). |
| **Gemini API key** | Optional. Not currently used by any live code path; see [Known limitations](#known-limitations). |

Re-running `setup` is safe: a value you have already set is never overwritten.

**Prerequisites** — Docker Desktop. For native mode, additionally Python 3.12+
and Node 22 (see [.nvmrc](.nvmrc)).

### Native mode (reload on save)

Postgres and Qdrant stay in Docker; the API and the web app run on your host.

```powershell
./scripts/setup.ps1 -Mode native    # once
./scripts/dev.ps1                   # API :8000 + web :3000
```

`setup` points `DATABASE_URL` and `QDRANT_URL` at the Compose service names in
docker mode and at `localhost` in native mode, so one `backend/.env` serves both.

### Unattended

```bash
TI_ADMIN_EMAIL=ops@example.com ./scripts/setup.sh --non-interactive
```

---

## How it works

### Tender lifecycle

Nothing is screened before it is parsed. The lifecycle enforces that ordering.

```
REGISTERED → DOWNLOADED → PARSED → ARCHIVED
```

| State | Meaning |
| --- | --- |
| `REGISTERED` | Tender recorded; source documents not yet fetched. |
| `DOWNLOADED` | Documents retrieved and stored. |
| `PARSED` | Text and fields extracted from those documents. |
| `ARCHIVED` | Closed. Terminal — nothing transitions out of it. |

Transitions as implemented in `domain/enums/tender_status.py`:

| From | Allowed targets |
| --- | --- |
| `REGISTERED` | `DOWNLOADED`, `ARCHIVED` |
| `DOWNLOADED` | `PARSED`, `ARCHIVED` |
| `PARSED` | `ANALYZED`, `ARCHIVED` |
| `ANALYZED` | `REVIEWED`, `PARSED`, `ARCHIVED` |
| `REVIEWED` | `ANALYZED`, `ARCHIVED` |
| `ARCHIVED` | none |

`ANALYZED` and `REVIEWED` are still legal states and the edges between them are
still defined, but **no code path reaches them**. The live workflow ends at
`PARSED` plus a separate eligibility annotation, and `ARCHIVED` is reached by
exactly one route: the ADMIN-only tender retirement endpoint. `ANALYZED` and
`REVIEWED` are retained so an existing database's rows remain readable, and are
filterable on `GET /tenders`.

Documents carry their own status, independent of the tender:
`PENDING` → `DOWNLOADING` → `DOWNLOADED`, or `FAILED`.

### The screening engine

`domain/decision/eligibility.py`. It reads every constant from `thresholds.py` and
never inlines a numeric literal, so the thresholds can later become
administrator-managed configuration without hunting values through the code. All
arithmetic is exact `Decimal`.

Three rules, evaluated together:

| Rule | Test |
| --- | --- |
| **Financial capacity** | The tender's required capital is `min(V/N, V)` where `V` is tender value and `N` is the required number of years. It is compared against the **average certified turnover over the last 3 completed financial years**. |
| **Stage A — work type** | The tender's scope of work is matched against the company's work-type taxonomy: `EXACT` → `LEXICAL` → `SEMANTIC`, first hit wins. |
| **Stage B — similar work** | Past projects completed within the last **7 years**, carrying a matching work type and a value of at least **60%** (one project), **40%** (two), or **30%** (three) of the tender value. |

The result is a three-valued status:

| Status | Meaning |
| --- | --- |
| `ELIGIBLE` | Every rule passed. |
| `NOT_ELIGIBLE` | At least one rule **definitively** failed. |
| `INDETERMINATE` | No rule definitively failed, but at least one could not be decided. |

**`INDETERMINATE` is the important one.** A missing input never resolves into a
pass, and it never collapses into a failure. If turnover has not been entered for
three completed years, or the tender value could not be parsed, or the scope of
work matched no work type, the tender reaches a person. Grouping indeterminate
under "not eligible" would rule out the entire portfolio until an administrator
finished configuring it.

Alongside the status the engine returns a before/after explanation: which rules
failed and in what words, which work types matched and by which method, and which
past projects qualified and in what order.

### Staleness

A screening result records a fingerprint of the inputs it was computed from —
the tender metadata, the turnover window, the work-type candidates, and a counter
that every portfolio mutation bumps. Staleness is **derived by recomputing that
digest**, never stored as a flag, so no code path has to remember to clear it.

`GET /tenders/{id}/eligibility` reports `is_stale` on every read. It is a warning
only: nothing is recomputed, invalidated or hidden, and the recorded result stays
readable until it is replaced by a fresh screening.

### Human review

There is no review queue and no verdict workflow. A screening result is read and
acted on outside the system. What *is* recorded, on every state change, is the
audit trail.

### Access control

Four roles, hierarchical and inclusive — an endpoint requiring level *N* admits
every role at or above it.

| Role | Level | Scope |
| --- | --- | --- |
| `EMPLOYEE` | 20 | The floor every account is born with. Read tenders, upload documents, run extraction, screen for eligibility, manage past projects. |
| `MANAGER` | 30 | Everything above, plus recording and amending certified turnover. |
| `ADMIN` | 40 | Everything above, plus user and role management, the work-type taxonomy, tender retirement, and the audit trail. |
| `SUPER_ADMIN` | 50 | Full control, including deleting users. |

`EMPLOYEE` is the floor, not a rejection. The gaps between levels are deliberate —
do not renumber them.

**Every new account is born `EMPLOYEE`, automatically, with no configuration.**
That is not a default you can forget to set — it is what the code does on every
registration and every Google first sign-in. Self-registration is open to anyone
who can receive mail at an allowed domain, so nothing about signing up grants
anything, and this is pinned by tests that fail if the floor is ever lifted.

**Changing someone's role is done in the application**, on `/admin` under *User
management*. It applies immediately and is written to the audit trail with its
actor and a before/after diff. You do not need a database script or a migration to
promote a colleague.

The `/admin/role-assignments` screen is a different, narrower tool: it decides the
role an account is **born** with, for somebody who has not signed in yet. It is
read exactly once, at creation, and never again — so promoting someone who already
has an account through it would silently do nothing.

There is exactly one gate shape in the application: inclusive. The previous
non-inheriting gate existed to keep bid verdicts away from ADMIN and was removed
with the verdict endpoint.

**Sign-in supports email/password and optional Google Identity Services.** There
is no password-reset flow. Passwords are PBKDF2-hashed and never stored in plain
text. Admission is fail-closed: the address must sit on a domain in
`ALLOWED_EMAIL_DOMAINS`, or be named individually in `ALLOWED_EMAIL_EXCEPTIONS`.
An empty domain list rejects everyone.

---

## Architecture

Clean Architecture. Dependencies point inward; the domain depends on nothing.

```
backend/src/tender_intel/
  domain/          entities, enums, the screening engine, exceptions, interfaces
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

**Guiding principles** — domain-first; a deterministic core; and *fail toward
caution*: `UNKNOWN` over a guess, `INDETERMINATE` over a refusal, offline
fallback over failure, an audit entry on every state change.

### Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Web | Node 22 · Next.js 16 (App Router) · React 19 · Tailwind CSS 4 |
| Data | PostgreSQL 16 · Qdrant (vector search) |
| Embeddings | fastembed · `BAAI/bge-small-en-v1.5` (384-d), with a deterministic offline backend |
| Extraction | pdfplumber / PyMuPDF · openpyxl for spreadsheet import |
| Observability | structlog · Prometheus · OpenTelemetry · Sentry |
| Edge | nginx on `:8080` → web on `:3000`, `/api/` → API on `:8000` |

### Services

| Service | Port | Notes |
| --- | --- | --- |
| `nginx` | 8080 | The entry point. Use this one. |
| `frontend` | 3000 | Next.js. |
| `backend` | 8000 | FastAPI; OpenAPI at `/docs`. |
| `postgres` | 5432 | Healthchecked; `setup` waits on it. |
| `qdrant` | 6333 | Vector store for past-project matching. |

### Screens

| Route | Purpose |
| --- | --- |
| `/` | Landing page. |
| `/login`, `/register` | Email/password access with optional Google sign-in. |
| `/dashboard` | Portfolio overview, eligibility breakdown, screening backlog. |
| `/tenders`, `/tenders/[id]`, `/tenders/upload` | List, screening detail, and ingestion. |
| `/projects` | Past-project corpus that stage B scores against. |
| `/turnover` | Certified turnover evidence, MANAGER+. |
| `/admin`, `/admin/role-assignments`, `/admin/audit-logs` | User and role management, pre-provisioning, and the audit trail. |
| `/profile` | The signed-in user's account. |
| `/design/tokens`, `/design/primitives` | Live theme and component reference. `noindex`, but publicly served. |

---

## API

OpenAPI lives at `http://localhost:8000/docs`. 47 paths.

| Group | Endpoints |
| --- | --- |
| Auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/google` · `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` |
| Tenders | `GET\|POST /tenders` · `GET\|PATCH\|DELETE /tenders/{id}` · `POST /tenders/import` |
| Documents | `POST /tenders/{id}/documents` · `.../upload` · `GET /tenders/{id}/documents` · `GET /documents/{id}` · `POST /documents/{id}/retrigger` |
| Extraction | `POST /tenders/{id}/extract` · `GET /tenders/{id}/metadata` · `GET /tenders/{id}/boq` |
| Screening | `POST\|GET /api/v1/tenders/{id}/eligibility` |
| Past projects | CRUD · `POST /api/v1/projects/import` · `POST /projects/backfill` · work-type tags |
| Turnover | `GET\|POST /api/v1/company-turnover` · `PATCH /{financial_year}` · `POST /import` — MANAGER+ |
| Retirement | `GET /api/v1/tenders/retirement/preview` · `POST /api/v1/tenders/retirement` — ADMIN |
| Admin | Users, role assignments, `GET /admin/audit-logs`, `/stats`, `/system-health`, `/api-usage` |
| Platform | `GET /stats` (any signed-in user) · `GET /health` · `GET /metrics` (Basic Auth) · `POST /observability/logs` |

`GET /stats` returns tender totals by lifecycle state, an eligibility breakdown,
the past-project count and the screening backlog to any authenticated user.
`GET /admin/stats` is separate and ADMIN-only — it carries user and account figures
that `/stats` deliberately omits.

---

## Configuration

All configuration comes from the environment. Three templates:

| Template | Copy to | Read by |
| --- | --- | --- |
| [.env.backend.example](.env.backend.example) | `backend/.env` | the API and Alembic |
| [.env.frontend.example](.env.frontend.example) | `frontend/.env.local` | `next dev` / `next build` on the host |
| [.env.example](.env.example) | `.env` | Docker Compose only, for its `${...}` substitutions |

Every backend setting has a default, so nothing crashes on a missing variable in
local mode. These matter in practice:

| Variable | Why it matters |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Optional Google sign-in. When set, it must match `NEXT_PUBLIC_GOOGLE_CLIENT_ID` because the backend verifies the token audience. |
| `ALLOWED_EMAIL_DOMAINS` | Empty rejects every sign-in. |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | Read by migration `d4a1e9c5b872`. Set it *before* migrating. |
| `JWT_SECRET` | Generated by `setup`. Must be ≥32 characters and not the template default. |
| `DATABASE_URL` | Host is `postgres` under Compose, `localhost` natively. |
| `EMBEDDING_BACKEND` | `fastembed` downloads a model on first boot; `hash` is deterministic and fully offline. |
| `QDRANT_API_KEY` | Required with Qdrant Cloud; leave blank for local Qdrant. |
| `METRICS_PASSWORD` | Separate Basic Auth secret for `/metrics`; production rejects the template value when metrics are enabled. |

`NEXT_PUBLIC_*` is inlined by `next build`, so under Compose it arrives as a
**build arg** from the root `.env` — changing one needs
`docker compose up -d --build frontend`, not a restart.

Production release gates are enforced at startup when `ENVIRONMENT=production`:
`JWT_SECRET` must be strong, `DATABASE_URL` and `CORS_ALLOW_ORIGINS` must be
explicitly supplied, the database must be PostgreSQL, CORS cannot contain `*`,
`ALLOWED_EMAIL_DOMAINS` must contain at least one domain, and enabled metrics must
use a separate password of at least 16 characters.

Provider `postgres://` and `postgresql://` URLs are normalised to SQLAlchemy's
asyncpg scheme at startup.

---

## Development

```bash
# Backend — from backend/
pytest                    # no live database needed; integration tests use in-memory SQLite
ruff check src tests
ruff format --check src tests
mypy src                  # strict

# Frontend — from frontend/
npm run lint              # theme-token rules: raw hex / rgb() / hsl() fail the build
npm run typecheck
npm run build
```

555 tests pass. CI
([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs exactly these on
every push to `main` and every pull request, plus a third job that applies the
whole Alembic chain to an empty PostgreSQL database and asserts `audit_logs`
survives — the check that catches a migration which only works against SQLite.

Backend tests need no external services: the integration suite runs against
in-memory SQLite, an in-memory Qdrant and a deterministic hash embedding
provider. `backend/tests/integration/test_migrations.py` drives the real Alembic
chain over a throwaway database.

### Migrations

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "what changed"
```

The DSN comes from application settings, never from `alembic.ini`, so migrations
need `backend/.env` present. Under Compose:

```bash
docker compose run --rm backend alembic upgrade head
```

The chain is linear with a single head. `f0e1d2c3b4a5` makes its own `downgrade`
raise `NotImplementedError` — the review and notification data it dropped cannot
be reconstructed — so a downgrade past it is not a supported operation.
`b1a4c7e2d903` restores the audit trail that same revision removed.

For multi-replica paid deployments, move migrations into the platform's single
pre-deploy job before scaling out.

---

## Frontend verification

Beyond lint and typecheck, the frontend carries a set of Playwright scripts in
`frontend/scripts/`, run directly with `node scripts/<name>.mjs`. They are not
part of CI.

| Script | What it proves |
| --- | --- |
| `screenshot.mjs <out.png>` | Deterministic capture; warns on horizontal overflow. |
| `compare-screenshots.mjs <a> <b>` | Pixel diff at threshold 0; writes a diff image. |
| `verify-tokens.mjs` | Every `@theme` token resolves to the exact literal it replaced. |
| `check-contrast.mjs` | Every required colour pairing meets WCAG AA. No server needed. |
| `measure-lcp.mjs` | LCP with every candidate in order; `--throttle` for Fast-3G. |
| `smoke-screens.mjs` | Every authenticated screen renders against mocked API fixtures. |
| `conformance-{static,runtime,states}.mjs` | Source structure, rendered-DOM contrast, loading / empty / error states. |
| `e2e-{live,roles,crud}.mjs` | The app and a real backend agree. |
| `test-hero-fallback.mjs` | The landing page survives the hero video failing to load. |
| `verify-deploy.mjs <site> <apiOrigin>` | A deployed build renders, hydrates, guards routes, and dials the configured API origin. |

All except `check-contrast.mjs` need `npm run start` on `:3000`; the `e2e-*`
scripts also need a seeded backend on `:8000`. Playwright browsers are a
prerequisite: `npx playwright install chromium`.

Captures are deterministic because the script freezes CSS and Framer animation
*and* pauses every `<video>` at frame 0 — without the video freeze, two captures
of an unchanged build differ by roughly 6% of pixels.

---

## Deployment

### Local production-shaped deployment

```bash
docker compose up -d --build --wait
curl http://localhost:8080/health
```

The backend container applies `alembic upgrade head` before uvicorn starts and
fails fast if the migration fails. Uploaded documents and both data stores use
named volumes. `docker compose down` without `-v` preserves them.

### No-cost deployment

A split topology has checked-in configuration:

| Piece | Platform | Config |
| --- | --- | --- |
| Frontend | Netlify Free | `netlify.toml` (repo root, base `frontend`, publish `.next`) |
| API | Render Free | `render.yaml` + `backend/Dockerfile` |
| PostgreSQL | Neon Free | — |
| Vector search | Qdrant Cloud Free | — |

`NEXT_PUBLIC_API_BASE_URL` must be the **bare origin** — scheme and host only, no
trailing `/api`. The backend mounts routers under two prefixes (`/tenders/...` and
`api/v1/tenders/...`) and the client appends both verbatim, so only the bare origin
resolves both. The `/api` suffix is a Docker Compose convention that nginx strips.

Render Free sleeps after 15 idle minutes, wakes in about a minute, has an
ephemeral filesystem, and shares 750 instance-hours per month. This is a
demonstration topology, not a production SLA.

**Document durability caveat.** The application stores tender documents on the
API filesystem. On a free Render service those files disappear on restart,
redeploy or spin-down. Rows remain in Neon and vectors in Qdrant, but file
durability needs a paid persistent disk or a future object-storage adapter.

### Rollback

- **Frontend:** in Netlify Deploys, select the previous known-good production
  deploy and publish it.
- **API:** in Render Events, roll back to one of the two retained previous free
  deploys. Verify `/health` before sending users back.
- **Database:** prefer a Neon restore/branch from before the migration. Do not run
  an Alembic downgrade against production until its data-loss behaviour has been
  reviewed and a backup exists — and note that downgrading past `f0e1d2c3b4a5`
  raises by design.
- **After rollback:** recheck CORS, login, one authenticated list route, and a
  tender detail route. If a frontend environment value changed, rebuild rather
  than only republishing an older bundle.

---

## Security

- Email/password credentials use salted PBKDF2 hashes. Google ID tokens are
  checked against the configured client ID as the audience boundary. Publishing
  the Google client ID is safe; it is a public identifier, not a secret.
- The Google client secret is genuinely unused by this flow. Leave it unset.
- Account admission is fail-closed. Deactivation is the offboarding control, and a
  deactivated account is refused even on an allowed domain.
- **Every state change is audit-logged.** `audit_logs` is append-only; the ORM
  registers no update or delete path, and `actor_id` carries no foreign key so
  deleting a user never cascades away the trail of what they did.
- Browser log ingestion accepts anonymous callers by design — sign-in and landing
  errors happen before anyone holds a token — so a per-user, per-address rate
  limit is what keeps it from being an open write sink. Behind the shipped nginx
  every anonymous caller shares the proxy's address and therefore one bucket;
  this is a documented limitation, not a security boundary.
- [.gitignore](.gitignore) covers `.env` files, OAuth client JSON, PEM keys and
  pasted credential notes. Never commit a real `.env`.

---

## Known limitations

Honest list of what is incomplete or surprising.

1. **`ANALYZED` and `REVIEWED` are unreachable.** Both states and every edge
   between them are still defined, and no code path reaches either. They are kept
   so existing rows stay readable and filterable. A future bid-decision feature
   would need to reintroduce the queue that `f0e1d2c3b4a5` removed.
2. **Re-extraction destroys manual corrections.** `ExtractionService.extract`
   builds a fresh `TenderMetadata` and upserts it, overwriting all ten fields.
   Since the correction endpoint was removed there is currently no way to make a
   manual correction, so this is latent rather than active — but it will bite the
   moment one is added.
3. **`COMPANY_NET_WORTH` does not exist.** It was retired (FR-303) along with the
   net-worth qualification rule. `thresholds.py` no longer defines it.
4. **`GEMINI_API_KEY` is inert.** The settings and the LLM port exist, but no
   service constructs an LLM provider and no analyst narrative is generated. The
   `AnalystReport` DTO was removed.
5. **`tender_metadata.fields` holds ten fields in one JSON column.** Manual
   correction of an individual field is not supported at the API level.
6. **`/tenders/{id}/boq/analytics` was removed.** BOQ items are readable; the
   aggregate summary endpoint is not.
7. **`.github/workflows/ci.yml` exists now.** It did not for most of this
   repository's history, which is why a 62-test failure count went unnoticed.
   Playwright verification scripts are still not in CI — they need a browser and
   a running stack.
