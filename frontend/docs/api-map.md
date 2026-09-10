# Backend API surface map

Produced at Stop Point 2 of `docs/frontend-rebuild-plan.md`, read directly out of
`backend/src/tender_intel/api/` (routers + Pydantic schemas). This is the authoritative
contract for Phase D — per the plan's Rule 3, do not consume any shape not listed here.

Verified against the backend on 2026-08-17, then re-verified on 2026-08-21 after the
auth/RBAC rework and the correction/verdict split. One endpoint was **added** with the
owner's explicit approval to set aside the plan's Rule 1: `GET /stats` (below).

## Auth model

- Bearer access token via `Authorization: Bearer <token>` (`HTTPBearer`, `auto_error=False`).
- Role hierarchy is **numeric and ascending**, enforced by `require_role(min)` as
  `user.level >= min.level`:

  | Role | Level |
  |---|---|
  | `EMPLOYEE` | 20 |
  | `MANAGER` | 30 |
  | `ADMIN` | 40 |
  | `SUPER_ADMIN` | 50 |

  `ANALYST` and `VIEWER` are gone — collapsed into `EMPLOYEE`, which carries the full
  former analyst capability set. Level 10 and the inter-tier gaps are reserved. Source:
  `domain/enums/roles.py`.

- **"Auth"** in the tables below means any authenticated active user (`get_current_user`,
  i.e. EMPLOYEE+). A named role means `require_role(THAT_ROLE)` — that role *or higher*.
- **One endpoint is an exception**: the bid verdict uses `require_exact_roles`, admitting
  MANAGER and SUPER_ADMIN only. ADMIN outranks MANAGER on level and is still refused.
- **Sign-in supports email/password and optional Google Identity Services**, both
  restricted to `ALLOWED_EMAIL_DOMAINS` or exact `ALLOWED_EMAIL_EXCEPTIONS`.
  Password reset is not implemented.
- Deactivated accounts get `403`, not `401`. A refused email domain is also `403`.

## Error envelope

Every handled error returns `{"detail": "<message>"}`. Mapping from `api/errors.py`:

| Domain error | HTTP | Default message |
|---|---|---|
| `EntityNotFoundError` | **404** | Resource not found. |
| `DuplicateEntityError` | **409** | Resource already exists. |
| `InvalidStatusTransitionError` | **409** | Invalid state transition. |
| `AuthenticationError` | **401** | Invalid credentials. (`WWW-Authenticate: Bearer`) |
| `InvalidTokenError` | **401** | Invalid or expired token. |
| `InactiveUserError` | **403** | Account is deactivated. |
| `PermissionDeniedError` | **403** | Insufficient permissions. |
| `DomainValidationError` | **422** | Invalid request. |
| unhandled | **500** | generic |

⚠️ **422 is overloaded.** It is both FastAPI's request-validation status *and* the mapping
for `DomainValidationError`. Verified against a live server:

| Call on a `REGISTERED` tender | Status |
|---|---|
| `POST /tenders/{id}/analyze` | **422** (not 409) |
| `POST /tenders/{id}/extract` | **422** |
| `GET /tenders/{id}/recommendation` | **422** |
| `GET /tenders/{id}/report` | **422** |
| `GET /tenders/{id}/metadata` | **404** |
| `GET /tenders/{id}/boq` | **200** `[]` |

So a stage-gated action fails with 422, while a missing sub-resource may be 404, 422 or an
empty 200 depending on the endpoint. Do not assume one shape.

⚠️ Plan §8 says "400 unparsed tender". **There is no 400 in the map** — acting on a tender
in the wrong lifecycle state raises `InvalidStatusTransitionError` → **409**.

## Lifecycle

`domain/enums/tender_status.py` — `TenderStatus`:

```
REGISTERED → DOWNLOADED → PARSED → ANALYZED → REVIEWED
```

Any state → `ARCHIVED` (terminal). `ANALYZED → PARSED` and `REVIEWED → ANALYZED` are legal
(re-analysis after a correction).

⚠️ Plan §8's `NEW / DOWNLOADING / APPROVED / REJECTED / FAILED` states **do not exist** on
the tender. `DOWNLOADING` and `FAILED` are `DocumentStatus` values (per-document, separate
enum: `PENDING`, `DOWNLOADING`, `DOWNLOADED`, `FAILED`). `APPROVED`/`REJECTED` are
`ReviewVerdict` values, not tender states.

