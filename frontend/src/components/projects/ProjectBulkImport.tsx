"use client";

import { useState } from "react";
import { FileUp, TriangleAlert } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError } from "@/lib/api";
import type { ProjectImportFile, ProjectImportResult } from "@/lib/types";

const REASON_LABELS: Record<string, string> = {
  work_value: "no work value",
  completion_certificate_date: "no completion certificate date",
  work_type_link: "no work-type match",
};

function describeReasons(reasons: string[]): string {
  return reasons.map((reason) => REASON_LABELS[reason] ?? reason).join(", ");
}

function FileOutcome({ file }: { file: ProjectImportFile }) {
  const invisible = file.rows.filter((row) => row.outcome === "created" && !row.eligibility_visible);

  return (
    <div className="mt-4">
      <p className="text-caption text-ink">
        <span className="font-semibold">{file.filename}</span>
        {" - "}
        {file.outcome === "error" ? (
          <span className="font-semibold text-state-danger-ink">
            failed: {file.message ?? "could not be read"}
          </span>
        ) : (
          <>
            <span className="font-semibold text-state-go-ink">{file.created} created</span>
            {file.errors > 0 ? (
              <span className="font-semibold text-state-danger-ink"> - {file.errors} errored</span>
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
                  <TD className="max-w-[32ch]">{row.name ?? "-"}</TD>
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
                    {row.message ? <span className="block text-mini text-ink-muted">{row.message}</span> : null}
                  </TD>
                  <TD className="text-caption text-ink-muted">{row.work_types_linked}</TD>
                  <TD className="text-mini">
                    {row.outcome !== "created" ? (
                      <span className="text-ink-muted">-</span>
                    ) : row.eligibility_visible ? (
                      <span className="font-semibold text-state-go-ink">Yes</span>
                    ) : (
                      <span className="text-state-danger-ink">No - {describeReasons(row.missing_for_eligibility)}</span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {file.rows.length > 50 ? (
            <p className="mt-2 text-caption text-ink-muted">Showing the first 50 of {file.rows.length} rows.</p>
          ) : null}
        </div>
      ) : null}

      {invisible.length > 0 ? (
        <p className="mt-2 text-mini text-ink-muted">
          {invisible.length} imported project{invisible.length === 1 ? "" : "s"} in this file will not affect eligibility until the missing details are filled in.
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
      const imported = await api.upload<ProjectImportResult>("/api/v1/projects/import", form);
      setResult(imported);
      onImported();
    } catch (uploadError) {
      setError(
        describeError(uploadError, {
          413: "That upload is too large. Import the files in smaller batches.",
          422: "Those files could not be read. Excel workbooks must have headings in row 1.",
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
        description="Excel workbooks (.xlsx) only. Each row is one project and row 1 contains headings. PROJECT NAME, LOCATION, LOA NAME, FINAL LOA AMOUNT and COMPLETION CERTIFICATE DATED are supported. Record turnover certificates separately under Administration."
        actions={onClose ? <Button variant="ghost" size="sm" onClick={onClose}>Close</Button> : undefined}
      />

      {error ? <p role="alert" className="mb-4 rounded-control border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-caption font-semibold text-state-danger-ink">{error}</p> : null}

      <label className="mb-4 flex cursor-pointer items-start gap-2">
        <input type="checkbox" checked={autoTag} disabled={busy} onChange={(event) => setAutoTag(event.target.checked)} className="mt-0.5 accent-brand-hover" />
        <span className="text-caption text-ink">
          <span className="font-semibold">Match work types automatically</span>
          <span className="block text-mini text-ink-muted">Confident matches are linked. A project counts as eligibility evidence only when it has a work value, a completion-certificate date and at least one work-type link.</span>
        </span>
      </label>

      <label className={`inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-control px-4 text-ui font-semibold leading-5 text-white transition-colors ${busy ? "cursor-wait bg-brand-hover/60" : "bg-brand-hover hover:bg-brand-deep"}`}>
        <FileUp className="h-3.5 w-3.5" aria-hidden="true" />
        {busy ? "Importing..." : "Choose Excel files"}
        <input type="file" multiple accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only" disabled={busy} onChange={onPick} />
      </label>

      {result ? (
        <div className="mt-5">
          <p className="text-caption text-ink">
            <span className="font-semibold text-state-go-ink">{result.created} created</span>
            {" - "}<span className={result.errors > 0 ? "font-semibold text-state-danger-ink" : "text-ink-muted"}>{result.errors} errored</span>
            {" - "}<span className="text-ink-muted">{result.work_types_linked} work-type links</span>
          </p>
          {notCounted > 0 ? (
            <p className="mt-3 flex items-start gap-2 rounded-control border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-caption text-state-danger-ink">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span><span className="font-semibold">{notCounted} of {result.created} imported project{result.created === 1 ? "" : "s"} will not count towards eligibility.</span> The rows below name the missing evidence.</span>
            </p>
          ) : result.created > 0 ? <p className="mt-3 text-caption font-semibold text-state-go-ink">All imported projects will count towards eligibility.</p> : null}
          {result.files.map((file) => <FileOutcome key={file.filename} file={file} />)}
        </div>
      ) : null}
    </Card>
  );
}
