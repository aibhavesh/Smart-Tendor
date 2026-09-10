import type { Metadata } from "next";
import { BRAND_NAME } from "@/components/brand/Wordmark";

/*
 * The token reference (plan §6.5): swatches, type specimen and state mapping, so later
 * screens can be checked without reading landing-page source.
 *
 * It renders the real tokens rather than describing them, so it cannot drift from the
 * theme — if a token changes, this page changes with it. It is also subject to the two
 * theme lint rules, so it has to be built from tokens like any other screen.
 */

export const metadata: Metadata = {
  title: `Design tokens — ${BRAND_NAME}`,
  description: "Colour, type, elevation and motion tokens for the platform theme.",
  robots: { index: false, follow: false },
};

type Swatch = {
  token: string;
  className: string;
  role: string;
  note?: string;
};

const SURFACE: Swatch[] = [
  { token: "--color-canvas", className: "bg-canvas", role: "Page background" },
  { token: "--color-ink", className: "bg-ink", role: "Body copy, panel headings" },
  { token: "--color-ink-strong", className: "bg-ink-strong", role: "Display headings" },
  {
    token: "--color-ink-muted",
    className: "bg-ink-muted",
    role: "Captions",
    note: "4.74:1 on glass (AA) — only 3.73:1 on bare canvas. Glass surfaces only.",
  },
];

const BRAND: Swatch[] = [
  { token: "--color-brand", className: "bg-brand", role: "Primary action, links, focus" },
  { token: "--color-brand-hover", className: "bg-brand-hover", role: "Primary hover" },
  { token: "--color-brand-deep", className: "bg-brand-deep", role: "Gradient terminus" },
  {
    token: "--color-sky-soft",
    className: "bg-sky-soft",
    role: "Ambient aura, orbit rings",
    note: "Decorative only — never a text colour.",
  },
  { token: "--color-sky-vivid", className: "bg-sky-vivid", role: "Ambient aura, orbit rings" },
];

const STATE: Swatch[] = [
  {
    token: "--color-state-go",
    className: "bg-state-go",
    role: "GO / pass / success",
    note: "White on this is 2.52:1 and FAILS AA — pair with --color-ink (6.98:1).",
  },
  { token: "--color-state-go-deep", className: "bg-state-go-deep", role: "GO gradient terminus" },
  {
    token: "--color-state-go-ink",
    className: "bg-state-go-ink",
    role: "GO as text, or fill under white text",
    note: "6.05:1 on canvas; white on it 7.69:1.",
  },
  {
    token: "--color-state-danger",
    className: "bg-state-danger",
    role: "NO_BID / fail / HIGH risk fill",
    note: "White on it 4.90:1 (AA). Only 3.86:1 as text on canvas — use the -ink variant there.",
  },
  {
    token: "--color-state-danger-ink",
    className: "bg-state-danger-ink",
    role: "Danger as text or icon",
    note: "5.09:1 on canvas; white on it 6.47:1.",
  },
  { token: "--color-accent-violet", className: "bg-accent-violet", role: "Tertiary data accent" },
  {
    token: "--color-accent-violet-deep",
    className: "bg-accent-violet-deep",
    role: "Violet gradient terminus",
  },
];

const TYPE = [
  { cls: "text-display-lg leading-display tracking-display font-outfit font-black", label: "display-lg · 60px · Outfit Black" },
  { cls: "text-display-md leading-display tracking-display font-outfit font-black", label: "display-md · 44px" },
  { cls: "text-display-sm leading-display tracking-tight font-outfit font-black", label: "display-sm · 36px" },
  { cls: "text-wordmark font-fustat font-extrabold tracking-tight", label: "wordmark · 22px · Fustat ExtraBold" },
  { cls: "text-lead tracking-body leading-relaxed", label: "lead · 18px · body paragraph" },
  { cls: "text-ui-lg font-medium", label: "ui-lg · 15px" },
  { cls: "text-ui font-semibold", label: "ui · 14px · nav, buttons" },
  { cls: "text-label font-black tracking-tight", label: "label · 13px · badge primary" },
  { cls: "text-caption", label: "caption · 12px" },
  { cls: "text-mini font-medium", label: "mini · 11px" },
  { cls: "text-micro font-semibold", label: "micro · 10px · badge secondary" },
  { cls: "text-nano font-semibold tracking-wide", label: "nano · 9px · tile labels" },
];

const RADII = [
  { cls: "rounded-control", label: "control · 12px" },
  { cls: "rounded-tile", label: "tile · 14px" },
  { cls: "rounded-surface", label: "surface · 16px" },
  { cls: "rounded-badge", label: "badge · 20px" },
  { cls: "rounded-panel", label: "panel · 24px" },
];

const ELEVATION = [
  { cls: "shadow-glass", label: "glass — the shared inset highlight" },
  { cls: "shadow-cta", label: "cta — inset highlight + brand glow" },
  { cls: "shadow-panel", label: "panel — hero centrepiece" },
  { cls: "shadow-badge-brand", label: "badge-brand" },
  { cls: "shadow-badge-go", label: "badge-go" },
  { cls: "shadow-badge-violet", label: "badge-violet" },
];

