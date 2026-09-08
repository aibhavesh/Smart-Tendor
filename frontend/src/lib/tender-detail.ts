import { api } from "./api";
import type {
  AnalystReport,
  BOQAnalytics,
  BOQItem,
  Decision,
  MatchResult,
  Tender,
  TenderDocument,
  TenderMetadata,
  TenderReview,
} from "./types";

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
  boqAnalytics: BOQAnalytics | null;
  decision: Decision | null;
  report: AnalystReport | null;
  reviews: TenderReview[] | null;
  matches: MatchResult | null;
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

  const [documents, metadata, boq, boqAnalytics, decision, report, reviews, matches] =
    await Promise.all([
    optional(api.get<TenderDocument[]>(`/tenders/${id}/documents`, signal)),
    optional(api.get<TenderMetadata>(`/tenders/${id}/metadata`, signal)),
    optional(api.get<BOQItem[]>(`/tenders/${id}/boq`, signal)),
    optional(api.get<BOQAnalytics>(`/tenders/${id}/boq/analytics`, signal)),
    optional(api.get<Decision>(`/tenders/${id}/recommendation`, signal)),
    optional(api.get<AnalystReport>(`/tenders/${id}/report`, signal)),
    optional(api.get<TenderReview[]>(`/tenders/${id}/reviews`, signal)),
      optional(api.get<MatchResult>(`/tenders/${id}/matches`, signal)),
    ]);

  return { tender, documents, metadata, boq, boqAnalytics, decision, report, reviews, matches };
}
