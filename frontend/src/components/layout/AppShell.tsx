"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileSearch,
  FolderKanban,
  LayoutDashboard,
  ScrollText,
  Settings,
  ShieldCheck,
  Upload,
  UserPlus,
  UserRound,
} from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { Wordmark } from "@/components/brand/Wordmark";
import { ROLE_LABEL, canActAs, type Role } from "@/lib/roles";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

/*
 * The application shell — role-aware navigation against the four-level hierarchy.
 *
 * `minRole` is set from what the API actually permits, never from a plan table. Note
 * that /reviews is EMPLOYEE+: the pending queue is readable by anyone, because seeing
 * what awaits a decision is not the same as making one. The decision form on that
 * screen is gated separately, and its absence is explained rather than silent.
 *
 * Hiding a link is presentation only. The server still enforces the real check.
 */

type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  minRole: Role;
};

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, minRole: "EMPLOYEE" },
  { href: "/tenders", label: "Tenders", icon: FileSearch, minRole: "EMPLOYEE" },
  { href: "/tenders/upload", label: "Add a tender", icon: Upload, minRole: "EMPLOYEE" },
  { href: "/reviews", label: "Reviews", icon: ShieldCheck, minRole: "EMPLOYEE" },
  { href: "/projects", label: "Past projects", icon: FolderKanban, minRole: "EMPLOYEE" },
  { href: "/admin", label: "Administration", icon: Settings, minRole: "ADMIN" },
  { href: "/admin/role-assignments", label: "Pre-provisioned roles", icon: UserPlus, minRole: "ADMIN" },
  { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText, minRole: "ADMIN" },
];

function matches(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/*
 * Only the most specific match lights up. /tenders/upload sits under /tenders, so a
 * plain per-item test would mark both rows current and leave the reader with two
 * "you are here" answers.
 */
function activeHref(pathname: string, items: NavItem[]): string | null {
  return items.reduce<string | null>(
    (best, item) =>
      matches(pathname, item.href) && (best === null || item.href.length > best.length)
        ? item.href
        : best,
    null,
  );
}

export function AppShell({
  role,
  userName,
  children,
}: {
  role: Role;
  userName?: string;
  children: ReactNode;
}) {
  const pathname = usePathname() ?? "/";
  const visible = NAV.filter((item) => canActAs(role, item.minRole));
  const current = activeHref(pathname, visible);

  return (
    <div className="min-h-full flex flex-col">
      <header className="sticky top-0 z-40 border-b border-ink-strong/10 bg-canvas/85 backdrop-blur-glass">
        <div className="w-full max-w-[1280px] mx-auto px-6 lg:px-10 h-16 flex items-center justify-between gap-6">
          <Wordmark className="flex text-ui-lg shrink-0" iconClassName="w-5 h-5" />

          <div className="flex items-center gap-2">
            <ThemeToggle />

            <Link
              href="/profile"
              className="flex items-center gap-2.5 rounded-control px-2.5 py-1.5 hover:bg-ink-strong/5 transition-colors"
            >
              <span className="w-8 h-8 rounded-full bg-brand/10 flex items-center justify-center shrink-0">
                <UserRound className="w-4 h-4 text-brand-ink" aria-hidden="true" />
              </span>
              <span className="hidden sm:flex flex-col text-left leading-tight">
                <span className="text-caption font-semibold text-ink">{userName ?? "Account"}</span>
                <span className="text-mini text-ink-muted">{ROLE_LABEL[role]}</span>
              </span>
            </Link>
          </div>
        </div>
      </header>

      <div className="w-full max-w-[1280px] mx-auto px-6 lg:px-10 flex-1 flex gap-8 py-8">
        <nav aria-label="Sections" className="hidden lg:block w-56 shrink-0">
          <ul className="flex flex-col gap-1 sticky top-24">
            {visible.map((item) => {
              const active = item.href === current;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-3 rounded-control px-3 py-2.5 text-ui font-medium transition-colors ${
                      active
                        ? "bg-brand/10 text-brand-ink font-semibold"
                        : "text-ink-strong/70 hover:bg-ink-strong/5 hover:text-ink"
                    }`}
                  >
                    <item.icon className="w-4 h-4 shrink-0" aria-hidden={true} />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
