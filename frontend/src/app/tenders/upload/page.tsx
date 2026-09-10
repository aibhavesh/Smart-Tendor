"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { FileUp, Link2, Upload } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { DateField, FileField, TextField } from "@/components/ui/Field";
import { SpreadsheetImport } from "@/components/tenders/SpreadsheetImport";
import { api, describeError } from "@/lib/api";
import type { Tender, TenderDocument } from "@/lib/types";

/*
 * Add a tender — the one screen for all three ways a tender gets into the system.
 *
 *   File     POST /tenders, then POST /tenders/{id}/documents/upload. The bytes are in
 *            hand, so the document is stored DOWNLOADED and the tender is ready to
 *            extract the moment this returns.
 *   URL      POST /tenders, then POST /tenders/{id}/documents. That only *queues* a
 *            download: nothing in this deployment runs DocumentService.process_pending(),
 *            so the document sits PENDING. The helper text says so rather than letting
 *            the reader assume the file is on its way.
 *   Sheet    POST /tenders/import — many tenders at once, documents attached later.
 *
 * The first two are two calls, and the second can fail after the first has succeeded.
 * That case is reported as what it is — the tender exists, the document did not attach —
 * with a link to the record, because silently rolling back a created tender would be a
 * worse lie than an honest half-finished state.
 */

type Mode = "file" | "url" | "spreadsheet";

const MODES: { id: Mode; label: string; icon: typeof Upload; hint: string }[] = [
  { id: "file", label: "Upload a file", icon: Upload, hint: "The document is on this computer." },
  { id: "url", label: "Source URL", icon: Link2, hint: "The document lives on a portal." },
  {
    id: "spreadsheet",
    label: "Excel bulk import",
    icon: FileUp,
    hint: "Many tenders in one workbook.",
  },
];

