"use client";

import { useState } from "react";
import { FileUp, FolderKanban, RefreshCw } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { ProjectBulkImport } from "@/components/projects/ProjectBulkImport";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { UnknownValue } from "@/components/ui/Badge";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { DateField, TextField } from "@/components/ui/Field";
import { api, describeError, query } from "@/lib/api";
import { canActAs } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/use-api";
import { formatDate, formatMoney } from "@/lib/format";
import type { Page, PastProject } from "@/lib/types";

const LIMIT = 20;

function EditProject({
  project,
  onDone,
  onCancel,
}: {
  project: PastProject;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(project.name);
  const [client, setClient] = useState(project.client ?? "");
  const [value, setValue] = useState(project.work_value ?? "");
  const [completion, setCompletion] = useState(project.completion_date ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch<PastProject>(`/projects/${project.id}`, {
        name,
        client: client || null,
        work_value: value || null,
        completion_date: completion || null,
      });
      onDone();
    } catch (err) {
      setError(describeError(err, { 422: "Check the values — work value must not be negative." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={`Edit ${project.name}`}
        description="Changing the work value can change which tenders this project qualifies."
      />
      <form onSubmit={save} className="flex flex-col gap-3">
        {error ? (
          <p
            role="alert"
            className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink"
          >
            {error}
          </p>
        ) : null}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TextField label="Name" required maxLength={1024} value={name} onChange={(e) => setName(e.target.value)} />
          <TextField label="Client" value={client} onChange={(e) => setClient(e.target.value)} />
          <TextField label="Work value" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
          <DateField label="Completion date" value={completion} onChange={(e) => setCompletion(e.target.value)} />
        </div>
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ProjectsBody() {
  const { user } = useAuth();
  const canWrite = canActAs(user?.role, "EMPLOYEE");
  const isAdmin = canActAs(user?.role, "ADMIN");

  const [offset, setOffset] = useState(0);
  const [importing, setImporting] = useState(false);
  const [backfill, setBackfill] = useState<string | null>(null);
  const [editing, setEditing] = useState<PastProject | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const page = useResource<Page<PastProject>>(
    (signal) => api.get(`/projects${query({ limit: LIMIT, offset })}`, signal),
    [offset],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
            Past projects
          </h1>
          <p className="text-ui text-ink-strong/60 mt-1.5">
            The capability portfolio qualification is checked against.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={async () => {
                setBackfill(null);
                try {
                  const res = await api.post<{ indexed: number }>("/projects/backfill");
                  setBackfill(`Indexed ${res.indexed} project(s) for semantic matching.`);
                  page.reload();
                } catch (err) {
                  setBackfill(describeError(err));
                }
              }}
            >
              <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
              Backfill index
            </Button>
          ) : null}
          {canWrite ? (
            <Button size="sm" onClick={() => setImporting((v) => !v)}>
              <FileUp className="w-3.5 h-3.5" aria-hidden="true" />
              Bulk import
            </Button>
          ) : null}
        </div>
      </div>

      {canWrite && importing ? (
        <ProjectBulkImport
          onImported={page.reload}
          onClose={() => setImporting(false)}
        />
      ) : null}

      {backfill ? (
        <p
          role="status"
          className="rounded-control border border-ink-strong/15 bg-surface/60 px-3 py-2.5 text-caption text-ink-muted"
        >
          {backfill}
        </p>
      ) : null}

      {rowError ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink"
        >
          {rowError}
        </p>
      ) : null}

      {editing ? (
        <EditProject
          project={editing}
          onDone={() => {
            setEditing(null);
            page.reload();
          }}
          onCancel={() => setEditing(null)}
        />
      ) : null}

      <Card>
        <CardHeader title="Registry" />
        {page.error ? (
          <ErrorState detail={page.error} onRetry={page.reload} />
        ) : page.loading || !page.data ? (
          <SkeletonRows rows={8} />
        ) : page.data.items.length === 0 ? (
          <EmptyState
            title="No past projects yet"
            description="Eligibility checks need a portfolio to match against. Use Bulk import to load them from the portfolio workbook or from completion certificates."
            icon={FolderKanban}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TH>Name</TH>
                <TH>Client</TH>
                <TH>Value</TH>
                <TH>Completed</TH>
                <TH>Indexed</TH>
                {canWrite ? <TH /> : null}
              </THead>
              <TBody>
                {page.data.items.map((p) => (
                  <TR key={p.id}>
                    <TD className="max-w-[34ch] truncate">{p.name}</TD>
                    <TD className="text-caption text-ink-muted">{p.client ?? "—"}</TD>
                    <TD className="whitespace-nowrap">{formatMoney(p.work_value) ?? "—"}</TD>
                    <TD className="text-caption text-ink-muted whitespace-nowrap">
                      {formatDate(p.completion_date) ?? "—"}
                    </TD>
                    <TD>
                      {p.embedding_indexed ? (
                        <span className="text-caption text-state-go-ink font-semibold">Yes</span>
                      ) : (
                        <UnknownValue label="NOT INDEXED" />
                      )}
                    </TD>
                    {canWrite ? (
                      <TD className="text-right whitespace-nowrap">
                        <span className="inline-flex items-center gap-2">
                          <Button size="sm" variant="secondary" onClick={() => setEditing(p)}>
                            Edit
                          </Button>
                          <ConfirmButton
                            label="Delete"
                            confirmLabel="Delete permanently"
                            onConfirm={async () => {
                              setRowError(null);
                              try {
                                await api.del(`/projects/${p.id}`);
                                page.reload();
                              } catch (err) {
                                setRowError(describeError(err));
                              }
                            }}
                          />
                        </span>
                      </TD>
                    ) : null}
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={page.data} onChange={setOffset} label="projects" />
          </>
        )}
      </Card>
    </div>
  );
}

export default function ProjectsPage() {
  return (
    <RequireAuth>
      <ProjectsBody />
    </RequireAuth>
  );
}
