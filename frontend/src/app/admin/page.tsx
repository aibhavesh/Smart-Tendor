"use client";

import Link from "next/link";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { TenderRetirement } from "@/components/admin/TenderRetirement";
import { UserRoleControl } from "@/components/admin/UserRoleControl";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState, SkeletonRows } from "@/components/ui/States";
import { api, query } from "@/lib/api";
import { ROLE_DESCRIPTION, ROLE_LABEL, ROLES } from "@/lib/roles";
import { useResource } from "@/lib/use-api";
import type { Page, User } from "@/lib/types";

/*
 * Administration.
 *
 * Two lists govern roles and they answer different questions, which used to be
 * the single most confusing thing about this system because only one of them had
 * a screen:
 *
 *   - This page changes the role an account *has*. It applies immediately, to
 *     anyone who has already signed in, and every change is audit-logged.
 *   - "Pre-provisioned roles" decides the role an account is *born* with, and is
 *     consulted exactly once at creation. It exists for somebody who has not
 *     signed in yet.
 *
 * A new account always arrives here as an employee. That is automatic and needs
 * no configuration: nobody is promoted by signing up.
 */

function UsersByRole({
  users,
  onChanged,
}: {
  users: User[];
  onChanged: () => void;
}) {
  return (
    <div className="space-y-5">
      {ROLES.map((role) => {
        const members = users.filter((user) => user.role === role);
        return (
          <section key={role} aria-labelledby={`role-${role}`}>
            <div className="flex items-baseline justify-between gap-4 border-b border-ink-strong/10 pb-2">
              <div>
                <h3 id={`role-${role}`} className="font-outfit font-bold text-ui text-ink">
                  {ROLE_LABEL[role]}
                </h3>
                <p className="text-mini text-ink-muted">{ROLE_DESCRIPTION[role]}</p>
              </div>
              <span className="text-caption font-semibold text-ink-muted">
                {members.length} user{members.length === 1 ? "" : "s"}
              </span>
            </div>
            {members.length > 0 ? (
              <ul className="divide-y divide-ink-strong/5">
                {members.map((user) => (
                  <li key={user.id} className="flex flex-wrap items-center justify-between gap-4 py-3">
                    <span className="min-w-0">
                      <span className="block truncate">{user.full_name}</span>
                      <span className="block truncate text-caption text-ink-muted">
                        {user.email}
                      </span>
                    </span>
                    <span className="flex items-center gap-3">
                      <span
                        className={
                          user.is_active ? "text-caption text-state-go-ink" : "text-caption text-state-danger-ink"
                        }
                      >
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                      <UserRoleControl user={user} onChanged={onChanged} />
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-3 text-caption text-ink-muted">
                No {ROLE_LABEL[role].toLowerCase()} users.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}

function Administration() {
  const users = useResource<Page<User>>(
    (signal) => api.get(`/admin/users${query({ limit: 200 })}`, signal),
    [],
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="User management"
          description="Every new account starts as an employee. Change a role here to give someone more or less access — it applies immediately and is recorded in the audit trail."
        />
        {users.loading ? (
          <SkeletonRows rows={8} />
        ) : users.error ? (
          <ErrorState detail="Unable to load users." onRetry={users.reload} />
        ) : (
          <UsersByRole users={users.data?.items ?? []} onChanged={users.reload} />
        )}
        <p className="mt-5 border-t border-ink-strong/10 pt-4 text-caption text-ink-muted">
          Granting a role to somebody who has not signed in yet is a different thing, done on{" "}
          <Link
            href="/admin/role-assignments"
            className="font-semibold text-brand-ink underline underline-offset-2"
          >
            the pre-provisioned roles page
          </Link>
          . That list is read once when an account is created and never again.
        </p>
      </Card>
      <TenderRetirement />
    </div>
  );
}

export default function AdminPage() {
  return (
    <RequireAuth minRole="ADMIN">
      <Administration />
    </RequireAuth>
  );
}