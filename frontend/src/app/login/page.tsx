"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { GoogleSignIn } from "@/components/auth/GoogleSignIn";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { useAuth } from "@/lib/auth";
import { describeError } from "@/lib/api";

/*
 * Sign in — email/password, with Google as an optional alternative.
 *
 * Either method reaches the same account: an address on an allowed organisation
 * domain (or an individually excepted one) is admitted, and a first sign-in creates
 * the account automatically. Google is shown only when the build has a client ID
 * configured (`GoogleSignIn` renders nothing otherwise), so this page works end to
 * end on email/password alone when Google isn't set up.
 */

function LoginBody() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";
  const { loginWithPassword } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await loginWithPassword(email.trim(), password);
      router.replace(next);
    } catch (err) {
      setError(
        describeError(err, {
          401: "That email or password isn't right. Try again, or use Google below.",
          403: "This account is not permitted to sign in. Contact an administrator.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {error ? (
        <p
          role="alert"
          className="rounded-control bg-state-danger/10 border border-state-danger/30 px-3 py-2.5 text-caption font-semibold text-state-danger-ink"
        >
          {error}
        </p>
      ) : null}

      <div className="flex items-start gap-2.5 text-caption text-ink-strong/70">
        <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5 text-brand" aria-hidden="true" />
        <p>
          Use your <strong className="font-semibold text-ink">work email address</strong>.
          Personal addresses cannot be used — access is limited to the organisation&rsquo;s
          own email domain.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Signing in…" : "Login"}
        </Button>
      </form>

      <div className="flex items-center gap-3" aria-hidden="true">
        <div className="h-px flex-1 bg-ink-strong/10" />
        <span className="text-mini font-semibold text-ink-muted uppercase tracking-wide">Or</span>
        <div className="h-px flex-1 bg-ink-strong/10" />
      </div>

      <GoogleSignIn
        label="Sign in with Google"
        onError={setError}
        onSuccess={() => router.replace(next)}
      />

      <p className="text-caption text-ink-strong/70 text-center">
        Don&rsquo;t have an account?{" "}
        <Link href="/register" className="font-semibold text-brand-ink hover:underline">
          Sign up
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <AuthLayout
      title="Welcome back"
      lede="Pick up where you left off."
      footer={
        <>
          Signing up for the first time creates your account automatically. If you need
          more than everyday access, ask an administrator to set your role before you sign in.
        </>
      }
    >
      <Suspense fallback={null}>
        <LoginBody />
      </Suspense>
    </AuthLayout>
  );
}