Gating consequence: analysis is available when the tender is `PARSED` (the
`PARSED → ANALYZED` transition). Earlier states must disable the action, not attempt it.

## Pagination

Every list endpoint below marked *paged* returns:

```ts
{ items: T[], total: number, limit: number, offset: number, has_more: boolean }
```

Query params: `limit` (default 50, 1..MAX_LIMIT), `offset` (default 0).

## Endpoints

### Health — `health.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/health` | **none** | — | `{ status: string, version: string }` |

### Operational statistics — `stats.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/stats` | Auth | — | `OperationalStatsResponse` |

```ts
type OperationalStatsResponse = {
  tenders_total: number
  tenders_by_status: Record<string, number>
  past_projects_total: number
  reviews_pending: number   // ANALYZED but not yet REVIEWED — same definition as
}                           // GET /reviews/pending, so the two cannot disagree
```

**Added 2026-08-18** to remove a client-side workaround: without it a non-admin dashboard
had to issue one `GET /tenders?status=…&limit=1` per lifecycle state and read `total` off
each envelope. `/admin/stats` answers the same question but is ADMIN-only and carries user
and account figures; this surface deliberately omits those, and every figure it does
return is an aggregate over records the caller can already page through.

### Auth — `auth.py`, prefix `/auth`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/auth/google` | none | `{ id_token }` | `TokenResponse` |
| POST | `/auth/refresh` | none | `{ refresh_token }` | `TokenResponse` |
| POST | `/auth/logout` | none | `{ refresh_token }` | **204** no body |
| GET | `/auth/me` | Auth | — | `UserResponse` |

`/auth/register`, `/auth/login`, `/auth/forgot-password` and `/auth/reset-password` were
**removed**. Google sign-in is the only way an account is created: the address must be on
an allowed organisation domain (`403` otherwise), and the account is born `EMPLOYEE` unless
an administrator pre-provisioned a higher role for it first.

```ts
type TokenResponse = { access_token: string; refresh_token: string; token_type: string; expires_in: number }
type UserResponse = {
  id: string; email: string; full_name: string; role: Role
  is_active: boolean; created_at: string; last_login_at: string | null
}
```

### Tenders — `tenders.py`, prefix `/tenders`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders` | EMPLOYEE | `TenderCreateRequest` | **201** `TenderResponse` |
| GET | `/tenders` | Auth | `limit`, `offset`, `status`, `search` | *paged* `TenderResponse` |
| GET | `/tenders/{tender_id}` | Auth | — | `TenderResponse` |
| PATCH | `/tenders/{tender_id}` | EMPLOYEE | `TenderPatchRequest` | `TenderResponse` |
| DELETE | `/tenders/{tender_id}` | EMPLOYEE | — | **204** no body |
| POST | `/tenders/import` | EMPLOYEE | multipart `file` — **Excel .xlsx** | `BulkImportResponse` |

Note the list filter query param is **`status`** (aliased from `status_filter`).

```ts
type TenderResponse = {
  id: string; tender_number: string; title: string; status: TenderStatus
  description: string | null; estimated_value: string | null   // Decimal → string
  closing_date: string | null; source_url: string | null; department: string | null
  created_at: string; updated_at: string
}
// Create: tender_number (1..128), title (1..1024), description?, estimated_value? (>=0),
//         closing_date?, source_url?, department?
// Patch: same minus tender_number, all optional
type BulkImportResponse = {
  created: number; skipped: number; errors: number
  results: { row: number; tender_number: string | null; outcome: string; message: string | null }[]
}
```

Duplicate `tender_number` → **409**.

⚠️ `/tenders/import` takes an **Excel workbook, not CSV** — `infrastructure/excel.py`
parses it with `openpyxl.load_workbook`. Row 1 is the header; `tender_number` and `title`
are required. Duplicates come back as skipped rows, not as a failed request.

### Documents — `documents.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders/{tender_id}/documents` | EMPLOYEE | `{ source_url (1..2048) }` | **201** `DocumentResponse` |
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

`retrigger` is the retry path for a `FAILED` **document** — this is what plan §8 was
reaching for when it described a retryable tender state.

