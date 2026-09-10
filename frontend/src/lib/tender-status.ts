import type { TenderStatus } from "./types";

/*
 * Plain-language names for the tender lifecycle.
 *
 * The enum is the contract — `REGISTERED → DOWNLOADED → PARSED → ANALYZED → REVIEWED`,
 * any state → `ARCHIVED` — and these labels never replace it in a request or a filter
 * value. They exist because the codes describe what the *system* did, and a reader needs
 * to know what that means for them. `REGISTERED` in particular is the whole point: it is
 * the state of a tender with nothing analysable attached, which is invisible if the cell
 * only ever reads REGISTERED.
 *
 * Note the codes do not match PRD §5.2, which describes `NEW → DOWNLOADING → DOWNLOADED
 * → PARSED → APPROVED/REJECTED`. No such states exist; `DOWNLOADING`/`FAILED` belong to
 * DocumentStatus and `APPROVED`/`REJECTED` to ReviewVerdict. The enums are authoritative.
 */

export const TENDER_STATUS_LABEL: Record<TenderStatus, string> = {
  REGISTERED: "No document yet",
  DOWNLOADED: "Document attached",
  PARSED: "Details extracted",
  ANALYZED: "Analysed",
  REVIEWED: "Reviewed",
  ARCHIVED: "Archived",
};

/** Tight spots — chart axes and legends, where the full label will not fit. */
export const TENDER_STATUS_SHORT: Record<TenderStatus, string> = {
  REGISTERED: "No doc",
  DOWNLOADED: "Doc in",
  PARSED: "Extracted",
  ANALYZED: "Analysed",
  REVIEWED: "Reviewed",
  ARCHIVED: "Archived",
};

/** What the state means and what moves it on. Supplementary, never the only telling. */
export const TENDER_STATUS_HINT: Record<TenderStatus, string> = {
  REGISTERED:
    "The record exists, but no document has landed. Upload one to make it readable.",
  DOWNLOADED: "A document is stored. Extraction can read it.",
  PARSED: "Fields and the BOQ have been extracted. Analysis can run.",
  ANALYZED: "Risk, qualification and a verdict are on the record.",
  REVIEWED: "A person has checked the analysis.",
  ARCHIVED: "Closed out. Nothing further runs on it.",
};

/**
 * The state a tender is created in, and the one that means "nothing to analyse yet".
 * `DocumentService._advance` leaves it here until a document actually lands, so a queued
 * URL counts as no document — which is exactly what the reader needs to see.
 */
export const NO_DOCUMENT_STATUS: TenderStatus = "REGISTERED";
