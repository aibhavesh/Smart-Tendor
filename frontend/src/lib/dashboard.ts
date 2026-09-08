import { api, query } from "./api";
import { canActAs, type Role } from "./roles";
import { TENDER_STATUSES, type OperationalStats, type Page, type PlatformStats, type Tender, type TenderStatus } from "./types";

/*
 * Dashboard data loading.
 *
 * `GET /stats` (added for this screen) returns tender counts, past-project total and the
 * pending-review depth in one call, for any authenticated user. Admins additionally get
 * `GET /admin/stats` for the user and account figures the operational surface
 * deliberately omits.
 *
 * This replaced a workaround that issued one `GET /tenders?status=…&limit=1` per
 * lifecycle state and read `total` off each envelope — six requests to render one row of
 * counters. That path is gone; there is no fallback to it, because a partial count is
 * worse than an honest failure.
 *
 * Pure async functions, no React state: fetching is called from inside an effect, and
 * React's set-state-in-effect rule traces setState through anything an effect invokes.
 */

export interface DashboardData {
  stats: OperationalStats;
  recent: Tender[];
  /** ADMIN+ only. */
  platform: PlatformStats | null;
  /** Non-fatal problems — shown as a caveat rather than replacing the whole board. */
  degraded: string[];
}

/** Statuses worth charting. ARCHIVED is terminal, not operational. */
export const DASHBOARD_STATUSES: TenderStatus[] = TENDER_STATUSES.filter((s) => s !== "ARCHIVED");

export async function fetchDashboard(role: Role): Promise<DashboardData> {
  const degraded: string[] = [];

  const [stats, recentPage] = await Promise.all([
    api.get<OperationalStats>("/stats"),
    api.get<Page<Tender>>(`/tenders${query({ limit: 8, offset: 0 })}`),
  ]);

  let platform: PlatformStats | null = null;
  if (canActAs(role, "ADMIN")) {
    try {
      platform = await api.get<PlatformStats>("/admin/stats");
    } catch {
      // The operational figures above still render; only the admin extras are missing.
      degraded.push("platform statistics");
    }
  }

  return { stats, recent: recentPage.items, platform, degraded };
}
