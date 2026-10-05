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
import { fetchDashboard, type DashboardData } from "@/lib/dashboard";
import { TenderStatusTag } from "@/components/tenders/TenderStatusTag";

/** A count that failed to load renders as UNKNOWN, never as a misleading zero. */
function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | null | undefined;
  /** Optional clarifier. Rendered under the value so the number stays dominant. */
  hint?: string;
}) {
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
      {hint ? <p className="mt-1 text-nano text-ink-muted">{hint}</p> : null}
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

  const isAdmin = canActAs(role, "ADMIN");

  const chartData = [
    { name: "No doc", value: data.stats.tenders_by_status.REGISTERED ?? 0 },
    { name: "Doc in", value: data.stats.tenders_by_status.DOWNLOADED ?? 0 },
    { name: "Extracted", value: data.stats.tenders_by_status.PARSED ?? 0 },
    { name: "Eligible", value: data.stats.eligibility_by_status.ELIGIBLE ?? 0 },
    { name: "Not eligible", value: data.stats.eligibility_by_status.NOT_ELIGIBLE ?? 0 },
    { name: "Needs review", value: data.stats.eligibility_by_status.INDETERMINATE ?? 0 },
  ];

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
        <StatTile label="Eligible" value={data.stats.eligibility_by_status.ELIGIBLE ?? 0} />
        <StatTile label="Not eligible" value={data.stats.eligibility_by_status.NOT_ELIGIBLE ?? 0} />
        <StatTile
          label="Awaiting screening"
          value={data.stats.screening_pending}
          hint="Recorded but not yet screened"
        />
      </div>

      {isAdmin && data.platform ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <StatTile label="Active users" value={data.platform.users_active} />
          <StatTile label="Total users" value={data.platform.users_total} />
          <StatTile label="Documents" value={data.platform.documents_total} />
        </div>
      ) : null}

      <Card>
        <CardHeader
          title="Tender workflow and eligibility"
          description="Workflow stages and screening outcomes. A tender can appear in both groups."
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
                labelFormatter={(label) => String(label)}
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
