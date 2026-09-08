import {
  BadgeCheck,
  FileSpreadsheet,
  GitBranch,
  KeyRound,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import type { ComponentType } from "react";
import { Card } from "@/components/ui/Card";

/*
 * The sections the nav links point at.
 *
 * Every claim here is grounded in something the API actually does — the six risk
 * categories, the five-level role hierarchy, the lifecycle states and the rule trail are
 * all read out of the backend enums and schemas (see frontend/docs/api-map.md). Nothing
 * on this page describes a capability the product does not have.
 */

type Item = {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  body: string;
};

const FEATURES: Item[] = [
  {
    icon: FileSpreadsheet,
    title: "Extract",
    body: "Bill of quantities and tender metadata are pulled from the documents, every field carrying a 0.00–1.00 confidence score. What could not be read is marked UNKNOWN rather than guessed.",
  },
  {
    icon: ShieldAlert,
    title: "Assess",
    body: "Six risk categories — performance guarantee, liquidated damages, OEM dependency, completion time, EMD and special clauses — each scored with the clause evidence behind it.",
  },
  {
    icon: BadgeCheck,
    title: "Qualify",
    body: "Eligibility is checked against your own registry of past projects, so a qualification result names the specific project that satisfies each requirement.",
  },
];

const PLATFORM: Item[] = [
  {
    icon: Workflow,
    title: "A lifecycle, not a black box",
    body: "Registered → downloaded → parsed → analyzed → reviewed. Nothing is analysed before it is parsed, and a reviewed tender can return for re-analysis after a correction.",
  },
  {
    icon: GitBranch,
    title: "Decisions are rule-derived",
    body: "The GO / REVIEW / NO_BID verdict comes from qualification and risk rules, and ships with the list of rules that produced it. AI commentary sits alongside that decision — it never makes it.",
  },
  {
    icon: ScrollText,
    title: "Corrections are recorded",
    body: "Human review captures the before and after of every corrected value, so the record shows what was changed, by whom, and what the system originally read.",
  },
];

const SECURITY: Item[] = [
  {
    icon: KeyRound,
    title: "Short-lived sessions",
    body: "Access tokens last 15 minutes and refresh silently for 7 days. The access token is held in memory only, so a stored token cannot be lifted from disk.",
  },
  {
    icon: ShieldCheck,
    title: "Five-level access control",
    body: "Viewer, analyst, manager, admin and super admin. Permissions are enforced on the server for every request — the interface hides what you cannot use, but the check does not live there.",
  },
  {
    icon: ScrollText,
    title: "Audited by default",
    body: "Privileged actions are written to an append-only audit log with actor, entity, before/after diff, address and timestamp, filterable by actor, action and date.",
  },
];

function Section({
  id,
  eyebrow,
  title,
  lede,
  items,
}: {
  id: string;
  eyebrow: string;
  title: string;
  lede: string;
  items: Item[];
}) {
  return (
    <section id={id} className="scroll-mt-28 py-16 lg:py-24">
      <p className="text-nano font-semibold tracking-wide text-brand-ink">{eyebrow}</p>
      <h2 className="font-outfit font-black text-display-sm lg:text-display-md leading-display tracking-tight lg:tracking-display text-ink-strong mt-3">
        {title}
      </h2>
      <p className="text-lead tracking-body leading-relaxed text-ink-strong/60 mt-4 max-w-[560px]">
        {lede}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-10">
        {items.map((item) => (
          <Card key={item.title} as="article">
            <span className="w-10 h-10 rounded-control bg-brand/10 flex items-center justify-center">
              <item.icon className="w-5 h-5 text-brand-ink" aria-hidden={true} />
            </span>
            <h3 className="font-outfit font-bold text-ui-lg tracking-tight text-ink mt-4">
              {item.title}
            </h3>
            <p className="text-caption leading-relaxed text-ink-strong/60 mt-2">{item.body}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}

export function LandingSections() {
  return (
    <>
      <Section
        id="features"
        eyebrow="FEATURES"
        title="Read the tender. Score it. Defend it."
        lede="Three passes over every tender, each producing evidence you can point at rather than a number you have to trust."
        items={FEATURES}
      />
      <Section
        id="platform"
        eyebrow="PLATFORM"
        title="Built so the reasoning survives the meeting."
        lede="The parts of the system that matter when someone asks why a bid was dropped six months later."
        items={PLATFORM}
      />
      <Section
        id="security"
        eyebrow="SECURITY"
        title="Access you can account for."
        lede="Tender documents are commercially sensitive before they are anything else."
        items={SECURITY}
      />
    </>
  );
}
