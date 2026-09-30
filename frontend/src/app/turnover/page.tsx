"use client";

import { CompanyTurnoverPanel } from "@/components/admin/CompanyTurnover";
import { RequireAuth } from "@/components/layout/RequireAuth";

export default function TurnoverPage() {
  return (
    <RequireAuth minRole="MANAGER">
      <div className="space-y-6">
        <div>
          <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
            Certified turnover
          </h1>
          <p className="mt-1.5 text-ui text-ink-strong/60">
            Record the certified annual turnover used for financial eligibility.
          </p>
        </div>
        <CompanyTurnoverPanel />
      </div>
    </RequireAuth>
  );
}
