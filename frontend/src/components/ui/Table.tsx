import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

/*
 * Data table + pagination.
 *
 * Every list endpoint in this API is paginated and returns the same envelope
 * ({ items, total, limit, offset, has_more }), so Pagination takes exactly that shape
 * rather than a page number — the backend is offset-based and inventing page numbers
 * would mean recomputing them at every call site.
 */

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  // The wrapper scrolls, not the page — a wide table must never push the body sideways.
  return (
    <div className={`w-full overflow-x-auto ${className ?? ""}`}>
      <table className="w-full text-left border-collapse">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead>
      <tr className="border-b border-ink-strong/10">{children}</tr>
    </thead>
  );
}

/** `children` is optional: action columns have no visible header, only a cell. */
export function TH({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={`py-2.5 px-3 text-nano font-semibold tracking-wide text-ink-muted whitespace-nowrap ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function TR({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-ink-strong/5 last:border-0 ${
        onClick ? "cursor-pointer hover:bg-ink-strong/5 transition-colors" : ""
      }`}
    >
      {children}
    </tr>
  );
}

export function TD({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={`py-3 px-3 text-ui text-ink align-middle ${className ?? ""}`}>{children}</td>;
}

export type PageMeta = {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export function Pagination({
  page,
  onChange,
  label = "results",
}: {
  page: PageMeta;
  onChange: (offset: number) => void;
  label?: string;
}) {
  const { total, limit, offset, has_more } = page;
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(offset + limit, total);

  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-4 pt-4 mt-1 border-t border-ink-strong/10"
    >
      <p className="text-caption text-ink-muted tabular-nums">
        {total === 0 ? `No ${label}` : `${first}–${last} of ${total} ${label}`}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          <ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
          Previous
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!has_more}
          onClick={() => onChange(offset + limit)}
        >
          Next
          <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
        </Button>
      </div>
    </nav>
  );
}
