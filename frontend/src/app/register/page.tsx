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
 * Create account — email/password, with Google as an optional alternative.
 *
 * `POST /auth/register` applies the same organisation-domain admission gate as
 * Google sign-in, so this cannot be used to admit an address Google sign-in would
 * refuse. A duplicate email (Google or password) is rejected outright — this form
 * never attaches a password to somebody else's existing account.
 */

const MIN_PASSWORD_LENGTH = 8;

function RegisterBody() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";
  const { register } = useAuth();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setBusy(true);
    try {
      await register(email.trim(), password, fullName.trim());
      router.replace(next);
    } catch (err) {
      setError(
        describeError(err, {
          403: "That email address is not on the organisation's domain. Use your work email instead.",
          409: "An account with this email already exists. Try logging in instead.",
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
          label="Name"
          autoComplete="name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
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
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          helper={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Creating account…" : "Create Account"}
        </Button>
      </form>

      <div className="flex items-center gap-3" aria-hidden="true">
        <div className="h-px flex-1 bg-ink-strong/10" />
        <span className="text-mini font-semibold text-ink-muted uppercase tracking-wide">Or</span>
        <div className="h-px flex-1 bg-ink-strong/10" />
      </div>

      <GoogleSignIn
        label="Sign up with Google"
        onError={setError}
        onSuccess={() => router.replace(next)}
      />

      <p className="text-caption text-ink-strong/70 text-center">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-brand-ink hover:underline">
          Login
        </Link>
      </p>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <AuthLayout
      title="Create your account"
      lede="Set up access in a couple of minutes."
      footer={
        <>
          If you need more than everyday access, ask an administrator to set your role
          before you sign up.
        </>
      }
    >
      <Suspense fallback={null}>
        <RegisterBody />
      </Suspense>
    </AuthLayout>
  );
}
