# Backend API surface map

**Generated from the running application's OpenAPI schema, not hand-maintained.**
Regenerate after any router or schema change; a stale copy of this file is worse
than none, because a frontend developer will code against it.

This describes the **eligibility screening** API. It is not the bid
recommendation API described in earlier revisions of this file: migration
`f0e1d2c3b4a5` removed `/tenders/{id}/analyze`, `/recommendation`, `/report`,
`/matches`, `/corrections`, `/verdict` and `/reviews/pending` along with the risk
and recommendation engines. Those endpoints do not exist. If you need them, the
engines are recoverable from git but the decision they fed is a product question,
not an API question.

## Auth model

- Bearer access token via `Authorization: Bearer <token>` (`HTTPBearer`,
  `auto_error=False`).
- Role hierarchy is **numeric and ascending**, enforced by `require_role(min)` as
  `user.level >= min.level`:

  | Role | Level |
  |---|---|
  | `EMPLOYEE` | 20 |
  | `MANAGER` | 30 |
  | `ADMIN` | 40 |
  | `SUPER_ADMIN` | 50 |

  `ANALYST` and `VIEWER` are gone — collapsed into `EMPLOYEE`. Level 10 and the
  inter-tier gaps are reserved; do not renumber. Source:
  `domain/enums/roles.py`.

- **"Auth"** in the tables below means any authenticated active user
  (`get_current_user`, i.e. EMPLOYEE+). A named role means `require_role(THAT_ROLE)`
  — that role *or higher*.
- **Every gate is inclusive.** There is no `require_exact_roles` any more; it
  existed only for the bid verdict and was removed with it.
- **Sign-in supports email/password and optional Google Identity Services**, both
  restricted to `ALLOWED_EMAIL_DOMAINS` or exact `ALLOWED_EMAIL_EXCEPTIONS`.
  Password reset is not implemented.
- Deactivated accounts get **403**, not 401. A refused email domain is also 403.

## Error envelope

Every handled error returns `{"detail": "<message>"}`. Mapping from `api/errors.py`:

| Domain error | HTTP | Default message |
|---|---|---|
| `EntityNotFoundError` | **404** | Resource not found. |
| `DuplicateEntityError` | **409** | Resource already exists. |
| `LiveUserExistsError` | **409** | Names `PATCH /admin/users/{user_id}/role` as the remedy. |
| `AssignmentConsumedError` | **409** | A consumed assignment cannot be revoked. |
| `InvalidStatusTransitionError` | **409** | Invalid state transition. |
| `AuthenticationError` | **401** | Invalid credentials. (`WWW-Authenticate: Bearer`) |
| `InvalidTokenError` | **401** | Invalid or expired token. |
| `InactiveUserError` | **403** | Account is deactivated. |
| `ForbiddenDomainError` | **403** | Email domain not permitted. |
| `PermissionDeniedError` | **403** | Insufficient permissions. |
| `DomainValidationError` | **422** | Invalid request. |
| unhandled `DomainError` | **500** | generic |

⚠️ **422 is overloaded.** It is both FastAPI's request-validation status *and* the
mapping for `DomainValidationError`. Screening a `REGISTERED` tender returns
**422**, not 409 — verified live:

| Call on a `REGISTERED` tender | Status |
|---|---|
| `POST /api/v1/tenders/{id}/eligibility` | **422** |
| `POST /tenders/{id}/extract` | **422** (no downloaded document) |
| `GET /tenders/{id}/metadata` | **404** |
| `GET /tenders/{id}/boq` | **200** `[]` |

So a stage-gated action fails with 422, while a missing sub-resource may be 404,
422 or an empty 200. Do not assume one shape. `lib/api.ts` documents this and
accepts per-call overrides via `describeError`.

⚠️ **There is no 400 in the map.**

## Lifecycle

`domain/enums/tender_status.py` — `TenderStatus`:

```
REGISTERED → DOWNLOADED → PARSED
```

Any state → `ARCHIVED` (terminal), reachable only through
`POST /api/v1/tenders/retirement`.

