# Tender Intelligence Platform

Decision support for **bid / no-bid analysis of construction tenders**, built for
Maheshwari Computer.

The platform ingests a tender, extracts its commercial and eligibility terms,
scores it against the company's capacity and its own past projects, and returns a
**GO / REVIEW / NO_BID** recommendation with the reasoning attached. A manager
signs off. Every state change is written to an audit log.

The scoring is deterministic. The AI analyst explains a decision; it never
changes one.

---

## Contents

- [Quick start](#quick-start)
- [How it works](#how-it-works) — lifecycle, decision engines, review, access control
- [Architecture](#architecture)
- [API](#api)
- [Configuration](#configuration)
- [Development](#development)
- [Frontend verification](#frontend-verification)
- [Deployment](#deployment)
- [Security](#security)
- [Asset licensing](#asset-licensing)

---

## Quick start

One command from a fresh clone. It writes the environment files, collects the
administrator email, optionally configures Google and Gemini, generates service
secrets, builds every service, and starts the stack. Backend startup applies the
migrations, including the first-administrator role assignment.

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
| **Gemini API key** | Optional. Enables generated analyst narratives; deterministic scoring works without it. |

Re-running `setup` is safe: a value you have already set is never overwritten.

**Prerequisites** — Docker Desktop. For native mode, additionally Python 3.12+
and Node 22 (see [.nvmrc](.nvmrc)).

### Native mode (reload on save)

Postgres and Qdrant stay in Docker; the API and the web app run on your host.

```powershell
./scripts/setup.ps1 -Mode native    # once
./scripts/dev.ps1                   # API :8000 + web :3000
```
```bash
./scripts/setup.sh --mode native
./scripts/dev.sh
```

`setup` points `DATABASE_URL` and `QDRANT_URL` at the Compose service names in
docker mode and at `localhost` in native mode, so one `backend/.env` serves both.
Switching modes means re-running `setup` with the other mode.

### Unattended

```bash
TI_ADMIN_EMAIL=ops@example.com \
  ./scripts/setup.sh --non-interactive
```

`--skip-start` (`-SkipStart`) writes the configuration without touching Docker.

---

## How it works

### Tender lifecycle

Nothing is analysed before it is parsed, and no recommendation exists before the
engines have run. The lifecycle enforces that ordering.

```
REGISTERED → DOWNLOADED → PARSED → ANALYZED → REVIEWED
```

| State | Meaning |
| --- | --- |
| `REGISTERED` | Tender recorded; source documents not yet fetched. |
| `DOWNLOADED` | Documents retrieved and stored. |
| `PARSED` | Text and fields extracted from those documents. |
| `ANALYZED` | Risk, qualification and recommendation engines have run. |
| `REVIEWED` | A manager has recorded a verdict. |
| `ARCHIVED` | Closed. Terminal — nothing transitions out of it. |

Any state may move to `ARCHIVED`. A `REVIEWED` tender may return to `ANALYZED`,
which is what makes re-analysis after a correction possible.

Documents carry their own status, independent of the tender:
`PENDING` → `DOWNLOADING` → `DOWNLOADED`, or `FAILED`.

### The decision engines

Three deterministic engines, all in `backend/src/tender_intel/domain/decision/`.
They read every constant from `thresholds.py` and never inline a numeric literal,
so the thresholds can later become administrator-managed configuration without
hunting values through the code. All arithmetic is exact `Decimal`.

**Risk** — six categories, each scored `NONE` / `LOW` / `MEDIUM` / `HIGH` and
mapped onto a 0–10 scale:

| Category | What it flags |
| --- | --- |
| `PERFORMANCE_GUARANTEE` | Guarantee demanded as a percentage of tender value. |
| `LIQUIDATED_DAMAGES` | Penalty exposure for delay. |
| `OEM_DEPENDENCY` | Reliance on a single original manufacturer. |
| `SHORT_COMPLETION_TIME` | Delivery window too tight for the value. |
| `HIGH_EMD` | Earnest money deposit disproportionate to tender value. |
| `SPECIAL_CLAUSES` | Non-standard terms needing a human read. |

A keyword detected but with an unparseable magnitude falls back to `MEDIUM` —
fail toward caution, not toward dismissal. High EMD is the single documented
exception, where an unparseable clause is `LOW`.

**Qualification** — three eligibility rules checked against the company's declared
capacity: past work value, average annual turnover (against a required percentage
of tender value), and net worth. A figure the company has not declared fails the
rule rather than passing it silently.

**Recommendation** — ordered rules, first match wins:

| Rule | Outcome |
| --- | --- |
| Qualification failed | `NO_BID` |
| Overall risk score > 8.0 | `REVIEW` |
| Strong past-project match | `GO` |
| Mid match | `REVIEW` |
| Weak match | `NO_BID` |
| Qualified, risk acceptable, no eligibility rules | `GO` |

Alongside the verdict the engine returns a **win probability** (clamped 10–95, or
0 for `NO_BID`), a **confidence** score that decays with every missing extracted
field, and explicit pros, cons and a checklist.

### Human review

A review record is explicitly one of two kinds, never inferred:

- **`CORRECTION`** — someone fixed an extracted field. No decision was made and
  the tender does not move.
- **`VERDICT`** — a manager decided (`APPROVED` / `REJECTED`). This is the bid
  decision.

Keeping the distinction explicit means review history and audit diffs never have
to guess what a row meant, and a correction can never be misread as a decision.
A verdict recorded before a later correction is marked stale rather than silently
trusted.

### Access control

Four roles, hierarchical and inclusive — an endpoint requiring level *N* admits
every role at or above it.

| Role | Level | Scope |
| --- | --- | --- |
| `EMPLOYEE` | 20 | The floor every account is born with. Read tenders, run analysis, record corrections. |
| `MANAGER` | 30 | Everything above, plus recording bid verdicts. |
| `ADMIN` | 40 | Everything above, plus user management and audit logs. |
| `SUPER_ADMIN` | 50 | Full control, including role assignment. |

`EMPLOYEE` is the floor, not a rejection. The gaps between levels are deliberate —
do not renumber them.

**Sign-in supports email/password and optional Google Identity Services.** There
is no password-reset flow. Passwords are PBKDF2-hashed and never stored in plain
text. Admission is fail-closed: the address must sit on a domain in
`ALLOWED_EMAIL_DOMAINS`, or be named individually in `ALLOWED_EMAIL_EXCEPTIONS`.
An empty domain list rejects everyone. New accounts land at `EMPLOYEE` unless an
administrator pre-provisioned a higher role for that address first.

---

## Architecture

Clean Architecture. Dependencies point inward; the domain depends on nothing.

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

**Guiding principles** — domain-first; a deterministic core with constrained AI;
and *fail toward caution*: `UNKNOWN` over a guess, `MEDIUM` over dismissal,
offline fallback over failure, an audit entry on every state change.

### Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Web | Node 22 · Next.js 16 (App Router) · React 19 · Tailwind CSS 4 |
| Data | PostgreSQL 16 · Qdrant (vector search) |
| Embeddings | fastembed · `BAAI/bge-small-en-v1.5` (384-d), with a deterministic offline backend |
| Extraction | pdfplumber / PyMuPDF · openpyxl for spreadsheet import |
| AI analyst | Google Gemini — optional, degrades gracefully when absent |
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
| `/dashboard` | Portfolio overview and pending work. |
| `/tenders`, `/tenders/[id]`, `/tenders/upload` | List, full analysis detail, and ingestion. |
| `/projects` | Past-project corpus that similarity matching scores against. |
| `/reviews` | Pending verdicts queue. |
| `/admin`, `/admin/audit-logs`, `/admin/role-assignments` | Administration. |
| `/profile` | The signed-in user's account. |
| `/design/tokens`, `/design/primitives` | Live theme and component reference. `noindex`, but publicly served. |

---

## API

OpenAPI lives at `http://localhost:8000/docs`. A full endpoint-to-screen map is in
[frontend/docs/api-map.md](frontend/docs/api-map.md).

| Group | Endpoints |
| --- | --- |
| Auth | `POST /auth/google` · `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` |
| Tenders | `GET\|POST /tenders` · `GET\|PATCH\|DELETE /tenders/{id}` · `POST /tenders/import` |
| Pipeline | `POST /tenders/{id}/extract` · `POST /tenders/{id}/analyze` · document download and retrigger |
| Decisions | `GET /tenders/{id}/recommendation` · `/metadata` · `/boq` · `/matches` · `/report` |
| Reviews | `GET /tenders/{id}/reviews` · `GET /reviews/pending` |
| Projects | Past-project CRUD |
| Admin | Users, roles, role assignments, audit logs, API usage, system health |
| Platform | `GET /stats` (any signed-in user) · `GET /health` · `GET /metrics` |

`GET /stats` returns tender totals by lifecycle state, past-project count and
pending reviews to any authenticated user. `GET /admin/stats` is separate and
`ADMIN`-only — it carries user and account figures that `/stats` deliberately
omits.

---

## Configuration

All configuration comes from the environment. Three templates:

| Template | Copy to | Read by |
| --- | --- | --- |
| [.env.backend.example](.env.backend.example) | `backend/.env` | the API and Alembic |
| [.env.frontend.example](.env.frontend.example) | `frontend/.env.local` | `next dev` / `next build` on the host |
| [.env.example](.env.example) | `.env` | Docker Compose only, for its `${...}` substitutions |

`setup` creates all three. Every backend setting has a default, so nothing crashes
on a missing variable in local mode — but several matter in practice:

| Variable | Why it matters |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Optional Google sign-in. When set, it must match `NEXT_PUBLIC_GOOGLE_CLIENT_ID` because the backend verifies the token audience. |
| `ALLOWED_EMAIL_DOMAINS` | Empty rejects every sign-in. |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | Read by migration `d4a1e9c5b872` to seed the first administrator. Set it *before* migrating. |
| `JWT_SECRET` | Generated by `setup`. Must be ≥32 characters and not the template default. |
| `DATABASE_URL` | Host is `postgres` under Compose, `localhost` natively. `setup` handles this. |
| `GEMINI_API_KEY` | Optional. Without it the AI analyst degrades rather than failing. |
| `EMBEDDING_BACKEND` | `fastembed` downloads a model on first boot; `hash` is deterministic and fully offline. |
| `QDRANT_API_KEY` | Required with Qdrant Cloud; leave blank for local Qdrant. |
| `METRICS_PASSWORD` | Separate Basic Auth secret for `/metrics`; production rejects the template value when metrics are enabled. |

`NEXT_PUBLIC_*` is inlined by `next build`, so under Compose it arrives as a
**build arg** from the root `.env` — changing one needs
`docker compose up -d --build frontend`, not a restart.

Production release gates are enforced at startup when `ENVIRONMENT=production`:
`JWT_SECRET` must be strong, `DATABASE_URL` and `CORS_ALLOW_ORIGINS` must be
explicitly supplied, the database must be PostgreSQL, CORS cannot contain `*`,
`ALLOWED_EMAIL_DOMAINS` must contain at least one domain, and enabled metrics
must use a separate password of at least 16 characters.

Required production values are:

| Service | Required | Conditional or optional |
| --- | --- | --- |
| Backend | `ENVIRONMENT=production`, `DATABASE_URL`, `CORS_ALLOW_ORIGINS`, `JWT_SECRET`, `ALLOWED_EMAIL_DOMAINS` | `QDRANT_URL` and `QDRANT_API_KEY` for Qdrant Cloud; `METRICS_PASSWORD` when metrics are enabled; `BOOTSTRAP_SUPER_ADMIN_EMAIL` for first-admin provisioning; Google, Gemini, Sentry, and OTLP settings are optional. |
| Frontend build | `NEXT_PUBLIC_API_BASE_URL` | `NEXT_PUBLIC_GOOGLE_CLIENT_ID` and `NEXT_PUBLIC_HERO_VIDEO` are optional. |
| Docker Compose | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `NEXT_PUBLIC_API_BASE_URL` | Public Google and hero-video build values are optional. |

All supported settings, defaults, and safe placeholders are listed in the three
environment templates. Provider `postgres://` and `postgresql://` URLs are
normalized to SQLAlchemy's asyncpg scheme at startup.

### Pre-provisioning roles

To give someone a role above `EMPLOYEE` before their first sign-in, copy
[scripts/seed_role_assignments.example.sql](scripts/seed_role_assignments.example.sql),
put your addresses in it, and run it once after migrating:

```bash
docker compose exec -T postgres psql -U tender -d tender_intel < scripts/seed_role_assignments.sql
```

The list is consulted once, at account creation, and never again. Live users are
changed with `PATCH /admin/users/{id}/role` instead.

---

## Development

```bash
# Backend — from backend/
pytest                    # no live database needed; integration tests use in-memory SQLite
ruff check .
ruff format --check .
mypy src                  # strict

# Frontend — from frontend/
npm run lint              # theme-token rules: raw hex / rgb() / hsl() fail the build
npm run typecheck
npm run build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs exactly these on
every push to `main` and every pull request.

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

The backend container runs `alembic upgrade head` before uvicorn. Native startup
must run the Alembic command explicitly. For multi-replica paid deployments,
move migrations into the platform's single pre-deploy job before scaling out.

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
| `conformance-{static,runtime,states}.mjs` | Source structure, rendered-DOM contrast, and loading / empty / error states. |
| `e2e-{live,roles,crud,lifecycle}.mjs` | The app and a real backend agree. |
| `test-hero-fallback.mjs` | The landing page survives the hero video failing to load. |

All except `check-contrast.mjs` need `npm run start` on `:3000`; the `e2e-*`
scripts also need a seeded backend on `:8000`. Playwright browsers are a
prerequisite: `npx playwright install chromium`.

Captures are deterministic because the script freezes CSS and Framer animation
*and* pauses every `<video>` at frame 0 — without the video freeze, two captures
of an unchanged build differ by roughly 6% of pixels, enough noise to hide a real
regression.

The landing hero video is the only asset on that page fetched over the network,
so it is the only thing that can fail. When it does, `HeroVisual.tsx` swaps in a
self-hosted DOM panel. `onError` alone is insufficient — the `<video>` is
server-rendered, so a failure fires before hydration and media errors do not
bubble; the component checks `el.error` and `networkState` on mount as well.

---

## Deployment

### Local production-shaped deployment

Copy the three environment templates, replace all production placeholders, then:

```bash
docker compose up -d --build --wait
curl http://localhost:8080/health
```

The backend container applies `alembic upgrade head` before uvicorn starts. The
nginx entry point is `http://localhost:8080`; uploaded documents and both data
stores use named volumes. Review logs with `docker compose logs -f` and stop the
stack with `docker compose down` (do not add `-v` unless deleting all local data
is intentional).

### No-cost deployment recommendation

For a public demo or low-traffic MVP, use a split deployment:

- **Frontend:** Netlify Free, using the checked-in `netlify.toml`.
- **API:** Render Free, using the checked-in `render.yaml` and backend Dockerfile.
- **PostgreSQL:** Neon Free.
- **Vector search:** Qdrant Cloud Free.

This is the best verified no-cost fit for the current stack, but it is not a
production SLA. Render explicitly positions free web services as preview/hobby
compute: they sleep after 15 idle minutes, can take about a minute to wake, have
an ephemeral filesystem, and share 750 instance-hours per month. The Hobby
workspace includes 5 GB outbound bandwidth and 500 build-pipeline minutes.
[Render free limits](https://render.com/docs/free) ·
[Render bandwidth](https://render.com/docs/outbound-bandwidth) ·
[Render build limits](https://render.com/docs/build-pipeline)

The application currently stores tender documents on the API filesystem. On a
free Render service those files disappear on a restart, redeploy, or spin-down.
PostgreSQL rows remain in Neon and vectors remain in Qdrant, but document-file
durability requires a paid persistent disk or a future object-storage adapter.
Do not treat the no-cost topology as production for irreplaceable tenders.

### Free-tier comparison verified 8 September 2026

| Platform | Relevant free limits | Sleep or cold start | Bandwidth and builds | Database and files | Custom domain | Card | Fit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Netlify Free** | 300 credits/month; a production deploy costs 15 credits | Static assets stay edge-served; dynamic Next compute consumes credits | 20 credits/GB bandwidth and 2 credits/10k requests; the account pauses at the limit | Basic Netlify Database exists, but this project already uses external PostgreSQL and Qdrant | Included with SSL | Not required for Free | Best frontend option; commercial projects are allowed and `netlify.toml` is ready. [Pricing](https://www.netlify.com/pricing/) |
| **Render Free** | 512 MB per free web instance; 750 shared instance-hours/month | Sleeps after 15 minutes; wake-up is about one minute | Hobby includes 5 GB bandwidth and 500 pipeline minutes | Filesystem is ephemeral; free Render Postgres expires after 30 days, so use Neon | Two Hobby domains; TLS included | Not required; services suspend instead of charging without one | Best API demo option because it runs the existing Dockerfile and supports health checks. [Free services](https://render.com/docs/free) |
| **Koyeb Free** | One 512 MB, 0.1 vCPU web service with 2 GB ephemeral SSD | Scales to zero after one idle hour | Outbound transfer is metered; free compute cannot use volumes or worker services | Free PostgreSQL is limited to 5 active hours/month and 1 GB | Supported | Required, including a temporary authorization hold | Technically compatible but weaker than Render for this app and inconvenient without a card. [Instances](https://www.koyeb.com/docs/reference/instances) · [Pricing FAQ](https://www.koyeb.com/docs/faqs/pricing) |
| **Vercel Hobby** | 4 active CPU-hours, 360 GB-hours memory and up to 60-second functions | Serverless functions may cold start | Typical guideline: 100 GB fast transfer and 100 build hours | External PostgreSQL/Qdrant required; local files are not durable | Supported | Not required until upgrading | Excellent Next.js hosting, but Hobby is restricted to personal non-commercial use, so it is not valid for this company app. [Hobby plan](https://vercel.com/docs/plans/hobby) · [Fair use](https://vercel.com/docs/limits/fair-use-guidelines) |
| **Railway Free** | $5 trial credit for 30 days, then $1/month | No enduring zero-cost promise | 10-minute builds after trial on Free | 0.5 GB volume after trial | No custom domain after trial | Not required for the trial | Existing deployment notes targeted Railway, but it is no longer genuinely free. [Pricing](https://railway.com/pricing) |

Neon Free currently provides 100 CU-hours and 0.5 GB storage per project,
with no time limit or card requirement. Qdrant Cloud Free provides one node with
0.5 vCPU, 1 GB RAM, and 4 GB disk without a card; an unused cluster is suspended
after one week and deleted after four weeks unless reactivated.
[Neon pricing](https://neon.com/pricing) ·
[Qdrant free cluster](https://qdrant.tech/documentation/cloud/create-cluster/)

### Exact no-cost deployment steps

1. **Create PostgreSQL.** Create a Neon Free project in a region near the API.
   Copy its pooled connection string. The backend accepts provider URLs beginning
   with `postgres://` or `postgresql://` and selects the asyncpg driver itself.
2. **Create vector storage.** Create a Qdrant Cloud Free cluster, then copy its
   HTTPS cluster URL and API key. Keep the cluster active or reactivate it before
   the four-week inactivity deletion point.
3. **Deploy the API.** In Render choose **New > Blueprint**, connect this repository,
   and select `render.yaml`. Supply the prompted values:

   ```dotenv
   DATABASE_URL=<Neon pooled connection string>
   CORS_ALLOW_ORIGINS=https://temporary.invalid
   ALLOWED_EMAIL_DOMAINS=example.com
   BOOTSTRAP_SUPER_ADMIN_EMAIL=admin@example.com
   QDRANT_URL=https://your-cluster.cloud.qdrant.io
   QDRANT_API_KEY=<Qdrant API key>
   ```

   Render generates `JWT_SECRET`; the Blueprint disables public metrics on the
   constrained free service, uses hash embeddings to stay inside 512 MB, runs
   migrations during container startup, and checks `/health`. Record the final
   `https://...onrender.com` API URL.
4. **Deploy the frontend.** In Netlify import the same repository. The root
   `netlify.toml` sets base directory `frontend`, build command `npm run build`,
   and publish directory `.next`. Add these build environment variables before
   the first production deploy:

   ```dotenv
   NEXT_PUBLIC_API_BASE_URL=https://your-api.onrender.com
   NEXT_PUBLIC_GOOGLE_CLIENT_ID=
   NEXT_PUBLIC_HERO_VIDEO=/video/hero.mp4
   ```

   Record the final `https://...netlify.app` URL. `NEXT_PUBLIC_*` values are
   compiled into the browser bundle, so every change requires a new frontend build.
5. **Lock down CORS.** Replace Render's temporary `CORS_ALLOW_ORIGINS` value with
   the exact Netlify origin (scheme and hostname only, no trailing slash), then
   redeploy the API. Add a custom frontend origin to the comma-separated list if used.
6. **Optional Google sign-in.** Set the same client ID as `GOOGLE_CLIENT_ID` on
   Render and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` on Netlify. Add the Netlify and custom
   frontend origins to the OAuth Web Client's Authorized JavaScript origins, then
   rebuild the frontend. Email/password works without Google.
7. **Post-deployment verification.** Confirm the API `/health` returns HTTP 200;
   confirm an `OPTIONS /auth/login` request from the frontend receives the exact
   `Access-Control-Allow-Origin`; register the bootstrap address; create a tender;
   and verify dashboard, audit, and role-protected screens. Expect the first API
   request after idle time to wait for Render's cold start.

### Production secrets

Set secrets in Render's environment settings, never in `render.yaml`, Netlify,
or source control. `DATABASE_URL`, `JWT_SECRET`, `QDRANT_API_KEY`, optional
`GEMINI_API_KEY`, optional `GOOGLE_CLIENT_ID`, `BOOTSTRAP_SUPER_ADMIN_EMAIL`, and
any observability DSNs belong on the API. Only `NEXT_PUBLIC_*` values belong on
Netlify; they are public by design. If enabling `/metrics`, also set a unique
`METRICS_PASSWORD` of at least 16 characters.

### Rollback

- **Frontend:** In Netlify Deploys, select the previous known-good production
  deploy and publish it.
- **API:** In Render Events, roll back to one of the two retained previous free
  deploys. Verify `/health` before sending users back.
- **Database:** Prefer a Neon restore/branch from before the migration. Do not run
  an Alembic downgrade against production until its data-loss behavior has been
  reviewed and a backup exists. Keep application and schema changes backward
  compatible for at least one release so an application-only rollback remains safe.
- **After rollback:** Recheck CORS, login, one authenticated list route, and a
  tender detail route. If a frontend environment value changed, rebuild rather
  than only republishing an older bundle.

## Security

- Email/password credentials use salted PBKDF2 hashes. Google ID tokens are
  checked against the configured client ID as the audience boundary. Publishing
  the Google client ID is safe; it is a public identifier, not a secret.
- The Google client secret is genuinely unused by this flow. Leave it unset.
- Account admission is fail-closed. Deactivation is the offboarding control, and
  a deactivated account is refused even on an allowed domain.
- Every state change is audit-logged.
- Browser log ingestion accepts anonymous callers by design — sign-in and landing
  errors happen before anyone holds a token — so a per-user, per-address rate
  limit is what keeps it from being an open write sink.
- [.gitignore](.gitignore) covers `.env` files, OAuth client JSON, PEM keys and
  pasted credential notes. Never commit a real `.env`.

## Asset licensing

| Asset | Status |
| --- | --- |
| Outfit, Fustat, Inter | Google Fonts (SIL OFL), self-hosted at build by `next/font`. |
| `public/video/hero.mp4` | **Licence cleared by the project owner, 2026-08-18.** Self-hosted since; override with `NEXT_PUBLIC_HERO_VIDEO`. |
| `public/fonts/*.woff2` (Supreme, Bespoke Stencil) | Fontshare / Indian Type Foundry; self-hosting cleared by the owner. Superseded and no longer referenced. |
| `public/spline/scene.splinecode` | **Licensing unconfirmed.** Currently unused, so the question is moot unless it is reintroduced. |

The hero video is 960×960 but renders at 600px, so it carries roughly 2.5× the
pixels needed. Re-encoding to 600×600 (and/or a WebM/AV1 alternate source) is the
remaining lever on landing-page LCP; it has not been done, because re-encoding the
owner's asset is their call.
