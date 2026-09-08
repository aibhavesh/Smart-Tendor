"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { SelectField, TextField } from "@/components/ui/Field";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError, query } from "@/lib/api";
import { ROLES, ROLE_DESCRIPTION, ROLE_LABEL, ROLE_LEVEL, type Role } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/use-api";
import type { Page, RoleAssignment } from "@/lib/types";

const LIMIT = 25;

/*
 * The pre-provisioned elevation list.
 *
 * Anyone signing in with an organisation Google account gets an account automatically,
 * at EMPLOYEE. This list is how somebody starts higher: an administrator records the
 * role against their address *before* they first sign in.
 *
 * Two limits worth stating on screen rather than discovering through an error:
 *
 *   - It cannot change anyone who already has an account. That is the Users table.
 *   - It cannot grant a role above the administrator's own, exactly as the Users table
 *     cannot. Otherwise this list would be a way around that rule.
 */

/** EMPLOYEE is the default every org account already gets, so it cannot be assigned. */
function assignableRoles(actorRole: Role | undefined): Role[] {
  if (!actorRole) return [];
  return ROLES.filter(
    (r) => r !== "EMPLOYEE" && ROLE_LEVEL[r] <= ROLE_LEVEL[actorRole],
  );
}

function CreateForm({ onCreated }: { onCreated: () => void }) {
  const { user } = useAuth();
  const options = assignableRoles(user?.role);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>(options[0] ?? "MANAGER");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const created = await api.post<RoleAssignment>("/admin/role-assignments", {
        email: email.trim(),
        role,
      });
      setDone(created.email);
      setEmail("");
      onCreated();
    } catch (err) {
      setError(
        describeError(err, {
          // 409 carries the server's own wording, which names the endpoint to use
          // instead — more useful than anything generic written here.
          403: "That address is not on the organisation's email domain, or the role is above your own.",
          422: "Pick an elevated role — every organisation account already starts as an employee.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  if (options.length === 0) {
    return (
      <p className="text-caption text-ink-muted">
        Your role cannot pre-provision any other role.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      {error ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink"
        >
          {error}
        </p>
      ) : null}
      {done ? (
        <p
          role="status"
          className="rounded-control bg-state-go/10 border border-state-go/30 px-3 py-2 text-caption font-semibold text-state-go-ink"
        >
          {done} will receive that role the first time they sign in.
        </p>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <TextField
          label="Work email"
          type="email"
          required
          placeholder="name@your-domain.com"
          helper="Must be on an allowed organisation domain."
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <SelectField
          label="Role at first sign-in"
          value={role}
          helper={ROLE_DESCRIPTION[role]}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {options.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </SelectField>
      </div>

      <Button type="submit" size="sm" className="w-fit" disabled={busy || !email.trim()}>
        <UserPlus className="w-3.5 h-3.5" aria-hidden="true" />
        {busy ? "Saving…" : "Pre-provision role"}
      </Button>
    </form>
  );
}

function AssignmentsBody() {
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const page = useResource<Page<RoleAssignment>>(
    (s) => api.get(`/admin/role-assignments${query({ limit: LIMIT, offset })}`, s),
    [offset],
  );

  async function revoke(id: string) {
    setError(null);
    try {
      await api.del(`/admin/role-assignments/${id}`);
      page.reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Pre-provisioned roles
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">
          Give someone a role before their first sign-in. Everyone else starts as an
          employee.
        </p>
      </div>

      <Card>
        <CardHeader
          title="Add someone"
          description="This only sets the role their account is created with. It has no effect on anyone who has already signed in — change those from the Users table."
        />
        <CreateForm onCreated={page.reload} />
      </Card>

      <Card>
        <CardHeader title="Current list" />
        {error ? (
          <p
            role="alert"
            className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2 text-caption font-semibold text-state-danger-ink mb-4"
          >
            {error}
          </p>
        ) : null}

        {page.error ? (
          <ErrorState detail={page.error} onRetry={page.reload} />
        ) : page.loading || !page.data ? (
          <SkeletonRows rows={5} />
        ) : page.data.items.length === 0 ? (
          <EmptyState
            title="Nobody is pre-provisioned"
            description="Anyone signing in with a work Google account will start as an employee."
            icon={UserPlus}
          />
        ) : (
          <>
            <Table>
              <THead>
                <TH>Email</TH>
                <TH>Role</TH>
                <TH>Status</TH>
                <TH>Added</TH>
                <TH />
              </THead>
              <TBody>
                {page.data.items.map((a) => (
                  <TR key={a.id}>
                    <TD className="max-w-[28ch] truncate">{a.email}</TD>
                    <TD>{ROLE_LABEL[a.role]}</TD>
                    <TD>
                      {a.is_consumed ? (
                        <span className="text-caption text-ink-muted">
                          Used
                          {a.consumed_at
                            ? ` · ${new Date(a.consumed_at).toLocaleDateString()}`
                            : ""}
                        </span>
                      ) : (
                        <span className="text-caption font-semibold text-brand-ink">
                          Awaiting first sign-in
                        </span>
                      )}
                    </TD>
                    <TD className="text-caption text-ink-muted whitespace-nowrap">
                      {new Date(a.assigned_at).toLocaleDateString()}
                      {a.assigned_by === null ? (
                        <span className="block text-mini">seeded at setup</span>
                      ) : null}
                    </TD>
                    <TD className="text-right">
                      {a.is_consumed ? (
                        /*
                         * Deliberately not offered. The account exists and carries its
                         * own role now, so removing this row would undo nothing and
                         * erase the record of how that role was granted.
                         */
                        <span className="text-mini text-ink-muted">
                          Account created — change the role from Users
                        </span>
                      ) : (
                        <ConfirmButton
                          label="Revoke"
                          confirmLabel="Revoke it"
                          onConfirm={() => revoke(a.id)}
                        />
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={page.data} onChange={setOffset} label="assignments" />
          </>
        )}
      </Card>
    </div>
  );
}

export default function RoleAssignmentsPage() {
  return (
    <RequireAuth minRole="ADMIN">
      <AssignmentsBody />
    </RequireAuth>
  );
}
