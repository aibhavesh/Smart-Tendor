"use client";

import { Sparkles } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { formatMoney } from "@/lib/format";
import type { MatchResult } from "@/lib/types";

/*
 * Semantic matches against the past-project registry.
 *
 * This is *evidence*, not a decision: qualification already states pass/fail and names
 * the project that satisfied a rule. What this adds is the shortlist the matcher
 * considered and why each candidate was or was not eligible — which is what someone
 * asks for when they disagree with the qualification result.
 */
export function MatchesCard({ matches }: { matches: MatchResult | null }) {
  if (!matches) return null;

  const candidates = matches.candidates ?? [];

  return (
    <Card>
      <CardHeader
        title="Matching past projects"
        description={
          matches.min_required_value
            ? `Ranked by similarity to the scope of work. Eligibility needs at least ${formatMoney(matches.min_required_value)}.`
            : "Ranked by similarity to the scope of work."
        }
      />
      {candidates.length === 0 ? (
        <EmptyState
          title="No comparable projects"
          description="Add past projects to the registry so qualification has something to match against."
          icon={Sparkles}
        />
      ) : (
        <Table>
          <THead>
            <TH>Project</TH>
            <TH>Value</TH>
            <TH>Similarity</TH>
            <TH>Eligible</TH>
            <TH>Why</TH>
          </THead>
          <TBody>
            {candidates.map((c) => (
              <TR key={c.project_id}>
                <TD className="max-w-[28ch] truncate">{c.name}</TD>
                <TD className="whitespace-nowrap">{formatMoney(c.work_value) ?? "—"}</TD>
                <TD>
                  <span className="inline-flex items-center gap-2">
                    <span className="h-1 w-10 rounded-full bg-ink-strong/10 overflow-hidden">
                      <span
                        className="block h-full rounded-full bg-brand"
                        style={{ width: `${Math.round(Math.min(1, Math.max(0, c.similarity)) * 100)}%` }}
                      />
                    </span>
                    <span className="text-mini font-semibold tabular-nums text-ink">
                      {c.similarity.toFixed(2)}
                    </span>
                  </span>
                </TD>
                <TD>
                  <span
                    className={`text-mini font-black tracking-wide ${
                      c.eligible ? "text-state-go-ink" : "text-state-danger-ink"
                    }`}
                  >
                    {c.eligible ? "YES" : "NO"}
                  </span>
                </TD>
                <TD className="text-mini text-ink-muted max-w-[34ch]">
                  {c.reasons.length > 0 ? c.reasons.join("; ") : "—"}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}
