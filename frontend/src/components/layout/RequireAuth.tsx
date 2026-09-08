"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { AppShell } from "./AppShell";
import { SkeletonRows } from "@/components/ui/States";
import { EmptyState } from "@/components/ui/States";
import { ButtonLink } from "@/components/ui/Button";
import { canActAs, type Role } from "@/lib/roles";
import { useAuth } from "@/lib/auth";

/*
 * Route guard for authenticated screens.
 *
 * `status` starts as "loading" while the persisted refresh token is exchanged, so this
 * must not treat "no user yet" as "signed out" — doing so would bounce every reload to
 * the login screen. Only an explicit "anonymous" redirects.
 *
 * `minRole` hides a screen the user cannot use. It is presentation only: the server
 * enforces the real check on every request, and a hidden route is not a secured one.
 */
export function RequireAuth({
  children,
  minRole = "EMPLOYEE",
}: {
  children: ReactNode;
  minRole?: Role;
}) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname() ?? "/";

  useEffect(() => {
    if (status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [status, router, pathname]);

  if (status === "loading" || (status === "anonymous" && !user)) {
    return (
      <div className="w-full max-w-[1280px] mx-auto px-6 lg:px-10 py-16">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (!user) return null;

  if (!canActAs(user.role, minRole)) {
    return (
      <AppShell role={user.role} userName={user.full_name}>
        <EmptyState
          title="You do not have access to this screen"
          description={`This section needs the ${minRole} role or higher. Your account is ${user.role}.`}
          action={<ButtonLink href="/dashboard">Back to dashboard</ButtonLink>}
        />
      </AppShell>
    );
  }

  return (
    <AppShell role={user.role} userName={user.full_name}>
      {children}
    </AppShell>
  );
}
