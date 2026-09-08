"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Pencil } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { DateField, TextField } from "@/components/ui/Field";
import { api, describeError } from "@/lib/api";
import type { Tender } from "@/lib/types";

/*
 * Edit and delete for a tender (EMPLOYEE+).
 *
 * `tender_number` is deliberately absent: the API's PATCH schema omits it, because the
 * number identifies the record and a duplicate is a 409. Showing a field the server will
 * ignore would be worse than not showing it.
 */
export function EditTenderCard({
  tender,
  onSaved,
}: {
  tender: Tender;
  onSaved: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState(tender.title);
  const [department, setDepartment] = useState(tender.department ?? "");
  const [value, setValue] = useState(tender.estimated_value ?? "");
  const [closing, setClosing] = useState(tender.closing_date ?? "");
  const [description, setDescription] = useState(tender.description ?? "");

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch<Tender>(`/tenders/${tender.id}`, {
        title,
        department: department || null,
        estimated_value: value || null,
        closing_date: closing || null,
        description: description || null,
      });
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(
        describeError(err, {
          422: "Check the values — the estimated value must not be negative.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
          <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
          Edit
        </Button>
        <ConfirmButton
          label="Delete"
          confirmLabel="Delete permanently"
          onConfirm={async () => {
            try {
              await api.del(`/tenders/${tender.id}`);
              router.replace("/tenders");
            } catch (err) {
              setError(describeError(err));
            }
          }}
        />
        {error ? (
          <span role="alert" className="text-mini font-semibold text-state-danger-ink">
            {error}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <Card className="w-full">
      <CardHeader
        title={`Edit ${tender.tender_number}`}
        description="The tender number identifies the record and cannot be changed here."
      />
      <form onSubmit={save} className="flex flex-col gap-4">
        {error ? (
          <p
            role="alert"
            className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink"
          >
            {error}
          </p>
        ) : null}
        <TextField
          label="Title"
          required
          maxLength={1024}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <TextField
            label="Department"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          />
          <TextField
            label="Estimated value"
            inputMode="decimal"
            helper="Decimal string; never rounded."
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <DateField label="Closing date" value={closing} onChange={(e) => setClosing(e.target.value)} />
        </div>
        <TextField
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
