"use client";

import { Upload } from "lucide-react";
import { useId, type ComponentProps, type ReactNode } from "react";

/*
 * Form controls with label, helper and error states.
 *
 * Errors are wired through aria-describedby / aria-invalid rather than being colour
 * plus a red border — colour alone never conveys state anywhere in this theme.
 */

const CONTROL =
  "w-full rounded-control border bg-surface/70 px-3 text-ui leading-5 text-ink " +
  "placeholder:text-ink-muted transition-colors " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-ink " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const ok = "border-ink-strong/15 hover:border-ink-strong/25";
const bad = "border-state-danger";

function FieldShell({
  id,
  label,
  helper,
  error,
  required,
  children,
}: {
  id: string;
  label: string;
  helper?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-caption font-semibold text-ink">
        {label}
        {required ? (
          <span className="text-state-danger-ink ml-0.5" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-mini font-semibold text-state-danger-ink">
          {error}
        </p>
      ) : helper ? (
        <p id={`${id}-helper`} className="text-mini text-ink-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
}

type Common = { label: string; helper?: string; error?: string };

export function TextField({
  label,
  helper,
  error,
  className,
  ...rest
}: Common & ComponentProps<"input">) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} helper={helper} error={error} required={rest.required}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : helper ? `${id}-helper` : undefined}
        className={`${CONTROL} ${error ? bad : ok} h-11 ${className ?? ""}`}
        {...rest}
      />
    </FieldShell>
  );
}

export function DateField(props: Common & ComponentProps<"input">) {
  return <TextField {...props} type="date" />;
}

export function SelectField({
  label,
  helper,
  error,
  children,
  className,
  ...rest
}: Common & ComponentProps<"select">) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} helper={helper} error={error} required={rest.required}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : helper ? `${id}-helper` : undefined}
        className={`${CONTROL} ${error ? bad : ok} h-11 ${className ?? ""}`}
        {...rest}
      >
        {children}
      </select>
    </FieldShell>
  );
}

export function FileField({
  label,
  helper,
  error,
  fileName,
  className,
  ...rest
}: Common & { fileName?: string | null } & ComponentProps<"input">) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} helper={helper} error={error} required={rest.required}>
      <label
        htmlFor={id}
        className={`${CONTROL} ${error ? bad : ok} h-11 flex items-center gap-2.5 cursor-pointer ${className ?? ""}`}
      >
        <Upload className="w-4 h-4 text-ink-muted shrink-0" aria-hidden="true" />
        <span className={fileName ? "text-ink truncate" : "text-ink-muted"}>
          {fileName ?? "Choose a file…"}
        </span>
        <input
          id={id}
          type="file"
          className="sr-only"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : helper ? `${id}-helper` : undefined}
          {...rest}
        />
      </label>
    </FieldShell>
  );
}
