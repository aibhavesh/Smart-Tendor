"use client";

import { useState } from "react";
import { ScrollText } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { DateField, TextField } from "@/components/ui/Field";
import { api, query } from "@/lib/api";
import { useResource } from "@/lib/use-api";
import type { AuditLog, Page } from "@/lib/types";

const LIMIT = 25;

/** The diff is the substance of an audit row — render it, don't hide it behind a modal. */
function Diff({ diff }: { diff: Record<string, unknown> }) {
  const entries = Object.entries(diff);
  if (entries.length === 0) return <span className="text-caption text-ink-muted">—</span>;

  return (
    <ul className="flex flex-col gap-0.5">
      {entries.map(([field, change]) => {
        const c = change as { before?: unknown; after?: unknown } | null;
        const hasPair = c && typeof c === "object" && ("before" in c || "after" in c);
        return (
          <li key={field} className="text-mini">
            <span className="text-ink-muted">{field}: </span>
            {hasPair ? (
              <>
                <span className="text-ink-muted line-through">{String(c?.before ?? "—")}</span>
                <span className="text-ink-muted" aria-hidden="true">
                  {" → "}
                </span>
                <span className="font-semibold text-ink">{String(c?.after ?? "—")}</span>
              </>
            ) : (
              <span className="text-ink">{JSON.stringify(change)}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function AuditLogsBody() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const page = useResource<Page<AuditLog>>(
    (signal) =>
      api.get(
        `/admin/audit-logs${query({
          limit: LIMIT,
          offset,
          action,
          entity_type: entityType,
          date_from: dateFrom,
          date_to: dateTo,
        })}`,
        signal,
      ),
    [offset, action, entityType, dateFrom, dateTo],
  );

  function filter<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setOffset(0);
    };
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Audit logs
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">
          Append-only record of privileged actions.
        </p>
      </div>

      <Card>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <TextField
            label="Action"
            placeholder="user.role_change"
            value={action}
            onChange={(e) => filter(setAction)(e.target.value)}
          />
          <TextField
            label="Entity type"
            placeholder="User"
            value={entityType}
            onChange={(e) => filter(setEntityType)(e.target.value)}
          />
          <DateField label="From" value={dateFrom} onChange={(e) => filter(setDateFrom)(e.target.value)} />
          <DateField label="To" value={dateTo} onChange={(e) => filter(setDateTo)(e.target.value)} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Entries" />
        {page.error ? (
          <ErrorState detail={page.error} onRetry={page.reload} />
        ) : page.loading || !page.data ? (
          <SkeletonRows rows={8} />
        ) : page.data.items.length === 0 ? (
          <EmptyState
            title="No entries match those filters"
            description="Try widening the date range or clearing the action filter."
            icon={ScrollText}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TH>When</TH>
                <TH>Action</TH>
                <TH>Entity</TH>
                <TH>Change</TH>
                <TH>Address</TH>
              </THead>
              <TBody>
                {page.data.items.map((log) => (
                  <TR key={log.id}>
                    <TD className="whitespace-nowrap text-caption text-ink-muted">
                      {new Date(log.created_at).toLocaleString()}
                    </TD>
                    <TD className="whitespace-nowrap text-caption font-semibold text-ink">
                      {log.action}
                    </TD>
                    <TD className="text-caption text-ink-muted">
                      {log.entity_type}
                      {log.entity_id ? (
                        <span className="block text-mini truncate max-w-[18ch]">
                          {log.entity_id}
                        </span>
                      ) : null}
                    </TD>
                    <TD>
                      <Diff diff={log.diff} />
                    </TD>
                    <TD className="text-caption text-ink-muted whitespace-nowrap">
                      {log.ip_address ?? "—"}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={page.data} onChange={setOffset} label="entries" />
          </>
        )}
      </Card>
    </div>
  );
}

export default function AuditLogsPage() {
  return (
    <RequireAuth minRole="ADMIN">
      <AuditLogsBody />
    </RequireAuth>
  );
}