⚠️ `ANALYZED` and `REVIEWED` are **still defined in the enum** and still appear in
`GET /tenders?status=…`, but **no code path enters either state**. They are
retained so historical rows stay readable and so a future bid-decision feature has
somewhere to attach. Do not build UI that waits for them.

⚠️ Plan §8's `DOWNLOADING` / `FAILED` states are `DocumentStatus` values on the
**document**, a separate enum: `PENDING`, `DOWNLOADING`, `DOWNLOADED`, `FAILED`.

## Pagination

Every endpoint marked *paged* returns:

```ts
{ items: T[], total: number, limit: number, offset: number, has_more: boolean }
```

Query params: `limit` (default 50, 1..200), `offset` (default 0).

---

## Endpoints

47 paths.

### Health — `health.py`

| Method | Path | Role | Response |
|---|---|---|---|
| GET | `/health` | **none** | `HealthResponse` |

```ts
type HealthResponse = { status: string; version: string }
```

### Operational statistics — `stats.py`

| Method | Path | Role | Response |
|---|---|---|---|
| GET | `/stats` | Auth | `OperationalStatsResponse` |

```ts
type OperationalStatsResponse = {
  tenders_total: number
  tenders_by_status: Record<string, number>
  eligibility_by_status: Record<string, number>   // ELIGIBLE | NOT_ELIGIBLE | INDETERMINATE
  past_projects_total: number
  screening_pending: number   // recorded but never screened
}
```

`screening_pending` **replaced** `reviews_pending`, which was hard-coded to `0` and
described a queue that no longer exists. It is derived as
`tenders_total − count(tender_eligibility)`, so it cannot drift. Stale-but-recorded
results still count as screened; `GET /eligibility` reports that case per tender
via `is_stale`.

### Auth — `auth.py`, prefix `/auth`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/auth/register` | none | `RegisterRequest` | **201** `TokenResponse` |
| POST | `/auth/login` | none | `LoginRequest` | `TokenResponse` |
| POST | `/auth/google` | none | `GoogleLoginRequest` | `TokenResponse` |
| POST | `/auth/refresh` | none | `RefreshRequest` | `TokenResponse` |
| POST | `/auth/logout` | none | `LogoutRequest` | **204** no body |
| GET | `/auth/me` | Auth | — | `UserResponse` |

⚠️ An earlier version of this file stated that `/auth/register` and `/auth/login`
were removed and that Google was the only way to create an account. **That is
wrong.** Both endpoints exist, both are wired to the login and register screens,
and 29 integration tests cover them. They were removed by migration
`b7f39d5a2e60` and restored, nullable, by `7690fc277a01`.

`POST /auth/register` refuses a duplicate email with **409** rather than attaching
a password to an existing Google-only account. `POST /auth/login` returns one
generic 401 for "no such user", "wrong password" and "this account is Google-only"
alike, so an attacker cannot enumerate addresses or discover which method an
account uses.

```ts
type RegisterRequest  = { email: string; full_name: string; password: string }
type LoginRequest     = { email: string; password: string }
type GoogleLoginRequest = { id_token: string }
type TokenResponse    = {
  access_token: string; refresh_token: string; token_type?: string; expires_in: number
}
type UserResponse     = {
  id: string; email: string; full_name: string; role: Role
  is_active: boolean; created_at: string; last_login_at: string | null
}
```

There is **no** `PATCH /auth/me` and no password-reset endpoint. Profile is
read-only plus logout; do not stub one.

### Tenders — `tenders.py`, prefix `/tenders`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders` | EMPLOYEE | `TenderCreateRequest` | **201** `TenderResponse` |
| GET | `/tenders` | Auth | `limit`, `offset`, `status`, `eligibility`, `search` | *paged* `TenderResponse` |
| GET | `/tenders/{tender_id}` | Auth | — | `TenderResponse` |
| PATCH | `/tenders/{tender_id}` | EMPLOYEE | `TenderPatchRequest` | `TenderResponse` |
| DELETE | `/tenders/{tender_id}` | EMPLOYEE | — | **204** no body |
| DELETE | `/tenders` | **MANAGER** | — | `{ deleted: number }` |
| POST | `/tenders/import` | EMPLOYEE | multipart `file` — **.xlsx** | `BulkImportResponse` |