### Extraction — `extraction.py`, prefix `/tenders/{tender_id}`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders/{tender_id}/extract` | EMPLOYEE | — | `ExtractionResponse` |
| GET | `/tenders/{tender_id}/metadata` | Auth | — | `MetadataResponse` |
| GET | `/tenders/{tender_id}/boq` | Auth | — | `BOQItemResponse[]` (**not paged**) |
| GET | `/tenders/{tender_id}/boq/analytics` | Auth | — | `BOQAnalyticsResponse` |

```ts
type MetadataFieldResponse = {
  value: string | null      // serialised; null when UNKNOWN
  confidence: number        // 0.0..1.0 — must be rendered wherever value is shown
  source: string | null
  is_known: boolean         // false ⇒ render the UNKNOWN treatment, not an empty cell
}
type MetadataResponse = {
  tender_id: string
  fields: Record<string, MetadataFieldResponse>   // keys = METADATA_FIELDS
  known_field_count: number
}
type BOQItemResponse = {
  id: string; item_number: string | null; description: string
  unit: string | null; quantity: string | null; unit_rate: string | null
  amount: string | null; category: string | null; confidence: number
}
type BOQAnalyticsResponse = {
  total_items: number; items_with_amount: number; total_value: string
  categories: { category: string; item_count: number; total_quantity: string
                total_value: string; value_share: number }[]
}
type ExtractionResponse = {
  tender_id: string; status: string; metadata: MetadataResponse; boq_item_count: number
}
```

`is_known: false` is the **UNKNOWN** signal the plan §7 primitive must key off.

### Past projects — `projects.py`, prefix `/projects`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/projects` | EMPLOYEE | `PastProjectCreateRequest` | **201** `PastProjectResponse` |
| POST | `/projects/from-document` | EMPLOYEE | multipart file | **201** `PastProjectResponse` |
| GET | `/projects` | Auth | `limit`, `offset` | *paged* `PastProjectResponse` |
| GET | `/projects/{project_id}` | Auth | — | `PastProjectResponse` |
| PATCH | `/projects/{project_id}` | EMPLOYEE | `PastProjectPatchRequest` | `PastProjectResponse` |
| DELETE | `/projects/{project_id}` | EMPLOYEE | — | **204** no body |
| POST | `/projects/backfill` | **ADMIN** | — | `{ indexed: number }` |

```ts
type PastProjectResponse = {
  id: string; name: string; client: string | null; work_value: string | null
  category: string | null; location: string | null; description: string | null
  completion_date: string | null; embedding_indexed: boolean; created_at: string
}
// Create: name (1..1024), client?, work_value? (>=0), category?, location?,
//         description?, completion_date?   |  Patch: all optional
```

### Matching — `matching.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/tenders/{tender_id}/matches` | Auth | — | `MatchResponse` |

```ts
type MatchResponse = {
  query: string; min_required_value: string | null
  candidates: { project_id: string; name: string; similarity: number; eligible: boolean
                work_value: string | null; category: string | null
                location: string | null; reasons: string[] }[]
}
```

### Decision — `decisions.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders/{tender_id}/analyze` | EMPLOYEE | — | `DecisionResponse` |
| GET | `/tenders/{tender_id}/recommendation` | Auth | — | `DecisionResponse` |

```ts
type DecisionResponse = {
  tender_id: string
  qualification: {
    qualified: boolean
    rules: { name: string; passed: boolean; detail: string
             required: string | null; actual: string | null
             qualifying_project_id: string | null
             qualifying_project_name: string | null }[]
  }
  risk: {
    overall_severity: string          // RiskLevel: NONE | LOW | MEDIUM | HIGH
    overall_score: number             // 0..10
    overall_category: string | null   // category of the highest finding
    categories: { category: string; severity: string; score: number
                  evidence: string[]; mitigations: string[] }[]
  }
  recommendation: {
    verdict: string                   // GO | REVIEW | NO_BID
    win_probability: number           // percentage points; 0 for NO_BID
    confidence: number                // 0.0..1.0
    pros: string[]; cons: string[]
    document_checklist: string[]
    applied_rules: string[]           // ← the rule trail; this is what makes the
  }                                   //   verdict rule-derived, not model opinion
  verdict_is_stale: boolean           // ← the RECORDED verdict is superseded, not this
}                                     //   payload. See "Staleness" below.
```

