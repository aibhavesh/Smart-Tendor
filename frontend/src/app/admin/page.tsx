"use client";

import { RequireAuth } from "@/components/layout/RequireAuth";
import { TenderRetirement } from "@/components/admin/TenderRetirement";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState, SkeletonRows } from "@/components/ui/States";
import { api, query } from "@/lib/api";
import { ROLE_DESCRIPTION, ROLE_LABEL, ROLES } from "@/lib/roles";
import { useResource } from "@/lib/use-api";
import type { Page, User } from "@/lib/types";

function UsersByRole({ users }: { users: User[] }) {
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
                  <li key={user.id} className="flex justify-between gap-4 py-3">
                    <span>
                      {user.full_name} <span className="text-ink-muted">{user.email}</span>
                    </span>
                    <span className={user.is_active ? "text-state-go-ink" : "text-state-danger-ink"}>
                      {user.is_active ? "Active" : "Inactive"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-3 text-caption text-ink-muted">No {ROLE_LABEL[role].toLowerCase()} users.</p>
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
          description="Accounts are restricted to the configured organisation domain and shown by role."
        />
        {users.loading ? (
          <SkeletonRows rows={8} />
        ) : users.error ? (
          <ErrorState detail="Unable to load users." onRetry={users.reload} />
        ) : (
          <UsersByRole users={users.data?.items ?? []} />
        )}
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