The list filter params are `status` and `eligibility` (the latter aliased from
`eligibility_status`), both enum-valued.

```ts
type TenderResponse = {
  id: string; tender_number: string; title: string; status: TenderStatus
  description: string | null; estimated_value: string | null   // Decimal → string
  closing_date: string | null; source_url: string | null; department: string | null
  created_at: string; updated_at: string
}
type TenderCreateRequest = {
  tender_number: string; title: string          // required
  description?: string | null; estimated_value?: string | null
  closing_date?: string | null; source_url?: string | null; department?: string | null
}
type TenderPatchRequest = {                       // all optional, no tender_number
  title?: string | null; description?: string | null; estimated_value?: string | null
  closing_date?: string | null; source_url?: string | null; department?: string | null
}
type BulkImportResponse = {
  created: number; skipped: number; errors: number; queued_documents: number
  results: { row: number; tender_number: string | null; outcome: string; message: string | null }[]
}
```

Duplicate `tender_number` → **409**.

⚠️ `/tenders/import` takes an **Excel workbook, not CSV** — `openpyxl.load_workbook`.
Row 1 is the header; `tender_number` and `title` are required. Duplicates come back
as skipped rows, not as a failed request.

⚠️ `TenderPatchRequest` has **no `status` field**. A caller cannot set a status
directly; `ARCHIVED` is reachable only through retirement.

### Documents — `documents.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders/{tender_id}/documents` | EMPLOYEE | `{ source_url }` | **201** `DocumentResponse` |
| POST | `/tenders/{tender_id}/documents/upload` | EMPLOYEE | multipart file | **201** `DocumentResponse` |
| GET | `/tenders/{tender_id}/documents` | Auth | — | `DocumentResponse[]` (**not paged**) |
| GET | `/documents/{document_id}` | Auth | — | `DocumentResponse` |
| POST | `/documents/{document_id}/retrigger` | EMPLOYEE | — | `DocumentResponse` |

```ts
type DocumentResponse = {
  id: string; tender_id: string; source_url: string | null
  file_name: string | null; file_path: string | null; file_size: number | null
  mime_type: string | null; sha256: string | null
  status: "PENDING" | "DOWNLOADING" | "DOWNLOADED" | "FAILED"
  attempt_count: number; last_error: string | null
  downloaded_at: string | null; created_at: string
}
```

`retrigger` is the retry path for a `FAILED` **document**.

### Extraction — `extraction.py`, prefix `/tenders/{tender_id}`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/extract` | EMPLOYEE | optional `?document_id=` | `ExtractionResponse` |
| GET | `/metadata` | Auth | — | `MetadataResponse` |
| GET | `/boq` | Auth | — | `BOQItemResponse[]` (**not paged**) |

⚠️ `GET /boq/analytics` **no longer exists.** The `BOQAnalytics` DTO and the
`summarise` service were deleted along with the recommendation surface; nothing
called them. `BOQItemResponse` is unchanged, so items are still readable, they are
just not pre-aggregated. Recompute totals client-side or restore the endpoint
deliberately.

```ts
type MetadataFieldResponse = {
  value: string | null      // serialised; null when UNKNOWN
  confidence: number        // 0.0..1.0 — render wherever a value is shown
  source: string | null
  is_known: boolean         // false ⇒ render the UNKNOWN treatment, not an empty cell
}
type MetadataResponse = {
  tender_id: string
  fields: Record<string, MetadataFieldResponse>   // keys = METADATA_FIELDS (10)
  known_field_count: number
}
type BOQItemResponse = {
  id: string; item_number: string | null; description: string
  unit: string | null; quantity: string | null; unit_rate: string | null
  amount: string | null; category: string | null; confidence: number
}
type ExtractionResponse = {
  tender_id: string; status: string; metadata: MetadataResponse; boq_item_count: number
}
```

`is_known: false` is the **UNKNOWN** signal the plan §7 primitive must key off.

