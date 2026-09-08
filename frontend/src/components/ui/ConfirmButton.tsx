"use client";

import { useEffect, useState } from "react";
import { Button, type ButtonVariant } from "./Button";

/*
 * Destructive action with an inline confirmation step.
 *
 * A native `confirm()` would be simpler but sits outside the design system and cannot be
 * driven by the e2e suite. The confirm state auto-expires so a half-pressed delete never
 * lies in wait for a later stray click.
 */
export function ConfirmButton({
  label,
  confirmLabel = "Confirm",
  onConfirm,
  variant = "destructive",
  size = "sm",
  disabled,
}: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => Promise<unknown> | unknown;
  variant?: ButtonVariant;
  size?: "sm" | "md";
  disabled?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 5000);
    return () => clearTimeout(t);
  }, [armed]);

  if (!armed) {
    return (
      <Button variant={variant} size={size} disabled={disabled} onClick={() => setArmed(true)}>
        {label}
      </Button>
    );
  }

  return (
    <span className="inline-flex items-center gap-2">
      <Button
        variant={variant}
        size={size}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onConfirm();
          } finally {
            setBusy(false);
            setArmed(false);
          }
        }}
      >
        {busy ? "Working…" : confirmLabel}
      </Button>
      <Button variant="ghost" size={size} disabled={busy} onClick={() => setArmed(false)}>
        Cancel
      </Button>
    </span>
  );
}
