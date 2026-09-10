"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { FileText, PencilLine, Play, ScanText } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader, DataRow, Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RiskBadge, UnknownValue, VerdictBadge } from "@/components/ui/Badge";
import { ConfidenceMeter, ExtractedField } from "@/components/ui/Confidence";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError } from "@/lib/api";
import { canActAs } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/use-api";
import { fetchTenderDetail, type TenderDetail } from "@/lib/tender-detail";
import { DocumentsCard } from "@/components/tenders/DocumentsCard";
import { MatchesCard } from "@/components/tenders/MatchesCard";
import { EditTenderCard } from "@/components/tenders/EditTenderCard";
import { CorrectionsCard } from "@/components/tenders/CorrectionsCard";
import { StaleVerdictNotice } from "@/components/tenders/StaleVerdictNotice";
import { TenderStatusTag } from "@/components/tenders/TenderStatusTag";
import { TENDER_STATUS_LABEL } from "@/lib/tender-status";
import { formatDate, formatMoney, humanise } from "@/lib/format";
import { canAnalyse, type RiskLevel, type TenderReview, type Verdict } from "@/lib/types";

function Section({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col gap-6">{children}</div>;
}

/** Lifecycle-gated action. Disabled states explain themselves rather than 409-ing. */
function StageAction({
  label,
  icon: Icon,
  allowed,
  reason,
  onRun,
}: {
  label: string;
  icon: typeof Play;
  allowed: boolean;
  reason: string;
  onRun: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        variant={allowed ? "primary" : "secondary"}
        disabled={!allowed || busy}
        title={allowed ? undefined : reason}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await onRun();
          } catch (err) {
            setError(
              // Confirmed live: a wrong-stage analyse returns 422 ("Invalid request."),
              // not the 409 the lifecycle wording would suggest. Both are mapped.
              describeError(err, {
                409: "The tender is not in a state where that can run.",
                422: "The tender is not at the right stage for that yet.",
              }),
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <Icon className="w-3.5 h-3.5" aria-hidden="true" />
        {busy ? "Running…" : label}
      </Button>
      {!allowed ? <span className="text-mini text-ink-muted max-w-[28ch] text-right">{reason}</span> : null}
      {error ? (
        <span role="alert" className="text-mini font-semibold text-state-danger-ink">
          {error}
        </span>
      ) : null}
    </div>
  );
}

function MetadataCard({ detail }: { detail: TenderDetail }) {
  if (!detail.metadata) {
    return (
      <Card>
        <CardHeader title="Extracted metadata" />
        <EmptyState
          title="Nothing extracted yet"
          description="Metadata appears once the tender documents have been parsed."
          icon={ScanText}
        />
      </Card>
    );
  }

  /*
   * Extracted values arrive as plain strings, so a money field renders as "18500000"
   * next to a tender card showing "₹ 4,20,00,000". The field name is the only signal
   * available for what a value means, so it drives the formatting.
   */
  const presentValue = (key: string, value: string | null): string | null => {
    if (value === null || value === "") return value;
    if (/(value|amount|cost|fee|emd|price)/i.test(key)) return formatMoney(value) ?? value;
    if (/date/i.test(key)) return formatDate(value) ?? value;
    return value;
  };

  const entries = Object.entries(detail.metadata.fields);
  return (
    <Card>
      <CardHeader
        title="Extracted metadata"
        description={`${detail.metadata.known_field_count} of ${entries.length} fields were found in the documents.`}
      />
      <div className="flex flex-col">
        {entries.map(([key, field]) => (
          <DataRow key={key} label={humanise(key)}>
            <ExtractedField
              value={presentValue(key, field.value)}
              confidence={field.confidence}
              isKnown={field.is_known}
              source={field.source}
            />
          </DataRow>
        ))}
      </div>
    </Card>
  );
}

function DecisionCard({ detail }: { detail: TenderDetail }) {
  const d = detail.decision;
  if (!d) {
    return (
      <Card>
        <CardHeader title="Recommendation" />
        <EmptyState
          title="Not analysed yet"
          description="Run the analysis once the tender is parsed to produce a verdict."
          icon={Play}
        />
      </Card>
    );
  }

  const rec = d.recommendation;
  return (
    <Panel>
      {/*
       * The banner sits above the verdict, the win probability and the confidence
       * meter, because the confidence score is the most misleading number on the
       * screen once a correction has landed: corrections are stored at confidence
       * 1.0, so the score *rises* at exactly the moment the recorded decision
       * stops being trustworthy.
       */}
      {d.verdict_is_stale ? <StaleVerdictNotice className="mb-4" /> : null}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-nano font-semibold tracking-wide text-ink-muted">RECOMMENDATION</p>
          <div className="flex items-center gap-3 mt-2">
            <VerdictBadge verdict={rec.verdict as Verdict} />
            <span className="text-caption text-ink-muted">
              win probability {rec.win_probability.toFixed(0)}%
            </span>
            <ConfidenceMeter confidence={rec.confidence} />
          </div>
        </div>
      </div>

      {/*
       * The verdict is rule-derived. The applied rules are shown first and framed as the
       * cause, so the decision never reads as a model's opinion (plan §8).
       */}
      <div className="mt-6 rounded-tile border border-ink-strong/10 bg-surface/60 p-4">
        <p className="text-nano font-semibold tracking-wide text-ink-muted">
          RULES THAT PRODUCED THIS VERDICT
        </p>
        {rec.applied_rules.length === 0 ? (
          <p className="text-caption text-ink-muted mt-2">No rules recorded.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1.5">
            {rec.applied_rules.map((rule) => (
              <li key={rule} className="text-caption text-ink flex gap-2">
                <span aria-hidden="true" className="text-ink-muted">
                  →
                </span>
                {rule}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-5">
        <div>
          <p className="text-nano font-semibold tracking-wide text-ink-muted">FOR</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {rec.pros.map((p) => (
              <li key={p} className="text-caption text-ink">
                {p}
              </li>
            ))}
            {rec.pros.length === 0 ? <li className="text-caption text-ink-muted">None.</li> : null}
          </ul>
        </div>
        <div>
          <p className="text-nano font-semibold tracking-wide text-ink-muted">AGAINST</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {rec.cons.map((c) => (
              <li key={c} className="text-caption text-ink">
                {c}
              </li>
            ))}
            {rec.cons.length === 0 ? <li className="text-caption text-ink-muted">None.</li> : null}
          </ul>
        </div>
      </div>

      {rec.document_checklist.length > 0 ? (
        <div className="mt-5">
          <p className="text-nano font-semibold tracking-wide text-ink-muted">
            DOCUMENT CHECKLIST
          </p>
          <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {rec.document_checklist.map((doc) => (
              <li key={doc} className="text-caption text-ink">
                {doc}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Panel>
  );
}

function RiskAndQualification({ detail }: { detail: TenderDetail }) {
  const d = detail.decision;
  if (!d) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader title="Risk" description="Six categories, each scored with its evidence." />
        <div className="flex items-center gap-3 mb-4">
          <RiskBadge level={d.risk.overall_severity as RiskLevel} />
          <span className="text-caption text-ink-muted">
            overall {d.risk.overall_score.toFixed(1)} / 10
            {d.risk.overall_category ? ` · ${humanise(d.risk.overall_category)}` : ""}
          </span>
        </div>
        <div className="flex flex-col gap-3">
          {d.risk.categories.map((c) => (
            <div key={c.category} className="rounded-tile border border-ink-strong/10 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-caption font-semibold text-ink">{humanise(c.category)}</span>
                <RiskBadge level={c.severity as RiskLevel} />
              </div>
              {c.evidence.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1">
                  {c.evidence.map((e) => (
                    <li key={e} className="text-mini text-ink-muted">
                      {e}
                    </li>
                  ))}
                </ul>
              ) : null}
              {c.mitigations.length > 0 ? (
                <p className="text-mini text-ink-muted mt-2">
                  <span className="font-semibold text-ink">Mitigation: </span>
                  {c.mitigations.join("; ")}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Qualification"
          description="Checked against your registry of past projects."
        />
        <p className="text-caption mb-4">
          {d.qualification.qualified ? (
            <span className="font-semibold text-state-go-ink">Qualified</span>
          ) : (
            <span className="font-semibold text-state-danger-ink">Not qualified</span>
          )}
        </p>
        <div className="flex flex-col gap-3">
          {d.qualification.rules.map((r) => (
            <div key={r.name} className="rounded-tile border border-ink-strong/10 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-caption font-semibold text-ink">{humanise(r.name)}</span>
                <span
                  className={`text-mini font-black tracking-wide ${
                    r.passed ? "text-state-go-ink" : "text-state-danger-ink"
                  }`}
                >
                  {r.passed ? "PASS" : "FAIL"}
                </span>
              </div>
              <p className="text-mini text-ink-muted mt-1.5">{r.detail}</p>
              {r.required || r.actual ? (
                <p className="text-mini text-ink-muted mt-1">
                  required {formatMoney(r.required) ?? "—"} · actual {formatMoney(r.actual) ?? "—"}
                </p>
              ) : null}
              {r.qualifying_project_name ? (
                <p className="text-mini text-ink mt-1">
                  Satisfied by <span className="font-semibold">{r.qualifying_project_name}</span>
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/*
 * One row of review history.
 *
 * Branches on `kind`, never on `verdict`. The previous version tested
 * `verdict === "APPROVED"` and fell through to the danger colour otherwise —
 * which, now that a correction carries a null verdict, would have rendered
 * every correction in the REJECTED red with a blank label. A correction is not
 * a decision and must never read as one.
 */
function ReviewHistoryRow({ review }: { review: TenderReview }) {
  const changed = Object.keys(review.after_snapshot);
  const isCorrection = review.kind === "CORRECTION";

  return (
    <div className="rounded-tile border border-ink-strong/10 p-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          {isCorrection ? (
            <span className="inline-flex items-center gap-1.5 text-mini font-black tracking-wide text-ink-muted">
              <PencilLine className="w-3.5 h-3.5" aria-hidden="true" />
              CORRECTION
            </span>
          ) : (
            <span
              className={`text-mini font-black tracking-wide ${
                review.verdict === "APPROVED" ? "text-state-go-ink" : "text-state-danger-ink"
              }`}
            >
              {review.verdict}
            </span>
          )}
          {review.is_stale ? (
            <span className="text-mini font-semibold text-brand-deep">
              · superseded by a later correction
            </span>
          ) : null}
        </div>
        <span className="text-mini text-ink-muted">
          {new Date(review.created_at).toLocaleString()}
        </span>
      </div>

      {changed.length > 0 ? (
        <p className="text-mini text-ink-muted mt-2">
          Changed: {changed.map(humanise).join(", ")}
        </p>
      ) : null}
      {review.comments ? <p className="text-caption text-ink mt-2">{review.comments}</p> : null}
    </div>
  );
}

function AnalystReportCard({ detail }: { detail: TenderDetail }) {
  const r = detail.report;
  if (!r) return null;

  return (
    <Card>
      <CardHeader
        title="Analyst commentary"
        description={`Generated by ${r.generated_by}. This is written commentary on the decision above — it does not produce it.`}
      />
      {/* Prose is regenerated per request, so it is current — the verdict may not be. */}
      {r.verdict_is_stale ? <StaleVerdictNotice className="mb-4" /> : null}
      <div className="flex flex-col gap-4">
        {Object.entries(r.sections).map(([heading, body]) => (
          <div key={heading}>
            <p className="text-nano font-semibold tracking-wide text-ink-muted">
              {humanise(heading).toUpperCase()}
            </p>
            <p className="text-caption leading-relaxed text-ink mt-1.5 whitespace-pre-line">
              {body}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function TenderDetailBody() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const { user } = useAuth();
  const canWrite = canActAs(user?.role, "EMPLOYEE");

  const detail = useResource<TenderDetail>(
    (signal) => fetchTenderDetail(id, signal),
    [id],
    { context: { 404: "That tender does not exist, or has been removed." } },
  );

  if (detail.error) return <ErrorState detail={detail.error} onRetry={detail.reload} />;
  if (detail.loading || !detail.data) return <SkeletonRows rows={9} />;

  const d = detail.data;
  const t = d.tender;
  const analysable = canAnalyse(t.status);
  const docs = d.documents ?? [];
  // Extraction needs a document that has actually landed, not merely been queued.
  const hasDownloaded = docs.some((doc) => doc.status === "DOWNLOADED");

  return (
    <Section>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <p className="text-caption text-ink-muted">{t.tender_number}</p>
          <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong mt-1">
            {t.title}
          </h1>
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            <TenderStatusTag status={t.status} />
            {d.decision ? (
              <VerdictBadge verdict={d.decision.recommendation.verdict as Verdict} />
            ) : null}
          </div>
        </div>

        {canWrite ? (
          <div className="flex items-start gap-3 flex-wrap">
            <StageAction
              label="Extract"
              icon={ScanText}
              allowed={hasDownloaded}
              reason={
                docs.length === 0
                  ? "Add a document first — extraction reads a downloaded file."
                  : "No document has finished downloading yet."
              }
              onRun={async () => {
                await api.post(`/tenders/${id}/extract`);
                detail.reload();
              }}
            />
            <StageAction
              label="Run analysis"
              icon={Play}
              allowed={analysable}
              reason={
                t.status === "ANALYZED" || t.status === "REVIEWED"
                  ? "Already analysed."
                  : `Analysis runs on the PARSED → ANALYZED step. This tender is ${TENDER_STATUS_LABEL[t.status]} (${t.status}).`
              }
              onRun={async () => {
                await api.post(`/tenders/${id}/analyze`);
                detail.reload();
              }}
            />
          </div>
        ) : null}
      </div>

      {canWrite ? <EditTenderCard tender={t} onSaved={detail.reload} /> : null}

      <Card>
        <CardHeader title="Tender" />
        <DataRow label="Department">{t.department ?? <UnknownValue label="NOT SET" />}</DataRow>
        <DataRow label="Estimated value">
          {formatMoney(t.estimated_value) ?? <UnknownValue label="NOT SET" />}
        </DataRow>
        <DataRow label="Closing date">
          {formatDate(t.closing_date) ?? <UnknownValue label="NOT SET" />}
        </DataRow>
        <DataRow label="Source">
          {t.source_url ? (
            <a
              href={t.source_url}
              className="text-brand-ink hover:text-brand-deep break-all"
              rel="noreferrer noopener"
              target="_blank"
            >
              {t.source_url}
            </a>
          ) : (
            <UnknownValue label="NOT SET" />
          )}
        </DataRow>
        {t.description ? <DataRow label="Description">{t.description}</DataRow> : null}
      </Card>

      <DecisionCard detail={d} />
      <RiskAndQualification detail={d} />
      <MatchesCard matches={d.matches} />
      <MetadataCard detail={d} />
      <CorrectionsCard tenderId={id} onSaved={detail.reload} />

      {d.boqAnalytics ? (
        <Card>
          <CardHeader
            title="Bill of quantities"
            description={`${d.boqAnalytics.total_items} items · ${d.boqAnalytics.items_with_amount} priced · total ${formatMoney(d.boqAnalytics.total_value) ?? "—"}`}
          />
          {d.boq && d.boq.length > 0 ? (
            <Table>
              <THead>
                <TH>Item</TH>
                <TH>Description</TH>
                <TH>Unit</TH>
                <TH>Quantity</TH>
                <TH>Amount</TH>
                <TH className="text-right">Confidence</TH>
              </THead>
              <TBody>
                {d.boq.slice(0, 25).map((item) => (
                  <TR key={item.id}>
                    <TD className="whitespace-nowrap">{item.item_number ?? "—"}</TD>
                    <TD className="max-w-[38ch] truncate">{item.description}</TD>
                    <TD>{item.unit ?? "—"}</TD>
                    <TD>{item.quantity ?? "—"}</TD>
                    <TD className="whitespace-nowrap">{formatMoney(item.amount) ?? "—"}</TD>
                    <TD className="text-right">
                      <ConfidenceMeter confidence={item.confidence} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState title="No line items" icon={FileText} />
          )}
          {d.boq && d.boq.length > 25 ? (
            <p className="text-caption text-ink-muted mt-3">
              Showing the first 25 of {d.boq.length} items.
            </p>
          ) : null}
        </Card>
      ) : null}

      <AnalystReportCard detail={d} />

      <DocumentsCard
        tenderId={id}
        documents={d.documents}
        canWrite={canWrite}
        onChanged={detail.reload}
      />

      {d.reviews && d.reviews.length > 0 ? (
        <Card>
          <CardHeader
            title="Review history"
            description="Corrections and decisions, newest first. A correction changes the data; only a decision approves or rejects the bid."
          />
          <div className="flex flex-col gap-3">
            {d.reviews.map((r) => (
              <ReviewHistoryRow key={r.id} review={r} />
            ))}
          </div>
        </Card>
      ) : null}
    </Section>
  );
}

export default function TenderDetailPage() {
  return (
    <RequireAuth>
      <TenderDetailBody />
    </RequireAuth>
  );
}