The ten field keys are `work_name`, `estimated_value`, `emd_amount`, `tender_fee`,
`closing_date`, `completion_period`, `location`, `department`,
`eligibility_criteria`, `scope_of_work`.

⚠️ `POST /extract` **replaces** the stored metadata row wholesale and deletes the
BOQ first. Any manual correction is lost — see Known limitations.

### Eligibility screening — `eligibility.py`, prefix `/api/v1/tenders/{tender_id}`

| Method | Path | Role | Response |
|---|---|---|---|
| POST | `/eligibility` | EMPLOYEE | `EligibilityResponse` |
| GET | `/eligibility` | Auth | `EligibilityResponse` |

This is the analysis endpoint. `POST` recomputes and replaces the stored result;
`GET` reads it and reports whether its inputs have moved.

⚠️ The `/api/v1` prefix is unique to this router and to the newer admin surfaces.
It is **not** a versioning scheme applied repo-wide — `/tenders` and `/projects`
carry no prefix. `lib/api.ts` resolves this correctly because `API_BASE` is the
bare origin and it appends both families verbatim.

```ts
type EligibilityResponse = {
  tender_id: string
  status: "ELIGIBLE" | "NOT_ELIGIBLE" | "INDETERMINATE"
  is_stale: boolean
  financial_pass: boolean | null
  financial_required: string | null      // Decimal → string
  financial_actual: string | null
  technical_pass: boolean | null
  rule_satisfied: "1x60" | "2x40" | "3x30" | null
  reasons: string[]                      // every rule that did not pass, in the engine's words
  matched_work_types: {
    work_type_id: string; code: string
    method: "EXACT" | "LEXICAL" | "SEMANTIC"
    score: string; grade: "MATCHED" | "REVIEW" | "NO_MATCH"
  }[]
  qualifying_projects: { project_id: string; name: string; rank: number; work_value: string }[]
  evaluated_at: string
}
```

Rendering notes:

- **`status` is three-valued and `INDETERMINATE` is the one that matters.** A
  missing input resolves to neither pass nor failure. Do not collapse it into
  "not eligible" — that would refuse the entire portfolio until an administrator
  has entered three completed years of turnover.
- `financial_pass: null` means *undecided*, distinct from `false`.
- `rule_satisfied` names which of the three nested similar-work rules was met.
  They are nested — a project clearing 60% also clears 40% — so the first
  satisfied rule is recorded.
- `is_stale` means the recorded result no longer describes its inputs. It is a
  **warning only**: nothing is recomputed, invalidated or hidden.

### Past projects — `projects.py`, prefix `/projects`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/projects` | EMPLOYEE | `PastProjectCreateRequest` | **201** `PastProjectResponse` |
| GET | `/projects` | Auth | `limit`, `offset` | *paged* `PastProjectResponse` |
| GET | `/projects/{project_id}` | Auth | — | `PastProjectResponse` |
| PATCH | `/projects/{project_id}` | EMPLOYEE | `PastProjectPatchRequest` | `PastProjectResponse` |
| DELETE | `/projects/{project_id}` | EMPLOYEE | — | **204** no body |
| DELETE | `/projects` | **MANAGER** | — | `{ deleted: number }` |
| POST | `/projects/backfill` | **ADMIN** | — | `{ indexed: number }` |

⚠️ `POST /projects/from-document` **does not exist.** Because
`/projects/{project_id}` still owns the path shape for reads and updates, a POST
to it returns **405**, not 404.

```ts
type PastProjectResponse = {
  id: string; name: string; client: string | null; work_value: string | null
  category: string | null; location: string | null; description: string | null
  completion_date: string | null
  loa_reference: string | null
  completion_certificate_date: string | null   // ← stage B requires this
  completion_certificate_note: string | null
  embedding_indexed: boolean; created_at: string
}
type PastProjectCreateRequest = {
  name: string                                       // required
  client?: string | null; work_value?: string | null; category?: string | null
  location?: string | null; description?: string | null; completion_date?: string | null
  loa_reference?: string | null
  completion_certificate_date?: string | null
  completion_certificate_note?: string | null
}
```

