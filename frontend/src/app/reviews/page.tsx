"use client";

import Link from "next/link";
import { useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { SelectField, TextField } from "@/components/ui/Field";
import { api, describeError, query } from "@/lib/api";
import { useResource } from "@/lib/use-api";
import { canDecideVerdict } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import type { Page, Tender, TenderReview, ReviewVerdict } from "@/lib/types";

const LIMIT = 20;

/** Before/after is the point of the review record — show them together, never one alone. */
function SnapshotDiff({ review }: { review: TenderReview }) {
  const keys = Array.from(
    new Set([...Object.keys(review.before_snapshot), ...Object.keys(review.after_snapshot)]),
  );
  if (keys.length === 0) {
    return <p className="text-caption text-ink-muted">No values were corrected.</p>;
  }

  const render = (v: unknown) =>
    v === null || v === undefined || v === "" ? "—" : String(v);

  return (
    <Table>
      <THead>
        <TH>Field</TH>
        <TH>Original</TH>
        <TH>Corrected</TH>
      </THead>
      <TBody>
        {keys.map((key) => {
          const before = review.before_snapshot[key];
          const after = review.after_snapshot[key];
          const changed = JSON.stringify(before) !== JSON.stringify(after);
          return (
            <TR key={key}>
              <TD className="whitespace-nowrap text-caption text-ink-muted">{key}</TD>
              <TD className={changed ? "text-ink-muted line-through" : "text-ink-muted"}>
                {render(before)}
              </TD>
              <TD className={changed ? "font-semibold text-ink" : "text-ink-muted"}>
                {render(after)}
              </TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}

function ReviewForm({ tender, onDone }: { tender: Tender; onDone: () => void }) {
  const [verdict, setVerdict] = useState<ReviewVerdict>("APPROVED");
  const [comments, setComments] = useState("");
  const [corrections, setCorrections] = useState<{ field: string; value: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TenderReview | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        verdict,
        comments: comments || null,
        corrections: Object.fromEntries(
          corrections.filter((c) => c.field.trim()).map((c) => [c.field.trim(), c.value]),
        ),
      };
      const review = await api.post<TenderReview>(`/tenders/${tender.id}/verdict`, body);
      setResult(review);
      onDone();
    } catch (err) {
      setError(
        describeError(err, {
          409: "This tender is not awaiting review — it may have been reviewed already.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-caption text-ink">
          Recorded as <span className="font-semibold">{result.verdict}</span>.
        </p>
        <SnapshotDiff review={result} />
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      {error ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink"
        >
          {error}
        </p>
      ) : null}

      <SelectField
        label="Verdict"
        value={verdict}
        onChange={(e) => setVerdict(e.target.value as ReviewVerdict)}
      >
        <option value="APPROVED">APPROVED</option>
        <option value="REJECTED">REJECTED</option>
      </SelectField>

      <TextField
        label="Comments"
        maxLength={4000}
        helper="Optional. Explain anything a later reader would need."
        value={comments}
        onChange={(e) => setComments(e.target.value)}
      />

      <div className="flex flex-col gap-3">
        <p className="text-caption font-semibold text-ink">Corrections</p>
        {corrections.map((c, i) => (
          <div key={i} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField
              label="Field"
              value={c.field}
              onChange={(e) =>
                setCorrections((prev) =>
                  prev.map((p, j) => (j === i ? { ...p, field: e.target.value } : p)),
                )
              }
            />
            <TextField
              label="Corrected value"
              value={c.value}
              onChange={(e) =>
                setCorrections((prev) =>
                  prev.map((p, j) => (j === i ? { ...p, value: e.target.value } : p)),
                )
              }
            />
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => setCorrections((p) => [...p, { field: "", value: "" }])}
        >
          Add a correction
        </Button>
      </div>

      <Button type="submit" size="sm" disabled={busy} className="w-fit">
        {busy ? "Recording…" : "Record decision"}
      </Button>
    </form>
  );
}

function ReviewsBody() {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Tender | null>(null);
  const { user } = useAuth();
  const canDecide = canDecideVerdict(user?.role);

  const queue = useResource<Page<Tender>>(
    (signal) => api.get(`/reviews/pending${query({ limit: LIMIT, offset })}`, signal),
    [offset],
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Reviews
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">
          Tenders that have been analysed but not yet decided. A correction does not clear a
          tender from this queue — only an approve or reject does.
        </p>
      </div>

      <Card>
        <CardHeader title="Pending queue" />
        {queue.error ? (
          <ErrorState detail={queue.error} onRetry={queue.reload} />
        ) : queue.loading || !queue.data ? (
          <SkeletonRows rows={6} />
        ) : queue.data.items.length === 0 ? (
          <EmptyState
            title="Nothing awaiting review"
            description="Analysed tenders appear here for a manager to approve or reject."
            icon={ClipboardCheck}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TH>Number</TH>
                <TH>Title</TH>
                <TH>Closing</TH>
                <TH />
              </THead>
              <TBody>
                {queue.data.items.map((t) => (
                  <TR key={t.id}>
                    <TD className="whitespace-nowrap">
                      <Link
                        href={`/tenders/${t.id}`}
                        className="font-semibold text-brand-ink hover:text-brand-deep"
                      >
                        {t.tender_number}
                      </Link>
                    </TD>
                    <TD className="max-w-[38ch] truncate">{t.title}</TD>
                    <TD className="text-caption text-ink-muted whitespace-nowrap">
                      {t.closing_date ?? "—"}
                    </TD>
                    <TD className="text-right">
                      <Button
                        size="sm"
                        variant={selected?.id === t.id ? "primary" : "secondary"}
                        onClick={() => setSelected(selected?.id === t.id ? null : t)}
                      >
                        {selected?.id === t.id ? "Close" : "Review"}
                      </Button>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={queue.data} onChange={setOffset} label="tenders" />
          </>
        )}
      </Card>

      {selected ? (
        <Card>
          <CardHeader
            title={`Decide ${selected.tender_number}`}
            description="Approving or rejecting is the final bid decision. Any corrections made here are applied before it is recorded."
          />
          {canDecide ? (
            <ReviewForm
              tender={selected}
              onDone={() => {
                queue.reload();
              }}
            />
          ) : (
            /*
             * Stated, not silently missing. An employee who opens a tender here
             * should learn who decides and where their own contribution goes,
             * rather than finding a blank panel.
             */
            <div className="flex flex-col gap-3">
              <p className="text-caption text-ink">
                Approving or rejecting a tender is a manager action, so the decision form is
                not available to you.
              </p>
              <p className="text-caption text-ink-muted">
                You can still correct extracted fields on the tender itself — corrections are
                picked up the next time the tender is analysed, and the tender stays in this
                queue until somebody decides.
              </p>
              <Link
                href={`/tenders/${selected.id}`}
                className="text-caption font-semibold text-brand-ink hover:text-brand-deep w-fit"
              >
                Open {selected.tender_number} to correct its fields →
              </Link>
            </div>
          )}
        </Card>
      ) : null}
    </div>
  );
}

export default function ReviewsPage() {
  /*
   * EMPLOYEE, not MANAGER. The pending queue is readable by anyone — seeing what
   * awaits a decision is not the same as making one — so bouncing an employee off
   * this screen would hide a list they are entitled to read. The decision form
   * inside is gated separately, and its absence is explained rather than silent.
   */
  return (
    <RequireAuth minRole="EMPLOYEE">
      <ReviewsBody />
    </RequireAuth>
  );
}