const SEMANTIC = [
  ["GO", "--color-state-go fill + --color-ink text", "Recommendation verdict"],
  ["REVIEW", "--color-brand", "Recommendation verdict"],
  ["NO_BID", "--color-state-danger fill + white text", "Recommendation verdict"],
  ["Risk NONE / LOW", "--color-state-go-ink", "Risk severity"],
  ["Risk MEDIUM", "--color-brand", "Risk severity"],
  ["Risk HIGH", "--color-state-danger-ink", "Risk severity"],
  ["UNKNOWN", "--color-ink-muted + explicit label", "Extraction — never an empty cell"],
  ["Confidence", "--color-brand ramp", "0.0–1.0, shown wherever an extracted value is"],
];

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

function SwatchGrid({ items }: { items: Swatch[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {items.map((s) => (
        <div
          key={s.token}
          className="flex gap-4 items-start rounded-tile border border-ink-strong/10 p-4"
        >
          <div
            className={`${s.className} w-14 h-14 shrink-0 rounded-control border border-ink-strong/10`}
          />
          <div className="min-w-0">
            <code className="block text-mini font-semibold text-ink">{s.token}</code>
            <p className="text-caption text-ink-strong/60 mt-1">{s.role}</p>
            {s.note ? <p className="text-mini text-ink-strong/60 mt-1.5 italic">{s.note}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function TokensPage() {
  return (
    <main className="w-full max-w-[1000px] mx-auto px-6 sm:px-12 py-16">
      <h1 className="font-outfit font-black text-display-md leading-display tracking-display text-ink-strong">
        Design tokens
      </h1>
      <p className="text-lead tracking-body leading-relaxed text-ink-strong/60 mt-4 max-w-[620px]">
        Extracted from the realised landing page. Every value here is defined once in{" "}
        <code className="text-ui">src/app/globals.css</code> — the only file permitted to
        contain a literal colour. Two lint rules fail CI on any literal introduced elsewhere.
      </p>

      <Section title="Surface and ink">
        <SwatchGrid items={SURFACE} />
      </Section>

      <Section title="Brand and ambient">
        <SwatchGrid items={BRAND} />
      </Section>

      <Section title="Semantic state">
        <SwatchGrid items={STATE} />
      </Section>

      <Section title="State mapping">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-ink-strong/10">
                <th className="py-2 pr-4 text-nano font-semibold tracking-wide text-ink-muted">
                  STATE
                </th>
                <th className="py-2 pr-4 text-nano font-semibold tracking-wide text-ink-muted">
                  TOKEN
                </th>
                <th className="py-2 text-nano font-semibold tracking-wide text-ink-muted">WHERE</th>
              </tr>
            </thead>
            <tbody>
              {SEMANTIC.map(([state, token, where]) => (
                <tr key={state} className="border-b border-ink-strong/5">
                  <td className="py-2.5 pr-4 text-caption font-semibold text-ink whitespace-nowrap">
                    {state}
                  </td>
                  <td className="py-2.5 pr-4 text-caption text-ink-strong/60">
                    <code>{token}</code>
                  </td>
                  <td className="py-2.5 text-caption text-ink-strong/60">{where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-caption text-ink-strong/60 mt-4">
          Never colour alone: every verdict and risk state pairs its colour with a label or
          icon.
        </p>
      </Section>

      <Section title="Type specimen">
        <div className="flex flex-col gap-5">
          {TYPE.map((t) => (
            <div key={t.label} className="border-b border-ink-strong/5 pb-4">
              <p className="text-nano font-semibold tracking-wide text-ink-muted">{t.label}</p>
              <p className={`${t.cls} text-ink-strong mt-1`}>Every bid decision, defensible.</p>
            </div>
          ))}
        </div>
        <p className="text-caption text-ink-strong/60 mt-4">
          The <code>--text-*</code> tokens set font-size only, matching the arbitrary values
          they replaced. A size swapped off a Tailwind built-in scale must bring its
          line-height with it.
        </p>
      </Section>

      <Section title="Radii">
        <div className="flex flex-wrap gap-4">
          {RADII.map((r) => (
            <div key={r.label} className="text-center">
              <div className={`${r.cls} w-24 h-24 bg-brand/10 border border-brand/30`} />
              <p className="text-mini text-ink-strong/60 mt-2">{r.label}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Elevation">
        <div className="flex flex-wrap gap-6">
          {ELEVATION.map((e) => (
            <div key={e.label} className="text-center">
              <div
                className={`${e.cls} w-40 h-24 rounded-badge bg-gradient-to-br from-surface/75 to-surface/45 border border-surface/70`}
              />
              <p className="text-mini text-ink-strong/60 mt-2 max-w-40">{e.label}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Motion">
        <ul className="flex flex-col gap-2 text-caption text-ink-strong/60">
          <li>
            <code className="text-ink">EASE_ENTRANCE</code> — cubic-bezier(0.16, 1, 0.3, 1);
            every entrance
          </li>
          <li>
            <code className="text-ink">EASE_FLOAT</code> — easeInOut; ambient breathing loops
          </li>
          <li>
            <code className="text-ink">DURATION</code> — quick 0.2s · drawer 0.3s · entrance
            0.6s · reveal 0.9s
          </li>
          <li>
            <code className="text-ink">SPRING_BADGE</code> — spring, damping 20, stiffness 100
          </li>
          <li>
            Defined in <code className="text-ink">src/lib/motion.ts</code>, mirrored as{" "}
            <code className="text-ink">--ease-*</code> / <code className="text-ink">--duration-*</code>{" "}
            for CSS. Every one is suppressed under <code className="text-ink">prefers-reduced-motion</code>.
          </li>
        </ul>
      </Section>
    </main>
  );
}