`completion_certificate_date` is what stage B filters on, not
`completion_date`. A project without one never enters the qualifying pool.

### Project import — `project_import.py`, prefix `/api/v1/projects`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/import` | EMPLOYEE | multipart `files` + `auto_tag` | `ProjectImportResponse` |

Multi-workbook import with per-file and per-row outcomes. `auto_tag` runs the
stage-A cascade to link work types automatically.

```ts
type ProjectImportResponse = {
  created: number; skipped: number; errors: number; files_failed: number
  work_types_linked: number; eligibility_visible: number
  files: {
    filename: string; outcome: string; message: string | null
    created: number; skipped: number; errors: number
    rows: {
      row: number; name: string | null; outcome: string; message: string | null
      project_id: string | null; work_types_linked: number
      eligibility_visible: boolean; missing_for_eligibility: string[]
    }[]
  }[]
}
```

`missing_for_eligibility` lists exactly what a row lacks to be screenable — the
most actionable field in the response, and the one to surface in the UI.

### Work types — `work_types.py`, prefix `/api/v1`

| Method | Path | Role | Response |
|---|---|---|---|
| GET | `/work-types` | Auth | *paged* `WorkTypeResponse` |
| GET | `/work-types/{id}` | Auth | `WorkTypeResponse` |
| POST | `/work-types` | **ADMIN** | **201** `WorkTypeResponse` |
| PATCH | `/work-types/{id}` | **ADMIN** | `WorkTypeResponse` |
| POST | `/work-types/{id}/deactivate` | **ADMIN** | `WorkTypeResponse` |
| POST | `/work-types/{id}/aliases` | **ADMIN** | **201** `AliasResponse` |
| DELETE | `/work-types/{id}/aliases/{alias_id}` | **ADMIN** | **204** |
| POST | `/projects/{project_id}/work-types` | **ADMIN** | **201** `ProjectTagResponse` |
| DELETE | `/projects/{project_id}/work-types/{work_type_id}` | **ADMIN** | **204** |

```ts
type WorkTypeResponse = {
  id: string; code: string; name: string
  category: "TELECOM_NETWORKING" | "SIGNALLING" | "AUDIO_VISUAL"
  description: string | null; is_active: boolean
  created_at: string; updated_at: string
}
type AliasResponse = {
  id: string; work_type_id: string; alias: string; normalised: string
  kind: "ABBREVIATION" | "EXPANSION" | "SYNONYM" | "VARIANT"
}
type ProjectTagResponse = {
  project_id: string; work_type_id: string
  source: "SEED" | "MANUAL" | "INFERRED"
  confidence: number | null; evidence: string | null
}
```

`alias_normalised` is **globally** unique, so two work types cannot claim the same
surface form. `AliasKind` is recorded for auditability, not behaviour — every
alias is matched identically regardless of kind.

### Company turnover — `company_turnover.py`, prefix `/api/v1/company-turnover`

| Method | Path | Role | Response |
|---|---|---|---|
| GET | `` | **MANAGER** | *paged* `TurnoverResponse` |
| POST | `` | MANAGER | **201** `TurnoverResponse` |
| PATCH | `/{financial_year}` | MANAGER | `TurnoverResponse` |
| POST | `/import` | MANAGER | `TurnoverImportResponse` |

⚠️ **Every route on this router is MANAGER+, including the read.** Reading
certified turnover is an administrative act, not a curiosity. This is the one
place the floor is genuinely raised.

`/import` extracts *candidate* figures from an xlsx/xlsm/pdf for a human to
confirm. **It never writes financial data** — that is the point.

```ts
type TurnoverResponse = {
  id: string; financial_year: string        // e.g. "2023-24"
  contractual_turnover: string               // Decimal → string
  certificate_document_id: string | null     // bare UUID, no FK
  recorded_by: string | null; recorded_at: string
}
```

Negative turnover is rejected. Amendments are audited.

### Tender retirement — `retirement.py`, prefix `/api/v1/tenders`

