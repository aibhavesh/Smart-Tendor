"use client";

import { useState } from "react";
import { LogOut } from "lucide-react";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Card, CardHeader, DataRow } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ROLE_DESCRIPTION, ROLE_LABEL, ROLE_LEVEL } from "@/lib/roles";
import { useAuth } from "@/lib/auth";

/*
 * Profile.
 *
 * Read-only by necessity, not by choice: the API has GET /auth/me but no PATCH. If
 * self-service editing is wanted, the backend needs PATCH /auth/me first.
 *
 * There is no password-management section because the API does not yet expose a
 * password-change or reset endpoint. Authentication settings are therefore read-only.
 */
function ProfileBody() {
  const { user, logout } = useAuth();
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  /*
   * No navigation here. `logout()` flips auth status to anonymous, and RequireAuth
   * already redirects on that. Navigating as well raced the in-flight revoke request and
   * showed up as an aborted POST /auth/logout — the server had processed it, but relying
   * on that race for a security-relevant revoke is not something to leave in place.
   */
  async function onLogout() {
    setBusy(true);
    await logout();
  }

  return (
    <div className="flex flex-col gap-6 max-w-[640px]">
      <div>
        <h1 className="font-outfit font-black text-display-sm tracking-tight text-ink-strong">
          Profile
        </h1>
        <p className="text-ui text-ink-strong/60 mt-1.5">Your account and access level.</p>
      </div>

      <Card>
        <CardHeader title="Account" />
        <DataRow label="Name">{user.full_name}</DataRow>
        <DataRow label="Email">{user.email}</DataRow>
        <DataRow label="Role">
          {ROLE_LABEL[user.role]}{" "}
          <span className="text-caption text-ink-muted">(level {ROLE_LEVEL[user.role]})</span>
          <span className="block text-caption text-ink-muted">
            {ROLE_DESCRIPTION[user.role]}
          </span>
        </DataRow>
        <DataRow label="Status">{user.is_active ? "Active" : "Deactivated"}</DataRow>
        <DataRow label="Member since">{new Date(user.created_at).toLocaleDateString()}</DataRow>
        <DataRow label="Last sign-in">
          {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}
        </DataRow>
      </Card>

      <Card>
        <CardHeader
          title="Sign-in"
          description="This platform holds no password of yours. You sign in with your work Google account, so passwords, two-factor and recovery are all managed there."
        />
        <p className="text-caption text-ink-muted">
          Signed in as <span className="font-semibold text-ink">{user.email}</span>.
        </p>
      </Card>

      <Card>
        <CardHeader
          title="Session"
          description="Signing out revokes the refresh token on the server, not just in this browser."
        />
        <Button variant="destructive" size="sm" onClick={onLogout} disabled={busy}>
          <LogOut className="w-3.5 h-3.5" aria-hidden="true" />
          {busy ? "Signing out…" : "Sign out"}
        </Button>
      </Card>

      <p className="text-caption text-ink-muted">
        Name and email cannot be changed here — the API exposes no endpoint for it. An
        administrator can change your role from the administration console.
      </p>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileBody />
    </RequireAuth>
  );
}