Risk categories (`domain/enums/risk.py`): `PERFORMANCE_GUARANTEE`, `LIQUIDATED_DAMAGES`,
`OEM_DEPENDENCY`, `SHORT_COMPLETION_TIME`, `HIGH_EMD`, `SPECIAL_CLAUSES`.

`applied_rules` is the evidence for plan §8's requirement that the recommendation never be
presented as the model's opinion. `POST /analyze` requires the tender at `PARSED`.

### Analyst report — `analyst.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/tenders/{tender_id}/report` | Auth | — | `AnalystReportResponse` |

```ts
type AnalystReportResponse = {
  tender_id: string; verdict: string; win_probability: number
  confidence: number; generated_by: string      // ← surface as provenance
  sections: Record<string, string>              // ← the AI narrative; commentary only
  verdict_is_stale: boolean                     // ← see DecisionResponse
}
```

`sections` is the only genuinely generated prose in the API. Per plan §8 it renders
*alongside* the decision, never as its source.

### Reviews — `reviews.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/tenders/{tender_id}/corrections` | EMPLOYEE | `CorrectionCreateRequest` | **201** `ReviewResponse` |
| POST | `/tenders/{tender_id}/verdict` | **MANAGER or SUPER_ADMIN, exactly** | `VerdictCreateRequest` | **201** `ReviewResponse` |
| GET | `/tenders/{tender_id}/reviews` | Auth | — | `ReviewResponse[]` (**not paged**) |
| GET | `/reviews/pending` | EMPLOYEE | `limit`, `offset` | *paged* `TenderResponse` |

`POST /tenders/{id}/reviews` was **removed** — it required a verdict, so a field could not
be corrected without simultaneously deciding the bid. The path still answers `GET`, so a
`POST` to it returns **405**, not 404.

A correction records no verdict and does **not** transition the tender, so a corrected
tender stays in `/reviews/pending` until somebody actually decides.

```ts
type CorrectionCreateRequest = {
  corrections: Record<string, string>    // field name → corrected value; at least one
  comments?: string | null               // max 4000
}
type VerdictCreateRequest = {
  verdict: "APPROVED" | "REJECTED"
  comments?: string | null            // max 4000
  corrections?: Record<string, string>   // applied before the transition
}
type ReviewResponse = {
  id: string; tender_id: string; reviewer_id: string
  kind: "CORRECTION" | "VERDICT"             // ← branch on this, never on `verdict`
  verdict: "APPROVED" | "REJECTED" | null    // ← null on every CORRECTION
  comments: string | null
  before_snapshot: Record<string, unknown>   // ← left side of the side-by-side
  after_snapshot: Record<string, unknown>    // ← right side
  created_at: string
  is_stale: boolean   // this verdict predates a later correction; always false for
}                     // a CORRECTION, which is not a decision and cannot be superseded
```

`before_snapshot` / `after_snapshot` are exactly the original-vs-corrected pair plan §8
requires the review screen to show side by side.

⚠️ Note the review verdict enum (`APPROVED`/`REJECTED`) is **not** the recommendation
verdict enum (`GO`/`REVIEW`/`NO_BID`). Two different badges.

### Staleness — `verdict_is_stale`

`DecisionResponse` and `AnalystReportResponse` both carry `verdict_is_stale: boolean`.

⚠️ **It does not mean the payload is stale.** Recommendations are never stored — every
read recomputes them from current metadata, so the figures returned are always current.
The flag means the tender's most recent *recorded verdict* predates a metadata correction,
so the human decision on file rests on evidence that has since changed. It is `false` when
no verdict exists.

Two things it does **not** do: it does not recompute anything, and it does not suppress or
alter the recommendation. A stale `GO` stays `GO` until a person re-runs the analysis and
records a fresh decision.

Worth knowing when rendering it: because corrections are stored at confidence 1.0 and
§13.5 caps the confidence score by the mean extraction confidence of tender value, EMD and
completion period, **the confidence score rises at the moment the recorded decision stops
being trustworthy.** Put the warning where the confidence meter is read.

