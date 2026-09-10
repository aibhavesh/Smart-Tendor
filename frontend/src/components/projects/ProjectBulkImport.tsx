"use client";

import { useState } from "react";
import { FileUp, TriangleAlert } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError } from "@/lib/api";
import type { ProjectImportFile, ProjectImportResult } from "@/lib/types";

/*
 * Bulk import of past projects from PDFs and Excel workbooks.
 *
 * Two things this panel exists to make impossible to miss.
 *
 * First, a partial import. A file that fails is reported beside the ones that
 * succeeded rather than failing the batch, so the result is a table per file and
 * a table of rows within it — the same convention the tender import uses.
 *
 * Second, and the reason the panel is this wordy: an imported project is only
 * counted as eligibility evidence when it has a work value, a completion
 * certificate date, and at least one work-type link. Import thirty projects
 * missing any of the three and eligibility does not move, with nothing on screen
 * explaining why. So the automatic linking is stated before the upload, and
 * every project that will not count is listed afterwards with the reason.
 */

const REASON_LABELS: Record<string, string> = {
  work_value: "no work value",
  completion_certificate_date: "no completion certificate date",
  work_type_link: "no work-type match",
};

function describeReasons(reasons: string[]): string {
  return reasons.map((r) => REASON_LABELS[r] ?? r).join(", ");
}

