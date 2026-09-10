"use client";

import { useState } from "react";
import { FileUp } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError } from "@/lib/api";
import type { BulkImportResult } from "@/lib/types";

/*
 * Bulk import from a spreadsheet.
 *
 * The endpoint parses the upload with **openpyxl**, so it takes an Excel workbook — not
 * CSV, despite the route being commonly described that way. Offering a .csv picker here
 * would hand the server a file it cannot open.
 *
 * Per-row outcomes are reported rather than failing the whole file, so the result is a
 * table: a run that creates 40 and skips 2 duplicates is a success with detail, and
 * hiding the skipped rows behind a count would lose what the operator actually needs.
 *
 * `onClose` is optional because the panel has had two homes: it renders open on the
 * upload screen, and can still be folded behind a toggle wherever that fits better.
 */
export function SpreadsheetImport({
  onImported,
  onClose,
}: {
  onImported: () => void;
  onClose?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkImportResult | null>(null);

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.upload<BulkImportResult>("/tenders/import", form);
      setResult(res);
      onImported();
    } catch (err) {
      setError(
        describeError(err, {
          422: "That file could not be read as a spreadsheet. It must be .xlsx with headings in row 1.",
          500: "The server could not open that file. It must be a real .xlsx workbook, not a CSV.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="w-full">
      <CardHeader
        title="Import tenders from a spreadsheet"
        description="Excel (.xlsx). Row 1 must hold the column headings. Common spellings are understood — TENDER NO., WORK, VALUE, DIVISION and TENDER LINK map to tender number, title, value, department and source link. A row with a link has its document downloaded automatically. Each row is processed independently — duplicates are skipped, not fatal."
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

      <label
        className={`inline-flex items-center justify-center gap-2 h-9 px-4 rounded-control text-ui leading-5 font-semibold cursor-pointer transition-colors ${
          busy ? "bg-brand-hover/60 text-white cursor-wait" : "bg-brand-hover hover:bg-brand-deep text-white"
        }`}
      >
        <FileUp className="w-3.5 h-3.5" aria-hidden="true" />
        {busy ? "Importing…" : "Choose an .xlsx file"}
        <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only" disabled={busy} onChange={onPick} />
      </label>

      {result ? (
        <div className="mt-5">
          <p className="text-caption text-ink">
            <span className="font-semibold text-state-go-ink">{result.created} created</span>
            {" · "}
            <span className="text-ink-muted">{result.skipped} skipped</span>
            {" · "}
            <span className={result.errors > 0 ? "font-semibold text-state-danger-ink" : "text-ink-muted"}>
              {result.errors} errored
            </span>
            {result.queued_documents > 0 ? (
              <>
                {" · "}
                <span className="text-ink-muted">
                  {result.queued_documents} document{result.queued_documents === 1 ? "" : "s"} queued for download
                </span>
              </>
            ) : null}
          </p>

          {result.results.length > 0 ? (
            <div className="mt-3">
              <Table>
                <THead>
                  <TH>Row</TH>
                  <TH>Tender</TH>
                  <TH>Outcome</TH>
                  <TH>Detail</TH>
                </THead>
                <TBody>
                  {result.results.slice(0, 50).map((row) => (
                    <TR key={`${row.row}-${row.tender_number ?? "?"}`}>
                      <TD className="text-caption text-ink-muted">{row.row}</TD>
                      <TD className="whitespace-nowrap">{row.tender_number ?? "—"}</TD>
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
                      </TD>
                      <TD className="text-mini text-ink-muted max-w-[40ch]">{row.message ?? "—"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              {result.results.length > 50 ? (
                <p className="text-caption text-ink-muted mt-2">
                  Showing the first 50 of {result.results.length} rows.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
