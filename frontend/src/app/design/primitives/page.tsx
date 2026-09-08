"use client";

import { useState } from "react";
import { FileSearch } from "lucide-react";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card, CardHeader, DataRow, Panel } from "@/components/ui/Card";
import { RiskBadge, UnknownValue, VerdictBadge } from "@/components/ui/Badge";
import { ConfidenceMeter, ExtractedField } from "@/components/ui/Confidence";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { DateField, FileField, SelectField, TextField } from "@/components/ui/Field";
import { ROLES, ROLE_LABEL, canActAs, type Role } from "@/lib/roles";
import { CHART_THEME } from "@/lib/chart-theme";
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

/*
 * Primitive gallery (plan §7). Not part of the product surface — it exists so the
 * primitives can be seen and checked without standing up an application screen, and so
 * Phase D can confirm a screen is composing rather than restyling.
 */

const NAV_MIN_ROLE = [
  ["Dashboard", "EMPLOYEE"],
  ["Tenders", "EMPLOYEE"],
  ["Reviews", "MANAGER"],
  ["Past projects", "EMPLOYEE"],
  ["Administration", "ADMIN"],
  ["Audit logs", "ADMIN"],
] as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-12">
      <h2 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
        {title}
      </h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

export default function PrimitivesPage() {
  const [offset, setOffset] = useState(0);
  const [role, setRole] = useState<Role>("EMPLOYEE");
  const limit = 10;
  const total = 34;

  return (
    <main className="w-full max-w-[1000px] mx-auto px-6 sm:px-12 py-16">
      <h1 className="font-outfit font-black text-display-md leading-display tracking-display text-ink-strong">
        Primitives
      </h1>
      <p className="text-lead tracking-body leading-relaxed text-ink-strong/60 mt-4 max-w-[620px]">
        Screens compose these. Screens do not style. If a screen needs a treatment no
        primitive provides, extend the primitive rather than styling locally.
      </p>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-3 mt-4">
          <Button size="sm" variant="primary">
            Small primary
          </Button>
          <Button size="sm" variant="secondary">
            Small secondary
          </Button>
          <ButtonLink href="/design/tokens" size="sm" variant="ghost">
            ButtonLink → tokens
          </ButtonLink>
        </div>
        <p className="text-caption text-ink-muted mt-4">
          Primary fills with <code>--color-brand-hover</code> (white 4.59:1), not{" "}
          <code>--color-brand</code> (3.66:1, below AA at button text sizes).
        </p>
      </Section>

      <Section title="Verdict and risk">
        <div className="flex flex-wrap items-center gap-3">
          <VerdictBadge verdict="GO" />
          <VerdictBadge verdict="REVIEW" />
          <VerdictBadge verdict="NO_BID" />
        </div>
        <div className="flex flex-wrap items-center gap-3 mt-4">
          <RiskBadge level="NONE" />
          <RiskBadge level="LOW" />
          <RiskBadge level="MEDIUM" />
          <RiskBadge level="HIGH" />
        </div>
        <p className="text-caption text-ink-muted mt-4">
          Every state carries an icon as well as a colour, so it survives greyscale and
          colour-blind readers. The verdict is rule-derived — never label it a prediction.
        </p>
      </Section>

      <Section title="Extraction: confidence and UNKNOWN">
        <Card className="max-w-[560px]">
          <CardHeader title="Tender metadata" description="Every extracted field shows its confidence." />
          <DataRow label="Tender number">
            <ExtractedField value="NIT/2026/0412" confidence={0.96} isKnown source="page 1" />
          </DataRow>
          <DataRow label="Estimated value">
            <ExtractedField value="₹ 4,20,00,000" confidence={0.62} isKnown source="BOQ" />
          </DataRow>
          <DataRow label="EMD amount">
            <ExtractedField value={null} confidence={0.18} isKnown={false} />
          </DataRow>
        </Card>
        <div className="flex flex-wrap items-center gap-5 mt-4">
          <ConfidenceMeter confidence={0.96} />
          <ConfidenceMeter confidence={0.62} />
          <ConfidenceMeter confidence={0.18} />
          <UnknownValue />
        </div>
        <p className="text-caption text-ink-muted mt-4">
          UNKNOWN is a deliberate output, not a gap — it renders as a distinct chip, never
          an empty cell.
        </p>
      </Section>

      <Section title="Table and pagination">
        <Card>
          <Table>
            <THead>
              <TH>Tender</TH>
              <TH>Status</TH>
              <TH>Verdict</TH>
              <TH>Risk</TH>
              <TH className="text-right">Confidence</TH>
            </THead>
            <TBody>
              {[
                { n: "NIT/2026/0412", s: "ANALYZED", v: "GO", r: "LOW", c: 0.91 },
                { n: "NIT/2026/0398", s: "PARSED", v: "REVIEW", r: "MEDIUM", c: 0.64 },
                { n: "NIT/2026/0377", s: "REVIEWED", v: "NO_BID", r: "HIGH", c: 0.44 },
              ].map((row) => (
                <TR key={row.n}>
                  <TD>{row.n}</TD>
                  <TD>
                    <span className="text-caption text-ink-muted">{row.s}</span>
                  </TD>
                  <TD>
                    <VerdictBadge verdict={row.v as "GO" | "REVIEW" | "NO_BID"} />
                  </TD>
                  <TD>
                    <RiskBadge level={row.r as "LOW" | "MEDIUM" | "HIGH"} />
                  </TD>
                  <TD className="text-right">
                    <ConfidenceMeter confidence={row.c} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination
            page={{ total, limit, offset, has_more: offset + limit < total }}
            onChange={setOffset}
            label="tenders"
          />
        </Card>
      </Section>

      <Section title="Form controls">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 max-w-[720px]">
          <TextField label="Tender number" placeholder="NIT/2026/0412" required helper="Must be unique." />
          <TextField
            label="Tender number"
            defaultValue="NIT/2026/0412"
            error="A tender with this number already exists (409)."
          />
          <SelectField label="Status" helper="Filters the list.">
            <option>REGISTERED</option>
            <option>DOWNLOADED</option>
            <option>PARSED</option>
            <option>ANALYZED</option>
            <option>REVIEWED</option>
            <option>ARCHIVED</option>
          </SelectField>
          <DateField label="Closing date" helper="Local time." />
          <FileField label="Tender document" helper="PDF, up to 50 MB." />
          <FileField label="Tender document" fileName="nit-2026-0412.pdf" error="Unsupported file type." />
        </div>
      </Section>

      <Section title="Empty, loading and error">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <Card>
            <EmptyState
              title="No tenders yet"
              description="Register a tender or import a CSV to get started."
              action={
                <Button size="sm" variant="primary">
                  Register a tender
                </Button>
              }
            />
          </Card>
          <Card>
            <ErrorState
              detail="That tender number is already registered (409). Open the existing record instead."
              onRetry={() => {}}
            />
          </Card>
          <Card>
            <SkeletonRows rows={5} />
          </Card>
        </div>
      </Section>

      <Section title="Charts">
        <Card>
          <CardHeader
            title="Tenders by status"
            description="Series, gridlines, axes and tooltip all come from CHART_THEME — never per-chart props."
          />
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[
                  { name: "REGISTERED", value: 12 },
                  { name: "DOWNLOADED", value: 9 },
                  { name: "PARSED", value: 17 },
                  { name: "ANALYZED", value: 24 },
                  { name: "REVIEWED", value: 7 },
                ]}
                margin={{ top: 4, right: 8, bottom: 4, left: -16 }}
              >
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
                />
                <Tooltip
                  cursor={{ fill: CHART_THEME.grid, fillOpacity: 0.06 }}
                  contentStyle={CHART_THEME.tooltip.contentStyle}
                  labelStyle={CHART_THEME.tooltip.labelStyle}
                />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {CHART_THEME.series.map((colour, i) => (
                    <Cell key={colour} fill={CHART_THEME.series[i % CHART_THEME.series.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <p className="text-caption text-ink-muted mt-4">
          Colours are <code>var(--color-*)</code>, so charts track the theme and the token
          lint rules stay satisfied. Severity and verdict ramps are reserved for meaning.
        </p>
      </Section>

      <Section title="Role-aware navigation">
        <div className="flex flex-wrap items-center gap-2">
          {ROLES.map((r) => (
            <Button
              key={r}
              size="sm"
              variant={r === role ? "primary" : "secondary"}
              onClick={() => setRole(r)}
            >
              {ROLE_LABEL[r]}
            </Button>
          ))}
        </div>
        <Panel className="mt-5 max-w-[420px]">
          <ul className="flex flex-col gap-1">
            {NAV_MIN_ROLE.map(([label, min]) => {
              const allowed = canActAs(role, min as Role);
              return (
                <li
                  key={label}
                  className={`flex items-center justify-between gap-3 rounded-control px-3 py-2.5 text-ui ${
                    allowed ? "bg-brand/10 text-brand-ink font-semibold" : "opacity-40 text-ink-muted"
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <FileSearch className="w-4 h-4" aria-hidden="true" />
                    {label}
                  </span>
                  <span className="text-mini">{allowed ? "visible" : `needs ${min}`}</span>
                </li>
              );
            })}
          </ul>
        </Panel>
        <p className="text-caption text-ink-muted mt-4">
          Levels are 20–50 (EMPLOYEE 20 → SUPER_ADMIN 50), mirroring the backend enum — not the
          50/40/30/20/10 in the plan&apos;s §7 table. Hiding a link is presentation only; the
          server still enforces the check.
        </p>
      </Section>
    </main>
  );
}
