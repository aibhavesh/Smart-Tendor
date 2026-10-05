/**
 * The four-level role hierarchy.
 *
 * Levels mirror `backend/src/tender_intel/domain/enums/roles.py` exactly. ANALYST and
 * VIEWER were collapsed into a single EMPLOYEE role at level 20, which absorbs the
 * former analyst capability set — level 10 and the gaps between tiers are left free
 * for future insertion, so do not renumber.
 */

export const ROLES = ["EMPLOYEE", "MANAGER", "ADMIN", "SUPER_ADMIN"] as const;

export type Role = (typeof ROLES)[number];

export const ROLE_LEVEL: Record<Role, number> = {
  EMPLOYEE: 20,
  MANAGER: 30,
  ADMIN: 40,
  SUPER_ADMIN: 50,
};

export const ROLE_LABEL: Record<Role, string> = {
  EMPLOYEE: "Employee",
  MANAGER: "Manager",
  ADMIN: "Admin",
  SUPER_ADMIN: "Super admin",
};

/** What each role may actually do — shown alongside the code, never instead of it. */
export const ROLE_DESCRIPTION: Record<Role, string> = {
  EMPLOYEE: "Adds tenders, uploads documents, and screens tenders for eligibility",
  MANAGER: "Everything an employee does, plus records certified turnover",
  ADMIN: "Manages users, pre-provisioned roles, work types and the audit trail",
  SUPER_ADMIN: "Full platform control, including deleting users",
};

/** True when `role` is at least as privileged as `required` — mirrors `can_act_as`. */
export function canActAs(role: Role | null | undefined, required: Role): boolean {
  if (!role) return false;
  return ROLE_LEVEL[role] >= ROLE_LEVEL[required];
}
