"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader, DataRow } from "@/components/ui/Card";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState, SkeletonRows } from "@/components/ui/States";
import { Pagination, TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, describeError, query } from "@/lib/api";
import { ROLES, ROLE_DESCRIPTION, ROLE_LABEL, canActAs, type Role } from "@/lib/roles";
import { useAuth } from "@/lib/auth";
import { useResource } from "@/lib/use-api";
import type { ApiUsage, Page, SystemHealth, User } from "@/lib/types";

const LIMIT = 20;

function HealthCard() {
  const health = useResource<SystemHealth>((s) => api.get("/admin/system-health", s), []);

  if (health.error) return null;
  if (health.loading || !health.data) return <SkeletonRows rows={3} />;

  const h = health.data;
  return (
    <Card>
      <CardHeader
        title="System health"
        actions={
          <span
            className={`text-mini font-black tracking-wide ${
              h.healthy ? "text-state-go-ink" : "text-state-danger-ink"
            }`}
          >
            {h.healthy ? "HEALTHY" : "DEGRADED"}
          </span>
        }
      />
      {h.components.map((c) => (
        <DataRow key={c.name} label={c.name}>
          <span
            className={
              c.status === "ok"
                ? "text-caption text-state-go-ink font-semibold"
                : "text-caption text-state-danger-ink font-semibold"
            }
          >
            {c.status}
          </span>
          {c.detail ? <span className="block text-mini text-ink-muted">{c.detail}</span> : null}
        </DataRow>
      ))}
      <DataRow label="CPU">{h.host.cpu_percent.toFixed(1)}%</DataRow>
      <DataRow label="Memory">
        {h.host.memory_percent.toFixed(1)}% of {h.host.memory_total_mb.toFixed(0)} MB
      </DataRow>
      <DataRow label="Disk">
        {h.host.disk_percent.toFixed(1)}% of {h.host.disk_total_gb.toFixed(0)} GB
      </DataRow>
    </Card>
  );
}

function UsageCard() {
  const usage = useResource<ApiUsage>((s) => api.get("/admin/api-usage", s), []);
  if (usage.error || usage.loading || !usage.data) return null;

  const u = usage.data;
  return (
    <Card>
      <CardHeader title="API usage" description={`${u.total_requests} requests recorded.`} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          <p className="text-nano font-semibold tracking-wide text-ink-muted">BY STATUS</p>
          {Object.entries(u.by_status_class).map(([k, v]) => (
            <DataRow key={k} label={k}>
              {v}
            </DataRow>
          ))}
        </div>
        <div>
          <p className="text-nano font-semibold tracking-wide text-ink-muted">BY METHOD</p>
          {Object.entries(u.by_method).map(([k, v]) => (
            <DataRow key={k} label={k}>
              {v}
            </DataRow>
          ))}
        </div>
      </div>
    </Card>
  );
}

function UsersCard() {
  const { user: me } = useAuth();
  const isSuperAdmin = canActAs(me?.role, "SUPER_ADMIN");

  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const page = useResource<Page<User>>(
    (s) => api.get(`/admin/users${query({ limit: LIMIT, offset })}`, s),
    [offset],
  );

  async function act(run: () => Promise<unknown>) {
    setError(null);
    try {
      await run();
      page.reload();
    } catch (err) {
      setError(
        describeError(err, {
          403: "You cannot assign a role at or above your own, or change your own account.",
        }),
      );
    }
  }

  return (
    <Card>
      <CardHeader
        title="Users"
        description="Everyone here already has an account. Roles are enforced on the server for every request."
        actions={
          <ButtonLink href="/admin/role-assignments" variant="secondary" size="sm">
            <UserPlus className="w-3.5 h-3.5" aria-hidden="true" />
            Pre-provision a role
          </ButtonLink>
        }
      />
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
        <SkeletonRows rows={6} />
      ) : (
        <>
          <Table>
            <THead>
              <TH>Name</TH>
              <TH>Email</TH>
              <TH>Role</TH>
              <TH>Active</TH>
              <TH />
            </THead>
            <TBody>
              {page.data.items.map((u) => (
                <TR key={u.id}>
                  <TD className="max-w-[22ch] truncate">{u.full_name}</TD>
                  <TD className="max-w-[26ch] truncate text-caption text-ink-muted">{u.email}</TD>
                  <TD>
                    <select
                      aria-label={`Role for ${u.email}`}
                      value={u.role}
                      onChange={(e) =>
                        act(() =>
                          api.patch(`/admin/users/${u.id}/role`, { role: e.target.value as Role }),
                        )
                      }
                      className="rounded-control border border-ink-strong/15 bg-surface/70 px-2 py-1 text-caption text-ink"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r} title={ROLE_DESCRIPTION[r]}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </select>
                  </TD>
                  <TD>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        act(() =>
                          api.patch(`/admin/users/${u.id}/active`, { is_active: !u.is_active }),
                        )
                      }
                    >
                      {u.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </TD>
                  <TD className="text-right">
                    {isSuperAdmin ? (
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => act(() => api.del(`/admin/users/${u.id}`))}
                      >
                        Delete
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page.data} onChange={setOffset} label="users" />
        </>
      )}
    </Card>
  );
}

function AdminBody() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Administration
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">Accounts, health and usage.</p>
      </div>
      <UsersCard />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <HealthCard />
        <UsageCard />
      </div>
    </div>
  );
}

export default function AdminPage() {
  return (
    <RequireAuth minRole="ADMIN">
      <AdminBody />
    </RequireAuth>
  );
}