function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div role="tablist" aria-label="How to add the tender" className="flex flex-wrap gap-2">
      {MODES.map((m) => {
        const selected = m.id === mode;
        return (
          <button
            key={m.id}
            type="button"
            role="tab"
            id={`tab-${m.id}`}
            aria-selected={selected}
            aria-controls={`panel-${m.id}`}
            onClick={() => onChange(m.id)}
            className={`h-11 px-4 rounded-control text-ui font-semibold flex items-center gap-2 border transition-colors ${
              selected
                ? "bg-brand/10 border-brand/30 text-brand-ink"
                : "bg-surface/60 border-ink-strong/10 text-ink-strong/70 hover:text-ink hover:bg-surface"
            }`}
          >
            <m.icon className="w-4 h-4 shrink-0" aria-hidden="true" />
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

function UploadBody() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("file");

  // The tender's own fields. Only number and title are required by the API; the rest are
  // sent as null when blank rather than as empty strings.
  const [number, setNumber] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [department, setDepartment] = useState("");
  const [value, setValue] = useState("");
  const [closingDate, setClosingDate] = useState("");

  const [file, setFile] = useState<File | null>(null);
  const [docUrl, setDocUrl] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [orphan, setOrphan] = useState<{ id: string; detail: string } | null>(null);

  /*
   * The document is optional: registering the record first and chasing the file later is
   * a real way of working. It is not encouraged, though — the submit says plainly what a
   * blank one produces, so the empty path is chosen rather than fallen into.
   */
  const noAttachment = mode === "file" ? !file : !docUrl.trim();

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();

    setBusy(true);
    setError(null);
    setOrphan(null);

    let tender: Tender;
    try {
      tender = await api.post<Tender>("/tenders", {
        tender_number: number.trim(),
        title: title.trim(),
        description: description.trim() || null,
        department: department.trim() || null,
        estimated_value: value.trim() || null,
        closing_date: closingDate || null,
        // In URL mode this is where the tender came from, so it belongs on the record too.
        source_url: mode === "url" ? docUrl.trim() : null,
      });
    } catch (err) {
      setError(
        describeError(err, {
          409: "A tender with that number already exists. Open the existing record and add the document there.",
          422: "Check the details — a number and a title are required, and the value cannot be negative.",
        }),
      );
      setBusy(false);
      return;
    }

    // Nothing to attach: the record stands on its own at REGISTERED.
    if (noAttachment) {
      router.push(`/tenders/${tender.id}`);
      return;
    }

    try {
      if (mode === "file" && file) {
        const form = new FormData();
        form.append("file", file);
        await api.upload<TenderDocument>(`/tenders/${tender.id}/documents/upload`, form);
      } else {
        await api.post<TenderDocument>(`/tenders/${tender.id}/documents`, {
          source_url: docUrl.trim(),
        });
      }
    } catch (err) {
      setOrphan({
        id: tender.id,
        detail: describeError(err, {
          422: "The server rejected that document. Check the file or the URL.",
        }),
      });
      setBusy(false);
      return;
    }

    router.push(`/tenders/${tender.id}`);
  }

  return (
    <div className="flex flex-col gap-6 max-w-[840px]">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Add a tender
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">
          Bring in one tender — with its document, or on its own for now — or a whole
          spreadsheet of them.
        </p>
      </div>

      <ModeTabs mode={mode} onChange={setMode} />

      {mode === "spreadsheet" ? (
        <div role="tabpanel" id="panel-spreadsheet" aria-labelledby="tab-spreadsheet">
          <SpreadsheetImport onImported={() => router.refresh()} />
        </div>
      ) : (
        <div role="tabpanel" id={`panel-${mode}`} aria-labelledby={`tab-${mode}`}>
          <Card>
            <CardHeader
              title="Tender details"
              description="The number and title identify the record. Everything else can be filled in later on the tender itself."
            />

            <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
              {error ? (
                <p
                  role="alert"
                  className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2.5 text-caption font-semibold text-state-danger-ink"
                >
                  {error}
                </p>
              ) : null}

              {orphan ? (
                <p
                  role="alert"
                  className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2.5 text-caption text-state-danger-ink"
                >
                  <span className="font-semibold">
                    The tender was created, but the document did not attach.
                  </span>{" "}
                  {orphan.detail}{" "}
                  <Link href={`/tenders/${orphan.id}`} className="font-semibold underline">
                    Open the tender
                  </Link>{" "}
                  to try the document again.
                </p>
              ) : null}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <TextField
                  label="Tender number"
                  required
                  maxLength={128}
                  value={number}
                  onChange={(e) => setNumber(e.target.value)}
                />
                <TextField
                  label="Title"
                  required
                  maxLength={1024}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
                <TextField
                  label="Department"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                />
                <TextField
                  label="Estimated value"
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  helper="In rupees. Leave blank if the tender does not state one."
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
                <DateField
                  label="Closing date"
                  value={closingDate}
                  onChange={(e) => setClosingDate(e.target.value)}
                />
                <TextField
                  label="Description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div className="border-t border-ink-strong/10 pt-4">
                {mode === "file" ? (
                  <FileField
                    label="Tender document"
                    fileName={file?.name ?? null}
                    helper="PDF or similar. Stored straight away, so the tender is ready to extract."
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                ) : (
                  <TextField
                    label="Document URL"
                    type="url"
                    maxLength={2048}
                    placeholder="https://example.gov.in/tender.pdf"
                    helper="Recorded and queued, but nothing fetches it in this deployment — the document stays PENDING and the tender stays “No document yet”, the same as leaving this blank. Upload the file to get something analysable."
                    value={docUrl}
                    onChange={(e) => setDocUrl(e.target.value)}
                  />
                )}
              </div>

              <div className="flex items-center gap-3 pt-1">
                <Button type="submit" disabled={busy}>
                  {busy
                    ? "Adding…"
                    : noAttachment
                      ? "Add tender without a document"
                      : "Add tender"}
                </Button>
                <Link
                  href="/tenders"
                  className="text-caption font-semibold text-brand-ink hover:text-brand-deep transition-colors"
                >
                  Cancel
                </Link>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}

export default function UploadTenderPage() {
  // Every write this screen makes is EMPLOYEE-gated server-side; matching that here
  // keeps the guard honest even though EMPLOYEE is currently the floor role.
  return (
    <RequireAuth minRole="EMPLOYEE">
      <UploadBody />
    </RequireAuth>
  );
}
