"use client";

import { useState } from "react";
import { Link2, RefreshCw, Upload } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { TextField } from "@/components/ui/Field";
import { api, describeError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DocumentStatus, TenderDocument } from "@/lib/types";

/*
 * Document ingestion — the step that moves a tender REGISTERED → DOWNLOADED.
 *
 * Two paths, and they behave differently:
 *
 *   Upload  — the bytes are already in hand, so the document is stored and marked
 *             DOWNLOADED immediately, and the tender advances at once.
 *   By URL  — creates a PENDING document for a background worker to fetch. Nothing in
 *             this deployment calls `DocumentService.process_pending()`, so a URL
 *             document stays PENDING indefinitely. The UI says so rather than leaving
 *             the reader to wonder why nothing happens.
 */

const STATUS_STYLE: Record<DocumentStatus, string> = {
  PENDING: "text-ink-muted",
  DOWNLOADING: "text-brand-ink",
  DOWNLOADED: "text-state-go-ink",
  FAILED: "text-state-danger-ink",
};

function formatSize(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DocumentsCard({
  tenderId,
  documents,
  canWrite,
  onChanged,
}: {
  tenderId: string;
  documents: TenderDocument[] | null;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<null | "upload" | "url" | string>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const docs = documents ?? [];
  const pendingCount = docs.filter((d) => d.status === "PENDING").length;

  async function run(key: string, action: () => Promise<unknown>, done?: string) {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await action();
      if (done) setNotice(done);
      onChanged();
    } catch (err) {
      setError(
        describeError(err, {
          404: "That tender no longer exists.",
          422: "The server rejected that document. Check the file or the URL.",
        }),
      );
    } finally {
      setBusy(null);
    }
  }

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-picking the same file after an error
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    await run(
      "upload",
      () => api.upload<TenderDocument>(`/tenders/${tenderId}/documents/upload`, form),
      `Uploaded ${file.name}. The tender is now DOWNLOADED — you can extract.`,
    );
  }

  return (
    <Card>
      <CardHeader
        title="Documents"
        description="Extraction reads a downloaded document. Upload is immediate; a URL is queued."
      />

      {error ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink mb-4"
        >
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="rounded-control border border-ink-strong/15 bg-surface/60 px-3 py-2 text-caption text-ink mb-4"
        >
          {notice}
        </p>
      ) : null}

      {canWrite ? (
        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-wrap items-center gap-3">
            <label
              className={`inline-flex items-center justify-center gap-2 h-9 px-4 rounded-control text-ui leading-5 font-semibold cursor-pointer transition-colors ${
                busy === "upload"
                  ? "bg-brand-hover/60 text-white cursor-wait"
                  : "bg-brand-hover hover:bg-brand-deep text-white"
              }`}
            >
              <Upload className="w-3.5 h-3.5" aria-hidden="true" />
              {busy === "upload" ? "Uploading…" : "Upload a document"}
              <input
                type="file"
                className="sr-only"
                disabled={busy !== null}
                onChange={onPick}
              />
            </label>
            <span className="text-caption text-ink-muted">
              PDF or similar. Stored immediately and ready to extract.
            </span>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[280px] flex-1">
              <TextField
                label="…or fetch from a URL"
                placeholder="https://example.gov.in/tender.pdf"
                maxLength={2048}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                helper="Queued for a background download."
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              disabled={!url.trim() || busy !== null}
              onClick={() =>
                run(
                  "url",
                  async () => {
                    await api.post<TenderDocument>(`/tenders/${tenderId}/documents`, {
                      source_url: url.trim(),
                    });
                    setUrl("");
                  },
                  "Queued. It stays PENDING until a download worker processes it.",
                )
              }
            >
              <Link2 className="w-3.5 h-3.5" aria-hidden="true" />
              {busy === "url" ? "Queueing…" : "Add URL"}
            </Button>
          </div>
        </div>
      ) : null}

      {docs.length === 0 ? (
        <EmptyState
          title="No documents yet"
          description={
            canWrite
              ? "Upload one to move this tender past REGISTERED."
              : "An analyst needs to add a document before this tender can progress."
          }
          icon={Upload}
        />
      ) : (
        <>
          <Table>
            <THead>
              <TH>File</TH>
              <TH>Status</TH>
              <TH>Size</TH>
              <TH>Added</TH>
              <TH />
            </THead>
            <TBody>
              {docs.map((doc) => (
                <TR key={doc.id}>
                  <TD className="max-w-[32ch] truncate">
                    {doc.file_name ?? doc.source_url ?? "—"}
                  </TD>
                  <TD>
                    <span className={`text-caption font-semibold ${STATUS_STYLE[doc.status]}`}>
                      {doc.status}
                    </span>
                    {doc.last_error ? (
                      <span className="block text-mini text-state-danger-ink max-w-[36ch]">
                        {doc.last_error}
                      </span>
                    ) : null}
                  </TD>
                  <TD className="text-caption text-ink-muted whitespace-nowrap">
                    {formatSize(doc.file_size)}
                  </TD>
                  <TD className="text-caption text-ink-muted whitespace-nowrap">
                    {formatDate(doc.downloaded_at ?? doc.created_at) ?? "—"}
                  </TD>
                  <TD className="text-right">
                    {canWrite && doc.status === "FAILED" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy !== null}
                        onClick={() =>
                          run(
                            doc.id,
                            () => api.post(`/documents/${doc.id}/retrigger`),
                            "Queued for another download attempt.",
                          )
                        }
                      >
                        <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                        Retry
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>

          {pendingCount > 0 ? (
            <p className="text-caption text-ink-muted mt-3">
              {pendingCount} document{pendingCount === 1 ? "" : "s"} pending. URL downloads
              are handled by a background worker, which is not running in this deployment —
              upload the file directly to proceed now.
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
