import { api } from "./api";
import type { BOQItem, Tender, TenderDocument, TenderMetadata } from "./types";

export interface TenderEligibility {
  status: "ELIGIBLE" | "NOT_ELIGIBLE" | "INDETERMINATE";
  is_stale: boolean;
  financial_pass: boolean | null;
  technical_pass: boolean | null;
  rule_satisfied: string | null;
  reasons: string[];
}

/*
 * Tender detail loading.
 *
 * Most of these endpoints legitimately 404 before the relevant stage has run — there is
 * no metadata before extraction, no recommendation before analysis, no report before the
 * narrative step. Those are not errors to surface; they are "not yet". Only the tender
 * itself is required, so it is awaited first and everything else is settled in parallel
 * with a missing result mapped to null.
 */

/** null = not available yet (or the caller may not see it), which the UI states plainly. */
export interface TenderDetail {
  tender: Tender;
  documents: TenderDocument[] | null;
  metadata: TenderMetadata | null;
  boq: BOQItem[] | null;
  eligibility: TenderEligibility | null;
}

async function optional<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch {
    return null;
  }
}

export async function fetchTenderDetail(id: string, signal?: AbortSignal): Promise<TenderDetail> {
  // Required: a missing tender is a real 404 and must reach the caller.
  const tender = await api.get<Tender>(`/tenders/${id}`, signal);

  const [documents, metadata, boq, eligibility] = await Promise.all([
    optional(api.get<TenderDocument[]>(`/tenders/${id}/documents`, signal)),
    optional(api.get<TenderMetadata>(`/tenders/${id}/metadata`, signal)),
    optional(api.get<BOQItem[]>(`/tenders/${id}/boq`, signal)),
    optional(api.get<TenderEligibility>(`/api/v1/tenders/${id}/eligibility`, signal)),
  ]);

  return { tender, documents, metadata, boq, eligibility };
}