| Method | Path | Role | Response |
|---|---|---|---|
| GET | `/retirement/preview` | **ADMIN** | `RetirementPreviewResponse` |
| POST | `/retirement` | **ADMIN** | `RetirementResultResponse` |

**This is the only route that reaches `ARCHIVED`.**

A tender is retirable once its closing date has passed a configurable cutoff in
IST (`+05:30`, a fixed offset — `domain/retirement.py`). Retiring purges the
stored document bytes, keeps the record, and sets `purged_at` so the download
worker can tell a reclaimed document from a pending one.

```ts
type RetirementPreviewResponse = {
  cutoff: string; timezone: string            // always "+05:30"
  retirable_count: number; skipped_count: number
  documents_to_purge: number; bytes_to_reclaim: number
  unknown_closing_date: number
  truncated: boolean                          // the batch hit MAX_BATCH
  candidates: {
    tender_id: string; tender_number: string; title: string; status: string
    closing_date: string | null
    documents_to_purge: number; bytes_to_reclaim: number
    retirable: boolean; skip_reason: string | null
  }[]
}
```

`skip_reason` is one of `unknown_closing_date`, `not_yet_parsed`,
`already_archived`. **Always preview before retiring** — the operation is batched
and capped, and `truncated: true` means there are more.

### Admin — `admin.py`, prefix `/admin`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/users` | ADMIN | `limit`, `offset` | *paged* `UserResponse` |
| GET | `/users/{user_id}` | ADMIN | — | `UserResponse` |
| PATCH | `/users/{user_id}/role` | ADMIN | `{ role }` | `UserResponse` |
| PATCH | `/users/{user_id}/active` | ADMIN | `{ is_active }` | `UserResponse` |
| DELETE | `/users/{user_id}` | **SUPER_ADMIN** | — | **204** |
| GET | `/role-assignments` | ADMIN | `limit`, `offset` | *paged* `RoleAssignmentResponse` |
| POST | `/role-assignments` | ADMIN | `{ email, role }` | **201** `RoleAssignmentResponse` |
| DELETE | `/role-assignments/{assignment_id}` | ADMIN | — | **204** |
| GET | `/audit-logs` | ADMIN | see below | *paged* `AuditLogResponse` |
| GET | `/stats` | ADMIN | — | `PlatformStatsResponse` |
| GET | `/system-health` | ADMIN | — | `SystemHealthResponse` |
| GET | `/api-usage` | ADMIN | — | `ApiUsageResponse` |

⚠️ **How a role is assigned, and the two endpoints people confuse.**

Every new account is born `EMPLOYEE`, automatically, on both the register and the
Google path. Nothing needs configuring and nobody is promoted by signing up —
`AuthService._create_account` resolves the role at creation and the floor is pinned
by tests.

Changing a role afterwards is `PATCH /admin/users/{id}/role`, and the UI for it is
`/admin` under *User management*. It applies immediately and is audit-logged with
a before/after diff. **This is the endpoint to reach for.**

`/admin/role-assignments` is narrower and easy to misuse: it decides the role an
account is **born** with, is read exactly once at creation, and skips addresses
that already have an account. Promoting someone who has already signed in through
it therefore **silently does nothing**. Use it only for somebody who has not
signed in yet.

Two more server-enforced guards that the UI mirrors by hiding the control rather
than disabling it: nobody may edit their own row, and nobody may modify an account
more privileged than their own.

The elevation list decides the role an account is born with; it is never read
when authorising a request. Creating an entry for an address that already has an
account is **409**, whose `detail` names `PATCH /admin/users/{user_id}/role`. A
consumed entry cannot be revoked (also **409**). An administrator cannot
pre-provision a role above their own (**403**), and `EMPLOYEE` is rejected
(**422**) because every organisation account already starts there.

Audit-log filters: `limit`, `offset`, `actor_id` (UUID), `entity_type`, `action`,
`date_from`, `date_to`. All optional and composable.

