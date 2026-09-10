/**
 * Types mirroring the backend's Pydantic schemas.
 *
 * Read out of `backend/src/tender_intel/api/` and cross-checked against
 * `frontend/docs/api-map.md`. Nothing here is invented — if a shape is not in the API
 * map it does not belong in this file (plan Rule 3).
 */

import type { Role } from "./roles";

export type { Role };

/** REGISTERED → DOWNLOADED → PARSED → ANALYZED → REVIEWED; any state → ARCHIVED. */
export type TenderStatus =
  | "REGISTERED"
  | "DOWNLOADED"
  | "PARSED"
  | "ANALYZED"
  | "REVIEWED"
  | "ARCHIVED";

export const TENDER_STATUSES: TenderStatus[] = [
  "REGISTERED",
  "DOWNLOADED",
  "PARSED",
  "ANALYZED",
  "REVIEWED",
  "ARCHIVED",
];

/** Allowed transitions, mirroring `TenderStatus.can_transition_to`. */
const TRANSITIONS: Record<TenderStatus, TenderStatus[]> = {
  REGISTERED: ["DOWNLOADED", "ARCHIVED"],
  DOWNLOADED: ["PARSED", "ARCHIVED"],
  PARSED: ["ANALYZED", "ARCHIVED"],
  ANALYZED: ["REVIEWED", "PARSED", "ARCHIVED"],
  REVIEWED: ["ANALYZED", "ARCHIVED"],
  ARCHIVED: [],
};

export function canTransition(from: TenderStatus, to: TenderStatus): boolean {
  return TRANSITIONS[from].includes(to);
}

/** Analysis is the PARSED → ANALYZED step; it is unavailable in every other state. */
export function canAnalyse(status: TenderStatus): boolean {
  return canTransition(status, "ANALYZED");
}

export type DocumentStatus = "PENDING" | "DOWNLOADING" | "DOWNLOADED" | "FAILED";
export type Verdict = "GO" | "REVIEW" | "NO_BID";
export type RiskLevel = "NONE" | "LOW" | "MEDIUM" | "HIGH";
export type ReviewVerdict = "APPROVED" | "REJECTED";

/** Which act a review record captures. Stored explicitly, never inferred. */
export type ReviewKind = "CORRECTION" | "VERDICT";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

/**
 * A role pre-provisioned against an email address before that person first signs in.
 *
 * This decides the role an account is *born* with, and nothing more. It is never
 * consulted when authorising a request, and it has no effect on an account that
 * already exists — changing a live user's role is done from the Users table.
 */
export interface RoleAssignment {
  id: string;
  email: string;
  role: Role;
  /** Null when seeded by the bootstrap migration rather than by an administrator. */
  assigned_by: string | null;
  assigned_at: string;
  /** Set when an account was created from this row. */
  consumed_at: string | null;
  consumed_user_id: string | null;
  is_consumed: boolean;
}

export interface Tender {
  id: string;
  tender_number: string;
  title: string;
  status: TenderStatus;
  description: string | null;
  /** Decimal serialised as a string — never parse into a float for display. */
  estimated_value: string | null;
  closing_date: string | null;
  source_url: string | null;
  department: string | null;
  created_at: string;
  updated_at: string;
}

/** POST /tenders/import — per-row outcomes; a duplicate is skipped, not fatal. */
export interface BulkImportResult {
  created: number;
  skipped: number;
  errors: number;
  /** Rows that carried a link and had their document queued for download. */
  queued_documents: number;
  results: {
    row: number;
    tender_number: string | null;
    outcome: string;
    message: string | null;
  }[];
}

export interface TenderDocument {
  id: string;
  tender_id: string;
  source_url: string | null;
  file_name: string | null;
  file_path: string | null;
  file_size: number | null;
  mime_type: string | null;
  sha256: string | null;
  status: DocumentStatus;
  attempt_count: number;
  last_error: string | null;
  downloaded_at: string | null;
  created_at: string;
}

export interface MetadataField {
  value: string | null;
  /** 0.0–1.0. Must be rendered wherever the value is. */
  confidence: number;
  source: string | null;
  /** false ⇒ render the UNKNOWN treatment, never an empty cell. */
  is_known: boolean;
}

export interface TenderMetadata {
  tender_id: string;
  fields: Record<string, MetadataField>;
  known_field_count: number;
}

