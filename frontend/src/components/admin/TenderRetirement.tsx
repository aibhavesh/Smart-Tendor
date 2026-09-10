"use client";

import { useState } from "react";
import { Archive, TriangleAlert } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { DateField } from "@/components/ui/Field";
import { api, describeError, query } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { RetirementPreview, RetirementResult } from "@/lib/types";

/*
 * Bulk retirement of expired tenders.
 *
 * The operation destroys stored PDFs, so nothing here happens without a preview
 * first: the operator sees the exact list, the cutoff it was computed from and
 * the timezone that cutoff means, before anything is unlinked.
 *
 * Two things this panel has to say plainly, because getting either wrong is
 * expensive and silent.
 *
 * What is destroyed and what is kept. Purging reclaims the megabytes and keeps
 * the kilobytes — the tender, its metadata, its BOQ lines, its reviews and its
 * eligibility result all survive, because they are what later analysis is
 * measured against.
 *
 * What is deliberately not selected. A tender whose closing date was never
 * extracted has an absent date, not a past one, and no date filter can reach it.
 * Those are counted here rather than left to be inferred from a total that does
 * not add up.
 */

const SKIP_LABELS: Record<string, string> = {
  unknown_closing_date: "closing date unknown",
  not_yet_parsed: "not yet extracted",
  already_archived: "already archived",
};

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 MB";
  const mb = bytes / (1024 * 1024);
  if (mb < 1) return "under 1 MB";
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

export function TenderRetirement() {
  const [cutoff, setCutoff] = useState("");
  const [preview, setPreview] = useState<RetirementPreview | null>(null);
  const [result, setResult] = useState<RetirementResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadPreview() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setPreview(
        await api.get<RetirementPreview>(
          `/api/v1/tenders/retirement/preview${query({ cutoff: cutoff || undefined })}`,
        ),
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<RetirementResult>("/api/v1/tenders/retirement", {
        cutoff: preview.cutoff,
        tender_ids: preview.candidates.filter((c) => c.retirable).map((c) => c.tender_id),
      });
      setResult(res);
      setPreview(null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Retire expired tenders"
        description="Reclaims storage from tenders past their closing date by deleting their stored PDFs. The tender record itself is kept. Preview first — nothing is deleted until you confirm the list."
      />

      {error ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink mb-4"
        >
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap items-end gap-3">
        <DateField
          label="Closing before"
          value={cutoff}
          onChange={(e) => setCutoff(e.target.value)}
        />
        <Button size="sm" variant="secondary" disabled={busy} onClick={loadPreview}>
          {busy && !preview ? "Checking…" : "Preview selection"}
        </Button>
      </div>
      <p className="text-mini text-ink-muted mt-2">
        Leave the date blank to use today. Tenders closing on the cutoff date are still open and are
        not selected.
      </p>

      {preview ? (
        <div className="mt-5">
          <p className="text-caption text-ink">
            Cutoff <span className="font-semibold">{formatDate(preview.cutoff)}</span> (
            {preview.timezone}) · {preview.retirable_count} tender
            {preview.retirable_count === 1 ? "" : "s"} selected ·{" "}
            {preview.documents_to_purge} document{preview.documents_to_purge === 1 ? "" : "s"} ·{" "}
            {formatBytes(preview.bytes_to_reclaim)} reclaimed
          </p>

          <div className="mt-3 rounded-control border border-state-danger/30 bg-state-danger/10 px-3 py-2.5">
            <p className="flex items-start gap-2 text-caption text-state-danger-ink">
              <TriangleAlert className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
              <span>
                <span className="font-semibold">
                  This permanently deletes {preview.documents_to_purge} stored PDF
                  {preview.documents_to_purge === 1 ? "" : "s"}.
                </span>{" "}
                The files cannot be recovered unless the source link still works.
              </span>
            </p>
            <p className="text-mini text-ink-muted mt-2">
              Kept for every tender listed: the tender record, its extracted metadata, its bill of
              quantities, every correction and verdict, and its eligibility result. Each tender is
              moved to ARCHIVED so it leaves the working queue.
            </p>
          </div>

          {preview.unknown_closing_date > 0 ? (
            <p className="mt-3 text-caption text-ink-muted">
              <span className="font-semibold text-ink">
                {preview.unknown_closing_date} tender
                {preview.unknown_closing_date === 1 ? " has" : "s have"} no closing date
              </span>{" "}
              and cannot be selected by any cutoff. An absent date is not a past one. Set a closing
              date on those tenders if they should be retired.
            </p>
          ) : null}

          {preview.truncated ? (
            <p className="mt-2 text-caption text-state-danger-ink">
              More tenders matched than one operation may take. Run this again afterwards to
              continue.
            </p>
          ) : null}

          {preview.candidates.length > 0 ? (
            <div className="mt-3">
              <Table>
                <THead>
                  <TH>Tender</TH>
                  <TH>Closing</TH>
                  <TH>Status</TH>
                  <TH>Documents</TH>
                  <TH>Action</TH>
                </THead>
                <TBody>
                  {preview.candidates.map((c) => (
                    <TR key={c.tender_id}>
                      <TD className="whitespace-nowrap">{c.tender_number}</TD>
                      <TD className="text-caption text-ink-muted">
                        {c.closing_date ? formatDate(c.closing_date) : "—"}
                      </TD>
                      <TD className="text-mini text-ink-muted">{c.status}</TD>
                      <TD className="text-caption text-ink-muted">
                        {c.documents_to_purge > 0
                          ? `${c.documents_to_purge} · ${formatBytes(c.bytes_to_reclaim)}`
                          : "—"}
                      </TD>
                      <TD className="text-mini">
                        {c.retirable ? (
                          <span className="font-semibold text-state-danger-ink">
                            Purge documents
                          </span>
                        ) : (
                          <span className="text-ink-muted">
                            Skipped — {SKIP_LABELS[c.skip_reason ?? ""] ?? c.skip_reason}
                          </span>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          ) : (
            <p className="mt-3 text-caption text-ink-muted">
              Nothing matches this cutoff. No tender has expired documents to reclaim.
            </p>
          )}

          {preview.retirable_count > 0 ? (
            <div className="mt-4 flex items-center gap-2">
              <ConfirmButton
                label={`Purge ${preview.documents_to_purge} document${
                  preview.documents_to_purge === 1 ? "" : "s"
                }`}
                confirmLabel="Delete the files"
                onConfirm={execute}
                disabled={busy}
              />
              <Button size="sm" variant="ghost" onClick={() => setPreview(null)}>
                Cancel
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <div className="mt-5 rounded-control border border-ink-strong/15 bg-surface/60 px-3 py-2.5">
          <p className="flex items-start gap-2 text-caption text-ink">
            <Archive className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
            <span>
              <span className="font-semibold text-state-go-ink">
                {result.documents_purged} document{result.documents_purged === 1 ? "" : "s"} purged,{" "}
                {formatBytes(result.bytes_reclaimed)} reclaimed.
              </span>{" "}
              {result.tenders_archived} tender{result.tenders_archived === 1 ? "" : "s"} archived.
            </span>
          </p>
          <p className="text-mini text-ink-muted mt-2">Kept: {result.retained}.</p>
          {result.failures.length > 0 ? (
            <p className="text-mini text-state-danger-ink mt-2">
              {result.failures.length} file{result.failures.length === 1 ? "" : "s"} could not be
              deleted and {result.failures.length === 1 ? "is" : "are"} unchanged. Running this
              again will retry {result.failures.length === 1 ? "it" : "them"}.
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