```ts
type RoleAssignmentResponse = {
  id: string; email: string; role: Role
  assigned_by: string | null      // null = seeded by the bootstrap migration
  assigned_at: string
  consumed_at: string | null; consumed_user_id: string | null
  is_consumed: boolean
}
type AuditLogResponse = {
  id: string; action: string; entity_type: string; entity_id: string | null
  actor_id: string | null; diff: Record<string, unknown>
  ip_address: string | null; user_agent: string | null; created_at: string
}
type PlatformStatsResponse = {
  tenders_total: number; tenders_by_status: Record<string, number>
  eligibility_by_status: Record<string, number>
  users_total: number; users_active: number; users_by_role: Record<string, number>
  past_projects_total: number; documents_total: number
}
type SystemHealthResponse = {
  healthy: boolean
  components: { name: string; status: string; detail: string | null }[]
  host: { cpu_percent: number; memory_percent: number
          memory_total_mb: number; memory_used_mb: number
          disk_percent: number; disk_total_gb: number; disk_used_gb: number }
}
type ApiUsageResponse = {
  total_requests: number
  by_status_class: Record<string, number>   // e.g. "2xx"
  by_method: Record<string, number>
}
```

⚠️ `actor_id` carries **no foreign key**, so a row outlives the user who caused
it. Rendering "unknown actor" is correct and expected, not a bug.

⚠️ `reviews_total` was **removed** from `PlatformStatsResponse`; it counted review
rows and was hard-coded to `0`. `eligibility_by_status` replaced it with a real
figure.

`/admin/api-usage` reads the Prometheus counters incremented by
`ObservabilityMiddleware`. That middleware used to be imported but never
registered, so this endpoint always reported `total_requests: 0`. It is now
wired — verified live returning a real status and method breakdown.

`tenders_by_status`, `eligibility_by_status` and `users_by_role` are the natural
chart series for `/dashboard` and `/admin` — all pre-aggregated server-side.

### Observability — `observability.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/observability/logs` | **none** | `FrontendLogBatch` | **202** `{ received: number }` |
| GET | `/metrics` | HTTP **Basic** | — | Prometheus text |

```ts
type FrontendLogBatch = {
  logs: {                              // 1..100 entries per batch
    message: string                    // max 2000
    level?: "debug" | "info" | "warning" | "error"   // default "error"
    context?: Record<string, unknown> | null
    url?: string | null
    timestamp?: string | null
  }[]
}
```

The wire field is **`logs`**, not `entries`, and the response key is **`received`**,
not `accepted`. Both are pinned by integration tests; renaming either silently
breaks every deployed browser, because the client is compiled into the shipped
bundle.

`context` is bounded server-side: at most 20 keys, each value truncated to 2000
characters **including** the `[truncated]` marker, and the number of dropped keys
recorded under `_dropped_keys`. Unencodable values degrade to `repr` rather than
500ing on an error-reporting path.

This endpoint is anonymous by necessity — the errors worth capturing happen on the
landing and sign-in screens, before anyone holds a token. The rate limit is what
keeps it from being an open write amplifier, and it is charged per **entry**, not
per request. Behind the shipped nginx every anonymous caller shares the proxy's
address and therefore one bucket; that is a documented limitation, not a security
boundary.

Both endpoints **404 when disabled by settings**. `lib/telemetry.ts` treats 404 as
"feature off, stop retrying" and disables itself permanently — correct, since a
404 is a configuration answer rather than a transient error. `/metrics` is Basic
auth and is not for the frontend to call.

---

## Gaps against the plan's screen list

- **`/reviews`** — **gone.** The pending-verdict queue was removed with the
  decision surface. `INDETERMINATE` tenders are the nearest equivalent and are
  visible as a `screening_pending` count on the dashboard. There is no per-tender
  "needs a decision" list.
- **`/profile`** — read is `GET /auth/me`. No self-service update endpoint, no
  password change.
- **`/tenders`** — `GET /tenders` is EMPLOYEE+, and write actions are EMPLOYEE+,
  which is the floor role.
- **`/turnover`** — MANAGER+, including the read.
- **BOQ analytics** — no endpoint. Recompute client-side or restore deliberately.
- **`/admin/audit-logs`** — restored, and `/admin/audit-logs` is the only screen
  that needs a new page; it did not exist when this surface went away.