export interface BOQItem {
  id: string;
  item_number: string | null;
  description: string;
  unit: string | null;
  quantity: string | null;
  unit_rate: string | null;
  amount: string | null;
  category: string | null;
  confidence: number;
}

export interface BOQAnalytics {
  total_items: number;
  items_with_amount: number;
  total_value: string;
  categories: {
    category: string;
    item_count: number;
    total_quantity: string;
    total_value: string;
    value_share: number;
  }[];
}

export interface QualificationRule {
  name: string;
  passed: boolean;
  detail: string;
  required: string | null;
  actual: string | null;
  qualifying_project_id: string | null;
  qualifying_project_name: string | null;
}

export interface RiskCategory {
  category: string;
  severity: RiskLevel;
  /** 0–10. */
  score: number;
  evidence: string[];
  mitigations: string[];
}

export interface Decision {
  tender_id: string;
  qualification: { qualified: boolean; rules: QualificationRule[] };
  risk: {
    overall_severity: RiskLevel;
    overall_score: number;
    overall_category: string | null;
    categories: RiskCategory[];
  };
  recommendation: {
    verdict: Verdict;
    /** Percentage points; 0 for NO_BID. */
    win_probability: number;
    confidence: number;
    pros: string[];
    cons: string[];
    document_checklist: string[];
    /** The rule trail — this is what makes the verdict defensible. */
    applied_rules: string[];
  };
  /**
   * The tender's most recent *recorded verdict* predates a metadata correction.
   *
   * This does NOT mean the recommendation above is stale — recommendations are
   * never stored, and this one was recomputed from current data on this request.
   * It means the human decision on file needs revisiting.
   */
  verdict_is_stale: boolean;
}

export interface AnalystReport {
  tender_id: string;
  verdict: Verdict;
  win_probability: number;
  confidence: number;
  generated_by: string;
  /** Generated prose. Commentary alongside the decision — never its source. */
  sections: Record<string, string>;
  /** See `Decision.verdict_is_stale` — the prose itself is regenerated per request. */
  verdict_is_stale: boolean;
}

export interface MatchResult {
  query: string;
  min_required_value: string | null;
  candidates: {
    project_id: string;
    name: string;
    similarity: number;
    eligible: boolean;
    work_value: string | null;
    category: string | null;
    location: string | null;
    reasons: string[];
  }[];
}

export interface PastProject {
  id: string;
  name: string;
  client: string | null;
  work_value: string | null;
  category: string | null;
  location: string | null;
  description: string | null;
  completion_date: string | null;
  embedding_indexed: boolean;
  created_at: string;
}

export interface TenderReview {
  id: string;
  tender_id: string;
  reviewer_id: string;
  /** A correction is not a decision. Branch on this, never on `verdict`. */
  kind: ReviewKind;
  /** Null on a CORRECTION record. */
  verdict: ReviewVerdict | null;
  comments: string | null;
  /** The before/after pair is the point of the review record. */
  before_snapshot: Record<string, unknown>;
  after_snapshot: Record<string, unknown>;
  created_at: string;
  /**
   * This verdict predates a later metadata correction, so the decision rests on
   * evidence that has since changed. Always false for a correction.
   */
  is_stale: boolean;
}

export interface AuditLog {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor_id: string | null;
  diff: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

/** GET /stats — available to any authenticated user. */
export interface OperationalStats {
  tenders_total: number;
  tenders_by_status: Record<string, number>;
  past_projects_total: number;
  /** Analysed but not yet reviewed — the same definition as GET /reviews/pending. */
  reviews_pending: number;
}

/** GET /admin/stats — ADMIN+ only; adds user and account figures. */
export interface PlatformStats {
  tenders_total: number;
  tenders_by_status: Record<string, number>;
  users_total: number;
  users_active: number;
  users_by_role: Record<string, number>;
  past_projects_total: number;
  reviews_total: number;
  documents_total: number;
}

export interface SystemHealth {
  healthy: boolean;
  components: { name: string; status: string; detail: string | null }[];
  host: {
    cpu_percent: number;
    memory_percent: number;
    memory_total_mb: number;
    memory_used_mb: number;
    disk_percent: number;
    disk_total_gb: number;
    disk_used_gb: number;
  };
}

export interface ApiUsage {
  total_requests: number;
  by_status_class: Record<string, number>;
  by_method: Record<string, number>;
}
