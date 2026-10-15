"use client";

import { useResource } from "@/lib/use-api";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState, SkeletonRows } from "@/components/ui/States";
import { api } from "@/lib/api";
import type { SystemHealth } from "@/lib/types";

/*
 * Configuration health for the screening engine.
 *
 * Exists because of one specific, silent failure. Migrations create the
 * work-type tables but none of their rows, and a database provisioned that way
 * imports past projects successfully, indexes every embedding, and links zero
 * work types. Every other signal in the system then stays green: the API answers
 * normally, the database is reachable, the vector store responds, and the import
 * reports "31 created".
 *
 * The visible consequence is that stage A has no candidates to match and stage B
 * has no links to score, so every tender screens INDETERMINATE — which reads as
 * "awaiting a human" rather than "never configured", and sends the investigation
 * to the tender list instead of to here.
 *
 * Self-heals on the next past-project write, since `ensure_taxonomy` provisions
 * the list when it finds it empty. A deployment that never adds one keeps this
 * warning, which is the point: it is the only place the gap is visible.
 */

const STATUS_STYLES: Record<string, string> = {
  ok: "text-state-go-ink",
  warning: "text-state-warn-ink",
  error: "text-state-danger-ink",
};

const STATUS_LABELS: Record<string, string> = {
  ok: "OK",
  warning: "Warning",
  error: "Error",
};

export function SystemConfigurationHealth() {
  const health = useResource<SystemHealth>(
    (signal) => api.get("/admin/system-health", signal),
    [],
  );

  const taxonomy = health.data?.components.find(
    (component) => component.name === "work_type_taxonomy",
  );
  const warned = taxonomy?.status === "warning";

  return (
    <Card>
      <CardHeader
        title="Screening configuration"
        description="Screening needs a configured work-type taxonomy, certified turnover, and past projects linked to work types. An empty taxonomy is the failure that looks like success: tenders import, nothing errors, and every result reads INDETERMINATE."
      />
      {health.loading ? (
        <SkeletonRows rows={2} />
      ) : health.error ? (
        <ErrorState detail="Unable to load configuration health." onRetry={health.reload} />
      ) : taxonomy ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="text-caption text-ink-muted">Work-type taxonomy</span>
            <span
              className={`text-caption font-black tracking-wide ${STATUS_STYLES[taxonomy.status] ?? "text-ink-muted"}`}
            >
              {STATUS_LABELS[taxonomy.status] ?? taxonomy.status}
            </span>
          </div>
          {warned ? (
            <p className="flex items-start gap-2 rounded-control border border-state-warn/30 bg-state-warn/10 px-3 py-2 text-caption text-state-warn-ink">
              <span>
                <span className="font-semibold">
                  No work types are configured, so eligibility screening cannot decide.
                </span>{" "}
                Every tender will screen INDETERMINATE. This is not a problem with your
                tenders or your past projects — it clears automatically the next time a past
                project is added, or an administrator can load the taxonomy from the API.
              </span>
            </p>
          ) : taxonomy.detail ? (
            <p className="text-caption text-ink-muted">{taxonomy.detail}</p>
          ) : null}
          <ul className="space-y-1 pt-1">
            {health.data?.components
              .filter((component) => component.name !== "work_type_taxonomy")
              .map((component) => (
                <li
                  key={component.name}
                  className="flex flex-wrap items-baseline justify-between gap-2 text-mini"
                >
                  <span className="text-ink-muted">{component.name.replace(/_/g, " ")}</span>
                  <span className={STATUS_STYLES[component.status] ?? "text-ink-muted"}>
                    {STATUS_LABELS[component.status] ?? component.status}
                  </span>
                </li>
              ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}