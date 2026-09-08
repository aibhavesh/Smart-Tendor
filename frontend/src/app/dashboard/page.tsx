"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { ButtonLink } from "@/components/ui/Button";
import { UnknownValue } from "@/components/ui/Badge";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { CHART_THEME } from "@/lib/chart-theme";
import { describeError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { canActAs } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { DASHBOARD_STATUSES, fetchDashboard, type DashboardData } from "@/lib/dashboard";
import { TenderStatusTag } from "@/components/tenders/TenderStatusTag";
import {
  TENDER_STATUS_LABEL,
  TENDER_STATUS_SHORT,
} from "@/lib/tender-status";
import type { TenderStatus } from "@/lib/types";

/** A count that failed to load renders as UNKNOWN, never as a misleading zero. */
function StatTile({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="rounded-tile border border-ink-strong/10 bg-surface/60 px-4 py-3.5">
      <p className="text-nano font-semibold tracking-wide text-ink-muted">{label.toUpperCase()}</p>
      <div className="mt-1">
        {value === null || value === undefined ? (
          <UnknownValue label="UNAVAILABLE" />
        ) : (
          <p className="font-outfit font-black text-display-sm tracking-tight text-ink tabular-nums">
            {value}
          </p>
        )}
      </div>
    </div>
  );
}

function DashboardBody() {
  const { user } = useAuth();
  const role = user?.role;

  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!role) return;
    let cancelled = false;

    void (async () => {
      try {
        const next = await fetchDashboard(role);
        if (cancelled) return;
        setError(null);
        setData(next);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [role, reloadKey]);

  if (error) return <ErrorState detail={error} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!data || !role) return <SkeletonRows rows={7} />;

  const isManager = canActAs(role, "MANAGER");
  const isAdmin = canActAs(role, "ADMIN");

  // Short labels on the axis; the code rides along in the tooltip so the bar can still be
  // matched to the status filter on the tender list.
  const chartData = DASHBOARD_STATUSES.map((status) => ({
    name: TENDER_STATUS_SHORT[status],
    code: status,
    value: data.stats.tenders_by_status[status] ?? 0,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Dashboard
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">Where every tender currently stands.</p>
      </div>

      {data.degraded.length > 0 ? (
        <p
          role="status"
          className="rounded-control border border-ink-strong/15 bg-surface/60 px-3 py-2.5 text-caption text-ink-muted"
        >
          Some figures could not be loaded ({data.degraded.join(", ")}). Everything else is
          current.
        </p>
      ) : null}

      {/* Role-appropriate KPIs: the same board would be either useless to a viewer or
          missing the queue a manager opens this screen for. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile label="Tenders" value={data.stats.tenders_total} />
        <StatTile label="Awaiting analysis" value={data.stats.tenders_by_status.PARSED ?? 0} />
        <StatTile label="Analysed" value={data.stats.tenders_by_status.ANALYZED ?? 0} />
        {isManager ? (
          <StatTile label="Pending review" value={data.stats.reviews_pending} />
        ) : (
          <StatTile label="Past projects" value={data.stats.past_projects_total} />
        )}
      </div>

      {isAdmin && data.platform ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatTile label="Active users" value={data.platform.users_active} />
          <StatTile label="Total users" value={data.platform.users_total} />
          <StatTile label="Reviews" value={data.platform.reviews_total} />
          <StatTile label="Documents" value={data.platform.documents_total} />
        </div>
      ) : null}

      <Card>
        <CardHeader
          title="Tenders by status"
          description="Nothing is analysed before it is parsed — the lifecycle enforces the order."
        />
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
              <CartesianGrid
                stroke={CHART_THEME.grid}
                strokeOpacity={CHART_THEME.gridOpacity}
                vertical={false}
              />
              <XAxis
                dataKey="name"
                stroke={CHART_THEME.axis}
                tick={{ fontSize: CHART_THEME.axisFontSize, fill: CHART_THEME.axis }}
                tickLine={false}
              />
              <YAxis
                stroke={CHART_THEME.axis}
                tick={{ fontSize: CHART_THEME.axisFontSize, fill: CHART_THEME.axis }}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
              />
              <Tooltip
                cursor={{ fill: CHART_THEME.grid, fillOpacity: 0.06 }}
                contentStyle={CHART_THEME.tooltip.contentStyle}
                labelStyle={CHART_THEME.tooltip.labelStyle}
                labelFormatter={(_label, payload) => {
                  const row = payload?.[0]?.payload as { code?: TenderStatus } | undefined;
                  return row?.code
                    ? `${TENDER_STATUS_LABEL[row.code]} (${row.code})`
                    : String(_label);
                }}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={entry.name} fill={CHART_THEME.series[i % CHART_THEME.series.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Recent tenders"
          actions={
            <ButtonLink href="/tenders" variant="secondary" size="sm">
              View all
            </ButtonLink>
          }
        />
        {data.recent.length === 0 ? (
          <EmptyState
            title="No tenders yet"
            description="Register a tender to start building the pipeline."
            action={
              <ButtonLink href="/tenders" size="sm">
                Go to tenders
              </ButtonLink>
            }
          />
        ) : (
          <Table>
            <THead>
              <TH>Number</TH>
              <TH>Title</TH>
              <TH>Status</TH>
              <TH>Closing</TH>
            </THead>
            <TBody>
              {data.recent.map((t) => (
                <TR key={t.id}>
                  <TD className="whitespace-nowrap">{t.tender_number}</TD>
                  <TD className="max-w-[36ch] truncate">{t.title}</TD>
                  <TD>
                    <TenderStatusTag status={t.status} showCode={false} />
                  </TD>
                  <TD className="whitespace-nowrap text-caption text-ink-muted">
                    {formatDate(t.closing_date) ?? "—"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardBody />
    </RequireAuth>
  );
}
