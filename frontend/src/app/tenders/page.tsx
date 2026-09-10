"use client";

import Link from "next/link";
import { useState } from "react";
import { FileWarning, Upload } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { ButtonLink } from "@/components/ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { SelectField, TextField } from "@/components/ui/Field";
import { api, query } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { canActAs } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/use-api";
import { TenderStatusTag } from "@/components/tenders/TenderStatusTag";
import { NO_DOCUMENT_STATUS, TENDER_STATUS_LABEL } from "@/lib/tender-status";
import { TENDER_STATUSES, type Page, type Tender, type TenderStatus } from "@/lib/types";

const LIMIT = 20;

function TendersBody() {
  const { user } = useAuth();
  const canWrite = canActAs(user?.role, "EMPLOYEE");

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<TenderStatus | "">("");
  const [offset, setOffset] = useState(0);

  const page = useResource<Page<Tender>>(
    (signal) => api.get(`/tenders${query({ limit: LIMIT, offset, status, search })}`, signal),
    [offset, status, search],
  );

  /*
   * How many records have nothing attached. A one-item page is the cheapest way to read
   * `total`, and it rides the same deps as the list so the number cannot go stale behind
   * a filter change or a fresh arrival.
   */
  const bare = useResource<Page<Tender>>(
    (signal) =>
      api.get(`/tenders${query({ limit: 1, offset: 0, status: NO_DOCUMENT_STATUS })}`, signal),
    [offset, status, search],
  );
  const bareCount = bare.data?.total ?? 0;
  const onlyBare = status === NO_DOCUMENT_STATUS;

  function applyFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setOffset(0); // A filter change must not leave the reader on page 4 of nothing.
    };
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
            Tenders
          </h1>
          <p className="text-ui text-ink-strong/60 mt-1.5">Search, filter and open a tender.</p>
        </div>
        {/* One way in. Registering a tender and importing a workbook both live on the
            upload screen now, alongside the document that makes the record useful. */}
        {canWrite ? (
          <ButtonLink href="/tenders/upload" size="sm">
            <Upload className="w-3.5 h-3.5" aria-hidden="true" />
            Add a tender
          </ButtonLink>
        ) : null}
      </div>

      <Card>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_220px] gap-4">
          <TextField
            label="Search"
            placeholder="Number, title or department"
            value={search}
            onChange={(e) => applyFilter(setSearch)(e.target.value)}
          />
          <SelectField
            label="Status"
            value={status}
            onChange={(e) => applyFilter(setStatus)(e.target.value as TenderStatus | "")}
          >
            <option value="">All statuses</option>
            {TENDER_STATUSES.map((s) => (
              <option key={s} value={s}>
                {TENDER_STATUS_LABEL[s]} ({s})
              </option>
            ))}
          </SelectField>
        </div>

        {/*
         * The one filter worth a shortcut. A tender with no document cannot be extracted
         * or analysed, so a pile of them is a queue nobody is working — and it is silent
         * unless the screen says the number out loud.
         */}
        <div className="mt-4 pt-4 border-t border-ink-strong/10 flex items-center gap-3 flex-wrap">
          <button
            type="button"
            aria-pressed={onlyBare}
            onClick={() => applyFilter(setStatus)(onlyBare ? "" : NO_DOCUMENT_STATUS)}
            className={`h-9 px-3.5 rounded-control text-caption font-semibold border transition-colors flex items-center gap-2 ${
              onlyBare
                ? "bg-brand/10 border-brand/30 text-brand-ink"
                : "bg-surface/60 border-ink-strong/10 text-ink-strong/70 hover:text-ink hover:bg-surface"
            }`}
          >
            <FileWarning className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            No document yet
            {/* Silent until counted — a placeholder zero would read as "none waiting". */}
            {bare.data ? (
              <span className={onlyBare ? "text-brand-ink" : "text-ink-muted"}>{bareCount}</span>
            ) : null}
          </button>
          <span className="text-mini text-ink-muted">
            {onlyBare
              ? "Showing only records with nothing attached. Add a document to move one on."
              : bare.data
                ? `${bareCount === 0 ? "No" : bareCount} tender${bareCount === 1 ? "" : "s"} ${
                    bareCount === 1 ? "is" : "are"
                  } waiting for a document.`
                : null}
          </span>
        </div>
      </Card>

      <Card>
        <CardHeader title="Results" />
        {page.error ? (
          <ErrorState detail={page.error} onRetry={page.reload} />
        ) : page.loading || !page.data ? (
          <SkeletonRows rows={8} />
        ) : page.data.items.length === 0 ? (
          <EmptyState
            title={search || status ? "No tenders match those filters" : "No tenders yet"}
            description={
              search || status
                ? "Try a broader search, or clear the status filter."
                : "Add a tender to start building the pipeline."
            }
          />
        ) : (
          <>
            <Table>
              <THead>
                <TH>Number</TH>
                <TH>Title</TH>
                <TH>Status</TH>
                <TH>Department</TH>
                <TH>Closing</TH>
              </THead>
              <TBody>
                {page.data.items.map((t) => (
                  <TR key={t.id}>
                    <TD className="whitespace-nowrap">
                      <Link
                        href={`/tenders/${t.id}`}
                        className="font-semibold text-brand-ink hover:text-brand-deep transition-colors"
                      >
                        {t.tender_number}
                      </Link>
                    </TD>
                    <TD className="max-w-[40ch] truncate">{t.title}</TD>
                    <TD>
                      <TenderStatusTag status={t.status} />
                    </TD>
                    <TD className="text-caption text-ink-muted">{t.department ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-caption text-ink-muted">
                      {formatDate(t.closing_date) ?? "—"}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={page.data} onChange={setOffset} label="tenders" />
          </>
        )}
      </Card>
    </div>
  );
}

export default function TendersPage() {
  return (
    <RequireAuth>
      <TendersBody />
    </RequireAuth>
  );
}
