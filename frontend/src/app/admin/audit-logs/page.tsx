"use client";

import { useState } from "react";
import { ScrollText } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { Button } from "@/components/ui/Button";
import { api, query } from "@/lib/api";
import { useResource } from "@/lib/use-api";
import type { AuditLog, Page } from "@/lib/types";

const LIMIT = 25;

/*
 * The append-only audit trail.
 *
 * Every state change the services make writes a row here: who did it, to what,
 * and what the value was before and after. Two things are worth stating on the
 * screen rather than leaving to be discovered:
 *
 *   - It cannot be edited or deleted. That is the point — a log that can be
 *     rewritten proves nothing.
 *   - `actor_id` is deliberately not a foreign key, so a row outlives the user
 *     who caused it. Deleting an account must not erase the record of what they
 *     did, so an audit row with no resolvable actor is expected, not a defect.
 *
 * Filters compose and are all optional, which is how an administrator narrows to
 * one action or one window without paging through everything.
 */

function FilterBar({
  action,
  entityType,
  onApply,
  onClear,
}: {
  action: string;
  entityType: string;
  onApply: (next: { action: string; entityType: string }) => void;
  onClear: () => void;
}) {
  const [draftAction, setDraftAction] = useState(action);
  const [draftEntity, setDraftEntity] = useState(entityType);

  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
      onSubmit={(event) => {
        event.preventDefault();
        onApply({ action: draftAction.trim(), entityType: draftEntity.trim() });
      }}
    >
      <TextField
        label="Action"
        value={draftAction}
        onChange={(e) => setDraftAction(e.target.value)}
        placeholder="user.role_change"
        helper="Exact match, e.g. tender.create"
      />
      <TextField
        label="Entity type"
        value={draftEntity}
        onChange={(e) => setDraftEntity(e.target.value)}
        placeholder="Tender"
        helper="Exact match, e.g. User"
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm">
          Filter
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setDraftAction("");
            setDraftEntity("");
            onClear();
          }}
        >
          Clear
        </Button>
      </div>
    </form>
  );
}

/** One `{"field": {"before": .., "after": ..}}` pair, rendered compactly. */
function DiffCell({ diff }: { diff: Record<string, unknown> }) {
  const fields = Object.entries(diff);

  if (fields.length === 0) {
    return <span className="text-caption text-ink-muted">No field-level detail</span>;
  }

  return (
    <ul className="flex flex-col gap-1">
      {fields.map(([field, change]) => {
        const pair = change as { before?: unknown; after?: unknown };
        const show = (value: unknown) =>
          value === null || value === undefined ? "—" : String(value);
        return (
          <li key={field} className="text-caption">
            <span className="font-semibold text-ink-strong">{field}</span>
            <span className="text-ink-muted">: </span>
            <span className="text-ink-muted line-through">{show(pair?.before)}</span>
            <span className="text-ink-muted"> &rarr; </span>
            <span className="font-semibold text-brand-ink">{show(pair?.after)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function AuditBody() {
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");

  const page = useResource<Page<AuditLog>>(
    (s) =>
      api.get<Page<AuditLog>>(
        `/admin/audit-logs${query({ limit: LIMIT, offset, action, entity_type: entityType })}`,
        s,
      ),
    [offset, action, entityType],
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Audit trail
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">
          Every state-changing action, with who did it and what changed. Append-only.
        </p>
      </div>

      <Card>
        <CardHeader
          title="Filter"
          description="Leave a field blank to include everything. Filters apply to the whole query, not just this page."
        />
        <FilterBar
          action={action}
          entityType={entityType}
          onApply={(next) => {
            setAction(next.action);
            setEntityType(next.entityType);
            setOffset(0);
          }}
          onClear={() => {
            setAction("");
            setEntityType("");
            setOffset(0);
          }}
        />
      </Card>

      <Card>
        <CardHeader
          title="Entries"
          description="Newest first. A row whose actor is missing was written by a user who has since been deleted — the entry is kept deliberately."
        />

        {page.error ? (
          <ErrorState detail={page.error} onRetry={page.reload} />
        ) : page.loading || !page.data ? (
          <SkeletonRows rows={6} />
        ) : page.data.items.length === 0 ? (
          <EmptyState
            title="No matching entries"
            description="Nothing in the trail matches these filters. Clear them to see everything."
            icon={ScrollText}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TH>When</TH>
                <TH>Action</TH>
                <TH>Actor</TH>
                <TH>Change</TH>
              </THead>
              <TBody>
                {page.data.items.map((entry) => (
                  <TR key={entry.id}>
                    <TD className="text-caption text-ink-muted whitespace-nowrap">
                      {new Date(entry.created_at).toLocaleString()}
                    </TD>
                    <TD>
                      <span className="font-semibold text-ink-strong">{entry.action}</span>
                      <span className="block text-mini text-ink-muted">
                        {entry.entity_type}
                        {entry.entity_id ? ` · ${entry.entity_id}` : ""}
                      </span>
                    </TD>
                    <TD className="text-caption">
                      {entry.actor_id ? (
                        <span className="font-mono text-mini">{entry.actor_id.slice(0, 8)}</span>
                      ) : (
                        <span className="text-ink-muted">Deleted user or system</span>
                      )}
                    </TD>
                    <TD className="max-w-[46ch]">
                      <DiffCell diff={entry.diff} />
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
      <AuditBody />
    </RequireAuth>
  );
}
