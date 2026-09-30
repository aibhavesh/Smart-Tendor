"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, CircleHelp, FileWarning, Upload, X } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { ButtonLink } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { SelectField, TextField } from "@/components/ui/Field";
import { api, describeError, query } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { canActAs } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/use-api";
import { TenderStatusTag } from "@/components/tenders/TenderStatusTag";
import { NO_DOCUMENT_STATUS, TENDER_STATUS_LABEL } from "@/lib/tender-status";
import { TENDER_STATUSES, type Page, type Tender, type TenderStatus } from "@/lib/types";

const LIMIT = 20;
type EligibilityStatus = "ELIGIBLE" | "NOT_ELIGIBLE" | "INDETERMINATE";

function EligibilityDecision({ status }: { status: EligibilityStatus | null | undefined }) {
  if (status === "ELIGIBLE") {
    return <span className="inline-flex items-center gap-1.5 rounded-full bg-state-go-ink px-2.5 py-1 text-mini font-black tracking-wide text-white"><Check className="h-3 w-3" aria-hidden="true" />Eligible</span>;
  }
  if (status === "NOT_ELIGIBLE") {
    return <span className="inline-flex items-center gap-1.5 rounded-full bg-state-danger px-2.5 py-1 text-mini font-black tracking-wide text-white"><X className="h-3 w-3" aria-hidden="true" />Not eligible</span>;
  }
  if (status === "INDETERMINATE") {
    return <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-deep px-2.5 py-1 text-mini font-black tracking-wide text-white"><CircleHelp className="h-3 w-3" aria-hidden="true" />Needs review</span>;
  }
  return <span className="text-caption text-ink-muted">Screening…</span>;
}

function TendersBody() {
  const { user } = useAuth();
  const canWrite = canActAs(user?.role, "EMPLOYEE");
  const canBulkDelete = canActAs(user?.role, "MANAGER");

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<TenderStatus | "">("");
  const [eligibilityStatus, setEligibilityStatus] = useState<EligibilityStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);

  const page = useResource<Page<Tender>>(
    (signal) => api.get(`/tenders${query({ limit: LIMIT, offset, status, eligibility: eligibilityStatus, search })}`, signal),
    [offset, status, eligibilityStatus, search],
  );
  const tenderIds = page.data?.items.map((tender) => tender.id).join(",") ?? "";
  const eligibility = useResource<Record<string, EligibilityStatus | null>>(
    async (signal) => {
      const rows = await Promise.all(
        (page.data?.items ?? []).map(async (tender) => {
          try {
            const result = await api.get<{ status: EligibilityStatus }>(
              `/api/v1/tenders/${tender.id}/eligibility`,
              signal,
            );
            return [tender.id, result.status] as const;
          } catch {
            return [tender.id, null] as const;
          }
        }),
      );
      return Object.fromEntries(rows);
    },
    [tenderIds],
    { enabled: tenderIds.length > 0 },
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

  async function deleteAll() {
    setDeleteMessage(null);
    try {
      const result = await api.del<{ deleted: number }>("/tenders");
      setDeleteMessage(`${result.deleted} tender${result.deleted === 1 ? "" : "s"} permanently deleted.`);
      setOffset(0);
      page.reload();
    } catch (error) {
      setDeleteMessage(describeError(error));
    }
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
        <div className="flex items-center gap-2">
          {canBulkDelete && (page.data?.total ?? 0) > 0 ? (
            <ConfirmButton
              label={`Delete all (${page.data?.total ?? 0})`}
              confirmLabel="Permanently delete all"
              onConfirm={deleteAll}
            />
          ) : null}
          {canWrite ? (
            <ButtonLink href="/tenders/upload" size="sm">
              <Upload className="w-3.5 h-3.5" aria-hidden="true" />
              Add a tender
            </ButtonLink>
          ) : null}
        </div>
      </div>

      {deleteMessage ? (
        <p
          role="status"
          className="rounded-control border border-ink-strong/10 bg-surface px-3 py-2 text-caption text-ink-strong"
        >
          {deleteMessage}
        </p>
      ) : null}

      <Card>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_220px_220px] gap-4">
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
          <SelectField label="Eligibility decision" value={eligibilityStatus} onChange={(e) => applyFilter(setEligibilityStatus)(e.target.value as EligibilityStatus | "")}>
            <option value="">All decisions</option>
            <option value="ELIGIBLE">Eligible</option>
            <option value="NOT_ELIGIBLE">Not eligible</option>
            <option value="INDETERMINATE">Needs review</option>
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
                <TH>Eligibility</TH>
                <TH>Department</TH>
                <TH>Closing</TH>
                {canWrite ? <TH className="text-right">Actions</TH> : null}
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
                    <TD>
                      <EligibilityDecision status={eligibility.data?.[t.id]} />
                    </TD>
                    <TD className="text-caption text-ink-muted">{t.department ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-caption text-ink-muted">
                      {formatDate(t.closing_date) ?? "—"}
                    </TD>
                    {canWrite ? (
                      <TD className="text-right whitespace-nowrap">
                        <ConfirmButton
                          label="Delete"
                          confirmLabel="Delete permanently"
                          onConfirm={async () => {
                            setDeleteMessage(null);
                            try {
                              await api.del(`/tenders/${t.id}`);
                              setDeleteMessage(`Tender ${t.tender_number} permanently deleted.`);
                              page.reload();
                            } catch (error) {
                              setDeleteMessage(describeError(error));
                            }
                          }}
                        />
                      </TD>
                    ) : null}
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
