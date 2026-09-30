"use client";

import { useState } from "react";
import { BadgeIndianRupee, FileSearch, Pencil, Upload } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { FileField, TextField } from "@/components/ui/Field";
import { ErrorState, SkeletonRows } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError, query } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { CompanyTurnover, Page, TurnoverExtraction, TurnoverImportResult } from "@/lib/types";
import { useResource } from "@/lib/use-api";

const YEAR_PATTERN = /^\d{4}-\d{2}$/;

export function CompanyTurnoverPanel() {
  const turnover = useResource<Page<CompanyTurnover>>(
    (signal) => api.get(`/api/v1/company-turnover${query({ limit: 50 })}`, signal),
    [],
  );
  const [financialYear, setFinancialYear] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [extracted, setExtracted] = useState<TurnoverExtraction[]>([]);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function edit(record: CompanyTurnover) {
    setFinancialYear(record.financial_year);
    setAmount(record.contractual_turnover);
    setMessage(null);
    setError(null);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const year = financialYear.trim();
    const value = amount.trim();
    if (!YEAR_PATTERN.test(year)) {
      setError("Use a financial year in the format YYYY-YY, for example 2024-25.");
      return;
    }
    if (!/^\d+(?:\.\d+)?$/.test(value)) {
      setError("Enter a non-negative turnover amount using digits only.");
      return;
    }

    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const existing = turnover.data?.items.find((record) => record.financial_year === year);
      if (existing) {
        await api.patch<CompanyTurnover>(`/api/v1/company-turnover/${encodeURIComponent(year)}`, {
          contractual_turnover: value,
        });
        setMessage(`Updated certified turnover for ${year}.`);
      } else {
        await api.post<CompanyTurnover>("/api/v1/company-turnover", {
          financial_year: year,
          contractual_turnover: value,
        });
        setMessage(`Recorded certified turnover for ${year}.`);
      }
      setFinancialYear("");
      setAmount("");
      turnover.reload();
    } catch (saveError) {
      setError(describeError(saveError, { 409: "A record for that financial year already exists. Try again to update it." }));
    } finally {
      setBusy(false);
    }
  }

  async function extract(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length) {
      setImportError("Choose at least one PDF, XLSX, or XLSM turnover certificate.");
      return;
    }
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    setImportBusy(true);
    setImportError(null);
    setImportWarnings([]);
    setExtracted([]);
    try {
      const result = await api.upload<TurnoverImportResult>("/api/v1/company-turnover/import", formData);
      setExtracted(result.records);
      setImportWarnings(result.warnings);
      if (!result.records.length && !result.warnings.length) {
        setImportError("No turnover figures could be found in those files.");
      }
    } catch (uploadError) {
      setImportError(describeError(uploadError));
    } finally {
      setImportBusy(false);
    }
  }

  async function applyExtracted() {
    if (!extracted.length) return;
    setImportBusy(true);
    setImportError(null);
    try {
      for (const record of extracted) {
        const existing = turnover.data?.items.find((item) => item.financial_year === record.financial_year);
        if (existing) {
          await api.patch<CompanyTurnover>(
            `/api/v1/company-turnover/${encodeURIComponent(record.financial_year)}`,
            { contractual_turnover: record.contractual_turnover },
          );
        } else {
          await api.post<CompanyTurnover>("/api/v1/company-turnover", record);
        }
      }
      setMessage(`Saved ${extracted.length} extracted turnover figure${extracted.length === 1 ? "" : "s"}.`);
      setExtracted([]);
      setImportWarnings([]);
      turnover.reload();
    } catch (applyError) {
      setImportError(describeError(applyError));
    } finally {
      setImportBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Certified company turnover"
        description="Upload a turnover certificate to detect yearly values automatically, then review and save them. You can still add or amend a figure manually."
      />
      <form onSubmit={extract} className="rounded-surface border border-ink-strong/10 bg-surface/40 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1">
            <FileField
              label="Turnover certificate"
              helper="PDF, XLSX, or XLSM. Scanned PDFs are read with OCR. Files are used for extraction and are not retained."
              accept=".pdf,.xlsx,.xlsm,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12"
              multiple
              fileName={files.length ? files.map((file) => file.name).join(", ") : null}
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
              disabled={importBusy}
            />
          </div>
          <Button type="submit" disabled={importBusy}>
            <FileSearch className="h-4 w-4" aria-hidden="true" />
            {importBusy ? "Extracting..." : "Extract turnover"}
          </Button>
        </div>
      </form>

      {importError ? <p role="alert" className="mt-4 rounded-control border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-caption font-semibold text-state-danger-ink">{importError}</p> : null}
      {importWarnings.length ? <div role="status" className="mt-4 rounded-control border border-brand-ink/20 bg-brand/5 px-3 py-2 text-caption text-ink">{importWarnings.map((warning) => <p key={warning}>{warning}</p>)}</div> : null}
      {extracted.length ? (
        <div className="mt-4 rounded-surface border border-brand-ink/20 bg-brand/5 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div><p className="font-semibold text-ink">Review extracted figures</p><p className="text-caption text-ink-muted">Save applies these figures to the matching financial years, updating an existing year if needed.</p></div>
            <Button onClick={applyExtracted} disabled={importBusy}><Upload className="h-4 w-4" aria-hidden="true" />Save extracted figures</Button>
          </div>
          <div className="mt-3 overflow-x-auto"><Table><THead><TH>Financial year</TH><TH>Certified turnover</TH><TH>Source</TH></THead><TBody>{extracted.map((record) => <TR key={`${record.source_file}-${record.financial_year}`}><TD>{record.financial_year}</TD><TD>{formatMoney(record.contractual_turnover)}</TD><TD className="text-caption text-ink-muted">{record.source_file}</TD></TR>)}</TBody></Table></div>
        </div>
      ) : null}

      <div className="my-5 border-t border-ink-strong/10" />
      <form onSubmit={save} className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <TextField
          label="Financial year"
          placeholder="2024-25"
          inputMode="numeric"
          value={financialYear}
          onChange={(event) => setFinancialYear(event.target.value)}
          required
          disabled={busy}
        />
        <TextField
          label="Certified turnover (INR)"
          placeholder="50000000"
          inputMode="decimal"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          required
          disabled={busy}
        />
        <Button type="submit" disabled={busy}>
          <BadgeIndianRupee className="h-4 w-4" aria-hidden="true" />
          {busy ? "Saving..." : "Save turnover"}
        </Button>
      </form>

      {error ? <p role="alert" className="mt-4 rounded-control border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-caption font-semibold text-state-danger-ink">{error}</p> : null}
      {message ? <p role="status" className="mt-4 rounded-control border border-state-go-ink/20 bg-state-go/10 px-3 py-2 text-caption font-semibold text-state-go-ink">{message}</p> : null}

      <div className="mt-5">
        {turnover.loading ? <SkeletonRows rows={3} /> : turnover.error ? <ErrorState detail={turnover.error} onRetry={turnover.reload} /> : turnover.data?.items.length ? (
          <Table>
            <THead><TH>Financial year</TH><TH>Certified turnover</TH><TH>Recorded</TH><TH /></THead>
            <TBody>
              {turnover.data.items.map((record) => (
                <TR key={record.id}>
                  <TD>{record.financial_year}</TD>
                  <TD className="whitespace-nowrap">{formatMoney(record.contractual_turnover)}</TD>
                  <TD className="text-caption text-ink-muted">{new Date(record.recorded_at).toLocaleDateString()}</TD>
                  <TD className="text-right"><Button size="sm" variant="secondary" onClick={() => edit(record)}><Pencil className="h-3.5 w-3.5" aria-hidden="true" />Edit</Button></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : <p className="text-caption text-ink-muted">No certified turnover years have been recorded.</p>}
      </div>
    </Card>
  );
}