function FileOutcome({ file }: { file: ProjectImportFile }) {
  const invisible = file.rows.filter((r) => r.outcome === "created" && !r.eligibility_visible);

  return (
    <div className="mt-4">
      <p className="text-caption text-ink">
        <span className="font-semibold">{file.filename}</span>
        {" — "}
        {file.outcome === "error" ? (
          <span className="font-semibold text-state-danger-ink">
            failed: {file.message ?? "could not be read"}
          </span>
        ) : (
          <>
            <span className="font-semibold text-state-go-ink">{file.created} created</span>
            {file.errors > 0 ? (
              <>
                {" · "}
                <span className="font-semibold text-state-danger-ink">{file.errors} errored</span>
              </>
            ) : null}
          </>
        )}
      </p>

      {file.rows.length > 0 ? (
        <div className="mt-2">
          <Table>
            <THead>
              <TH>Row</TH>
              <TH>Project</TH>
              <TH>Outcome</TH>
              <TH>Work types</TH>
              <TH>Counts as evidence</TH>
            </THead>
            <TBody>
              {file.rows.slice(0, 50).map((row) => (
                <TR key={`${file.filename}-${row.row}`}>
                  <TD className="text-caption text-ink-muted">{row.row}</TD>
                  <TD className="max-w-[32ch]">{row.name ?? "—"}</TD>
                  <TD>
                    <span
                      className={`text-mini font-black tracking-wide ${
                        row.outcome === "created"
                          ? "text-state-go-ink"
                          : row.outcome === "skipped"
                            ? "text-ink-muted"
                            : "text-state-danger-ink"
                      }`}
                    >
                      {row.outcome.toUpperCase()}
                    </span>
                    {row.message ? (
                      <span className="block text-mini text-ink-muted">{row.message}</span>
                    ) : null}
                  </TD>
                  <TD className="text-caption text-ink-muted">{row.work_types_linked}</TD>
                  <TD className="text-mini">
                    {row.outcome !== "created" ? (
                      <span className="text-ink-muted">—</span>
                    ) : row.eligibility_visible ? (
                      <span className="font-semibold text-state-go-ink">Yes</span>
                    ) : (
                      <span className="text-state-danger-ink">
                        No — {describeReasons(row.missing_for_eligibility)}
                      </span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {file.rows.length > 50 ? (
            <p className="text-caption text-ink-muted mt-2">
              Showing the first 50 of {file.rows.length} rows.
            </p>
          ) : null}
        </div>
      ) : null}

      {invisible.length > 0 ? (
        <p className="text-mini text-ink-muted mt-2">
          {invisible.length} imported project{invisible.length === 1 ? "" : "s"} in this file will
          not affect any eligibility screen until the missing details are filled in.
        </p>
      ) : null}
    </div>
  );
}

export function ProjectBulkImport({
  onImported,
  onClose,
}: {
  onImported: () => void;
  onClose?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [autoTag, setAutoTag] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProjectImportResult | null>(null);

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length === 0) return;

    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      for (const file of picked) form.append("files", file);
      form.append("auto_tag", autoTag ? "true" : "false");
      const res = await api.upload<ProjectImportResult>("/api/v1/projects/import", form);
      setResult(res);
      onImported();
    } catch (err) {
      setError(
        describeError(err, {
          413: "That upload is too large. Import the files in smaller batches.",
          422: "Those files could not be read. Excel files must be .xlsx with headings in row 1.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  const notCounted = result ? result.created - result.eligibility_visible : 0;

  return (
    <Card className="w-full">
      <CardHeader
        title="Import past projects"
        description="Excel workbooks (.xlsx) and PDFs, several at a time. A workbook imports one project per row, with row 1 holding the headings — NAME OF WORK, CLIENT, ORDER VALUE, LOA NO and COMPLETION CERTIFICATE are understood. Each file and each row is processed independently, so one bad file never loses the rest."
        actions={
          onClose ? (
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink mb-4"
        >
          {error}
        </p>
      ) : null}

      <label className="flex items-start gap-2 mb-4 cursor-pointer">
        <input
          type="checkbox"
          checked={autoTag}
          disabled={busy}
          onChange={(e) => setAutoTag(e.target.checked)}
          className="mt-0.5 accent-brand-hover"
        />
        <span className="text-caption text-ink">
          <span className="font-semibold">Match work types automatically</span>
          <span className="block text-mini text-ink-muted">
            A past project counts towards eligibility only once it is linked to a work type. With
            this on, each imported project is matched against the taxonomy and confident matches are
            linked for you; weaker matches are listed for you to confirm. With it off, every
            imported project needs linking by hand before eligibility will see it.
          </span>
        </span>
      </label>

      <label
        className={`inline-flex items-center justify-center gap-2 h-9 px-4 rounded-control text-ui leading-5 font-semibold cursor-pointer transition-colors ${
          busy ? "bg-brand-hover/60 text-white cursor-wait" : "bg-brand-hover hover:bg-brand-deep text-white"
        }`}
      >
        <FileUp className="w-3.5 h-3.5" aria-hidden="true" />
        {busy ? "Importing…" : "Choose files"}
        <input
          type="file"
          multiple
          accept=".xlsx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="sr-only"
          disabled={busy}
          onChange={onPick}
        />
      </label>

      {result ? (
        <div className="mt-5">
          <p className="text-caption text-ink">
            <span className="font-semibold text-state-go-ink">{result.created} created</span>
            {" · "}
            <span
              className={
                result.errors > 0 ? "font-semibold text-state-danger-ink" : "text-ink-muted"
              }
            >
              {result.errors} errored
            </span>
            {result.files_failed > 0 ? (
              <>
                {" · "}
                <span className="font-semibold text-state-danger-ink">
                  {result.files_failed} file{result.files_failed === 1 ? "" : "s"} unreadable
                </span>
              </>
            ) : null}
            {" · "}
            <span className="text-ink-muted">{result.work_types_linked} work-type links</span>
          </p>

          {notCounted > 0 ? (
            <p className="mt-3 flex items-start gap-2 rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption text-state-danger-ink">
              <TriangleAlert className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
              <span>
                <span className="font-semibold">
                  {notCounted} of {result.created} imported project
                  {result.created === 1 ? "" : "s"} will not count towards eligibility.
                </span>{" "}
                A project is only used as evidence once it has a work value, a completion
                certificate date and a work-type link. The rows below name what each one is missing.
              </span>
            </p>
          ) : result.created > 0 ? (
            <p className="mt-3 text-caption text-state-go-ink font-semibold">
              All {result.created} imported project{result.created === 1 ? "" : "s"} will count
              towards eligibility.
            </p>
          ) : null}

          {result.files.map((file) => (
            <FileOutcome key={file.filename} file={file} />
          ))}
        </div>
      ) : null}
    </Card>
  );
}