### Admin — `admin.py`, prefix `/admin`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/admin/users` | ADMIN | `limit`, `offset` | *paged* `UserResponse` |
| GET | `/admin/users/{user_id}` | ADMIN | — | `UserResponse` |
| PATCH | `/admin/users/{user_id}/role` | ADMIN | `{ role: Role }` | `UserResponse` |
| PATCH | `/admin/users/{user_id}/active` | ADMIN | `{ is_active: boolean }` | `UserResponse` |
| DELETE | `/admin/users/{user_id}` | **SUPER_ADMIN** | — | **204** no body |
| GET | `/admin/role-assignments` | ADMIN | `limit`, `offset` | *paged* `RoleAssignmentResponse` |
| POST | `/admin/role-assignments` | ADMIN | `{ email, role }` | **201** `RoleAssignmentResponse` |
| DELETE | `/admin/role-assignments/{assignment_id}` | ADMIN | — | **204** no body |
| GET | `/admin/audit-logs` | ADMIN | see below | *paged* `AuditLogResponse` |

The elevation list decides the role an account is **born** with. It is never read when
authorising a request. Creating an entry for an address that already has an account is
rejected with **409**, whose `detail` names `PATCH /admin/users/{user_id}/role` as the
remedy; an already-consumed entry cannot be revoked (also **409**). An administrator
cannot pre-provision a role above their own (**403**), and `EMPLOYEE` is rejected (**422**)
because every organisation account already starts there.

```ts
type RoleAssignmentResponse = {
  id: string; email: string; role: Role
  assigned_by: string | null      // null = seeded by the bootstrap migration
  assigned_at: string
  consumed_at: string | null; consumed_user_id: string | null
  is_consumed: boolean
}
```
| GET | `/admin/stats` | ADMIN | — | `PlatformStatsResponse` |
| GET | `/admin/system-health` | ADMIN | — | `SystemHealthResponse` |
| GET | `/admin/api-usage` | ADMIN | — | `ApiUsageResponse` |

Audit-log filters: `limit`, `offset`, `actor_id` (UUID), `entity_type`, `action`,
`date_from`, `date_to` (dates).

```ts
type AuditLogResponse = {
  id: string; action: string; entity_type: string; entity_id: string | null
  actor_id: string | null; diff: Record<string, unknown>
  ip_address: string | null; user_agent: string | null; created_at: string
}
type PlatformStatsResponse = {
  tenders_total: number; tenders_by_status: Record<string, number>
  users_total: number; users_active: number; users_by_role: Record<string, number>
  past_projects_total: number; reviews_total: number; documents_total: number
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

`tenders_by_status` and `users_by_role` are the natural chart series for the `/` dashboard
and `/admin` — both are pre-aggregated server-side.

### Observability — `observability.py`, `metrics.py`

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| POST | `/observability/logs` | **none** | `FrontendLogBatch` | **202** `{ received: number }` |
| GET | `/metrics` | HTTP **Basic** | — | Prometheus text |

```ts
type FrontendLogBatch = {
  logs: {                                    // 1..100 entries per batch
    level?: "debug" | "info" | "warning" | "error"   // default "info"
    message: string                          // 1..2000
    context?: Record<string, unknown> | null
    url?: string | null                      // max 2000
    timestamp?: string | null                // max 64
  }[]
}
```

This is plan §8 / FR-705's log shipping target. Both endpoints **404 when disabled by
settings** (`log ingestion disabled` / `metrics disabled`) — the frontend logger must treat
404 as "feature off, stop retrying", not as an error worth surfacing. `/metrics` is Basic
auth and is not for the frontend to call.

## Gaps against the plan's screen list

Every route in plan §8's table has backing endpoints, with these notes:

- ~~The dashboard has no KPI source below ADMIN.~~ **Resolved** — `GET /stats` above.

- ~~**`/reviews`** — pending queue is MANAGER+, so an analyst gets 403.~~ **Resolved** —
  the queue is now EMPLOYEE+; only the verdict form inside it is gated, and its absence is
  explained on screen rather than left silent.
- **`/profile`** — read is `GET /auth/me`. There is **no** self-service update endpoint
  (no `PATCH /auth/me`). There is no password to change either: credentials live in the
  user's Google account. Profile is read-only plus logout unless the backend gains an
  endpoint — do not stub one.
- **`/tenders`** — plan §8 scopes to "Analyst, Manager" but `GET /tenders` is EMPLOYEE+.
  Read access is broader than the plan's table implies; write actions are also EMPLOYEE+,
  which is the floor role, so every authenticated user can perform them.
