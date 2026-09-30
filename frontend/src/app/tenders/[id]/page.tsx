"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader, DataRow } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";
import { api, describeError } from "@/lib/api";
import { fetchTenderDetail, type TenderEligibility } from "@/lib/tender-detail";
import { useResource } from "@/lib/use-api";

function Detail() {
  const { id } = useParams<{ id: string }>();
  const detail = useResource((signal) => fetchTenderDetail(id, signal), [id]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (detail.loading) return <p className="text-ink-muted">Loading tender…</p>;
  if (detail.error || !detail.data) return <ErrorState detail={describeError(detail.error)} />;
  const { tender, documents, metadata, boq, eligibility } = detail.data;
  async function run(path: string) {
    setBusy(true); setError(null);
    try {
      await api.post<TenderEligibility | undefined>(path);
      detail.reload();
    } catch (cause) { setError(describeError(cause)); }
    finally { setBusy(false); }
  }
  return <div className="space-y-6">
    <Card><CardHeader title={tender.title} description={`${tender.tender_number} · ${tender.status}`} actions={<><Button size="sm" variant="secondary" onClick={() => run(`/tenders/${id}/extract`)} disabled={busy}>Extract</Button><Button size="sm" onClick={() => run(`/api/v1/tenders/${id}/eligibility`)} disabled={busy || tender.status === "REGISTERED" || tender.status === "DOWNLOADED"}>Check eligibility</Button></>} />
      <DataRow label="Closing date">{tender.closing_date ?? "Unknown"}</DataRow><DataRow label="Estimated value">{tender.estimated_value ?? "Unknown"}</DataRow>
    </Card>
    {error ? <ErrorState detail={error} /> : null}
    <Card><CardHeader title="Parsing and extraction" description="These fields are used by eligibility screening." />
      {metadata ? Object.entries(metadata.fields).slice(0, 12).map(([name, field]) => <DataRow key={name} label={name.replaceAll("_", " ")}>{field.is_known ? String(field.value) : "Unknown"}</DataRow>) : <p className="text-ink-muted">Upload a document, then run extraction.</p>}
      <p className="mt-4 text-caption text-ink-muted">{documents?.length ?? 0} document(s) · {boq?.length ?? 0} BOQ item(s)</p>
    </Card>
    {eligibility ? <Card><CardHeader title={`Eligibility: ${eligibility.status.replaceAll("_", " ")}`} description={eligibility.is_stale ? "The project or turnover evidence changed after this screening. Re-run eligibility to refresh it." : "Automatically screened after document extraction."} />
      <DataRow label="Financial eligibility">{eligibility.financial_pass === true ? "Pass" : eligibility.financial_pass === false ? "Fail" : "Needs review"}</DataRow>
      <DataRow label="Technical eligibility">{eligibility.technical_pass === true ? "Pass" : eligibility.technical_pass === false ? "Fail" : "Needs review"}</DataRow>
      <DataRow label="Similar-work rule">{eligibility.rule_satisfied ?? "Needs review"}</DataRow>
      {eligibility.reasons.map((reason) => <p key={reason} className="mt-2 text-caption text-ink-muted">{reason}</p>)}
    </Card> : tender.status === "DOWNLOADED" || tender.status === "REGISTERED" ? <p className="text-ink-muted">The document is being prepared for automatic eligibility screening.</p> : <p className="text-ink-muted">Eligibility screening is in progress.</p>}
  </div>;
}

export default function TenderDetailPage() { return <RequireAuth><Detail /></RequireAuth>; }
