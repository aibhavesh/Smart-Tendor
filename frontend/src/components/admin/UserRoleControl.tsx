"use client";

import { useState } from "react";
import { SelectField } from "@/components/ui/Field";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { api, describeError } from "@/lib/api";
import { ROLE_LABEL, ROLE_LEVEL, canActAs, type Role } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import type { Role as ApiRole, User } from "@/lib/types";

/*
 * Promote or demote an account that already exists.
 *
 * Every new account arrives as EMPLOYEE. This is how anyone above that floor is
 * granted — which is why it lives here rather than in a database script: a role
 * changed through this control is audit-logged with its actor and a before/after
 * diff, and it takes effect immediately.
 *
 * Three rules the UI mirrors, all enforced again by the server:
 *
 *   - An actor may not assign a role above their own. An ADMIN cannot mint a
 *     SUPER_ADMIN, or they could escalate past whoever promoted them.
 *   - An actor may not modify an account more privileged than themselves. The
 *     control is hidden rather than disabled so the screen does not imply an
 *     action that would fail.
 *   - Nobody edits their own row. Self-promotion would sidestep rule one.
 *
 * The two lists overlap on purpose. `role-assignments` decides the role an
 * account is *born* with and is consulted once, at creation, for people who have
 * not signed in yet. This decides the role an account *has*, for everyone else.
 */

export function UserRoleControl({ user, onChanged }: { user: User; onChanged: () => void }) {
  const { user: actor } = useAuth();
  const [selected, setSelected] = useState<Role>(user.role);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const actorRole = actor?.role;

  // The server refuses both of these with 403; hiding them keeps the screen honest.
  if (!actorRole) return null;
  if (user.id === actor?.id) {
    return <span className="text-mini text-ink-muted">That is you</span>;
  }
  if (ROLE_LEVEL[user.role as Role] > ROLE_LEVEL[actorRole]) {
    return <span className="text-mini text-ink-muted">Above your own role</span>;
  }

  // Only roles at or below the actor's own are offered.
  const assignable = (Object.keys(ROLE_LABEL) as Role[]).filter(
    (r) => ROLE_LEVEL[r] <= ROLE_LEVEL[actorRole],
  );
  const unchanged = selected === user.role;

  async function apply() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const updated = await api.patch<User>(`/admin/users/${user.id}/role`, {
        role: selected,
      });
      setDone(`${ROLE_LABEL[updated.role as ApiRole]} now`);
      onChanged();
    } catch (err) {
      setError(describeError(err, { 403: "That role is above your own, or the account is." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex items-end gap-2">
        <SelectField
          /* Visually hidden: the row already names the person, and a repeated
             visible "Role" label on every line is noise. Still a real <label>, so
             the select keeps its accessible name. */
          label={<span className="sr-only">Role for {user.email}</span>}
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value as Role);
            setDone(null);
          }}
          disabled={busy}
          className="h-9 w-40"
        >
          {assignable.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </SelectField>
        {unchanged ? null : (
          <ConfirmButton
            label="Set"
            confirmLabel="Change role"
            onConfirm={apply}
            disabled={busy}
          />
        )}
      </div>
      {error ? (
        <p role="alert" className="text-mini font-semibold text-state-danger-ink">
          {error}
        </p>
      ) : null}
      {done && !error ? <p className="text-mini text-state-go-ink">{done}</p> : null}
    </div>
  );
}

/** True when this viewer could promote anyone at all, used to size the explanation. */
export function viewerCanAssign(actorRole: Role | undefined): boolean {
  return canActAs(actorRole, "ADMIN");
}