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
  EMPLOYEE: "Adds tenders, runs analysis, and corrects extracted fields",
  MANAGER: "Approves or rejects tenders — owns the final bid decision",
  ADMIN: "Manages users, audit logs, and system health",
  SUPER_ADMIN: "Full platform control, including deleting users",
};

/** True when `role` is at least as privileged as `required` — mirrors `can_act_as`. */
export function canActAs(role: Role | null | undefined, required: Role): boolean {
  if (!role) return false;
  return ROLE_LEVEL[role] >= ROLE_LEVEL[required];
}

/**
 * True only for these exact roles — mirrors `require_exact_roles`.
 *
 * The bid verdict is the one capability the hierarchy must not hand upward: ADMIN
 * outranks MANAGER on level but owns user administration, not bid decisions.
 */
export function isExactly(role: Role | null | undefined, ...allowed: Role[]): boolean {
  if (!role) return false;
  return allowed.includes(role);
}

/** Who may record an APPROVE / REJECT verdict. */
export function canDecideVerdict(role: Role | null | undefined): boolean {
  return isExactly(role, "MANAGER", "SUPER_ADMIN");
}
