"use client";

import { useState } from "react";
import { PencilLine, Plus, X } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/Field";
import { api, describeError } from "@/lib/api";
import { canDecideVerdict } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import type { TenderReview } from "@/lib/types";
import { humanise } from "@/lib/format";

/*
 * Correcting extracted fields (EMPLOYEE+).
 *
 * This used to be impossible below MANAGER: corrections travelled on the verdict
 * endpoint, so fixing a wrong EMD figure meant simultaneously recording APPROVED
 * or REJECTED. That put a decision in the audit log before the corrected
 * recommendation had been recomputed. Corrections now stand alone, decide
 * nothing, and leave the tender in the queue.
 */

/** The ten extracted fields, mirroring METADATA_FIELDS on the server. */
const CORRECTABLE_FIELDS = [
  "work_name",
  "estimated_value",
  "emd_amount",
  "tender_fee",
  "closing_date",
  "completion_period",
  "location",
  "department",
  "eligibility_criteria",
  "scope_of_work",
] as const;

type Row = { field: string; value: string };

export function CorrectionsCard({
  tenderId,
  onSaved,
}: {
  tenderId: string;
  onSaved: () => void;
}) {
  const { user } = useAuth();
  const [rows, setRows] = useState<Row[]>([{ field: CORRECTABLE_FIELDS[0], value: "" }]);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<TenderReview | null>(null);

  const filled = rows.filter((r) => r.field && r.value.trim());

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const review = await api.post<TenderReview>(`/tenders/${tenderId}/corrections`, {
        corrections: Object.fromEntries(filled.map((r) => [r.field, r.value.trim()])),
        comments: comments || null,
      });
      setSaved(review);
      setRows([{ field: CORRECTABLE_FIELDS[0], value: "" }]);
      setComments("");
      onSaved();
    } catch (err) {
      setError(
        describeError(err, {
          422: "Check the values — money fields must be numbers and dates must be YYYY-MM-DD.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Correct extracted fields"
        description="Corrected values are stored as verified, so the next analysis uses them. This records no decision and leaves the tender awaiting review."
      />

      <form onSubmit={submit} className="flex flex-col gap-4">
        {error ? (
          <p
            role="alert"
            className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink"
          >
            {error}
          </p>
        ) : null}

        {saved ? (
          <p
            role="status"
            className="rounded-control bg-state-go/10 border border-state-go/30 px-3 py-2 text-caption font-semibold text-state-go-ink"
          >
            Correction recorded for {Object.keys(saved.after_snapshot).map(humanise).join(", ")}.
            Re-run the analysis to see the updated recommendation.
          </p>
        ) : null}

        {rows.map((row, i) => (
          <div key={i} className="flex items-end gap-2">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1">
              <SelectField
                label="Field"
                value={row.field}
                onChange={(e) =>
                  setRows((prev) =>
                    prev.map((r, j) => (j === i ? { ...r, field: e.target.value } : r)),
                  )
                }
              >
                {CORRECTABLE_FIELDS.map((f) => (
                  <option key={f} value={f}>
                    {humanise(f)}
                  </option>
                ))}
              </SelectField>
              <TextField
                label="Corrected value"
                value={row.value}
                onChange={(e) =>
                  setRows((prev) =>
                    prev.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)),
                  )
                }
              />
            </div>
            {rows.length > 1 ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`Remove correction ${i + 1}`}
                onClick={() => setRows((prev) => prev.filter((_, j) => j !== i))}
              >
                <X className="w-3.5 h-3.5" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ))}

        <div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setRows((prev) => [...prev, { field: CORRECTABLE_FIELDS[0], value: "" }])}
          >
            <Plus className="w-3.5 h-3.5" aria-hidden="true" />
            Add another field
          </Button>
        </div>

        <TextField
          label="Note (optional)"
          maxLength={4000}
          helper="Why the value was wrong, if it is not obvious."
          value={comments}
          onChange={(e) => setComments(e.target.value)}
        />

        <div className="flex items-center gap-3 flex-wrap">
          <Button type="submit" size="sm" disabled={busy || filled.length === 0}>
            <PencilLine className="w-3.5 h-3.5" aria-hidden="true" />
            {busy ? "Saving…" : "Record correction"}
          </Button>
          {filled.length === 0 ? (
            <span className="text-mini text-ink-muted">
              Enter at least one corrected value.
            </span>
          ) : null}
        </div>

        {/*
         * The verdict control is deliberately not on this screen for anyone below
         * MANAGER — but its absence is stated rather than left silent, so nobody
         * concludes the decision step has gone missing.
         */}
        {!canDecideVerdict(user?.role) ? (
          <p className="text-mini text-ink-muted border-t border-ink-strong/10 pt-3">
            Recording an <strong>approve or reject</strong> decision is a manager action, so it
            is not available here. Corrections you save are picked up the next time the tender is
            analysed.
          </p>
        ) : null}
      </form>
    </Card>
  );
}
