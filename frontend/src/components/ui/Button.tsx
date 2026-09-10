import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/*
 * Buttons. Screens compose these; screens do not style buttons.
 *
 * The primary fill is --color-brand-hover, not --color-brand. Measured, white on
 * --color-brand is 3.66:1 and fails AA at button text sizes; brand-hover is 4.59:1.
 * The landing page's CTA still uses the brighter fill — see scripts/check-contrast.mjs.
 */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
export type ButtonSize = "sm" | "md";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-brand-hover hover:bg-brand-deep text-white shadow-cta disabled:hover:bg-brand-hover",
  secondary:
    "bg-surface/70 hover:bg-surface border border-ink-strong/10 text-ink disabled:hover:bg-surface/70",
  ghost: "bg-transparent hover:bg-ink-strong/5 text-brand-ink disabled:hover:bg-transparent",
  destructive:
    "bg-state-danger hover:bg-state-danger-ink text-white disabled:hover:bg-state-danger",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-9 px-4 text-ui leading-5 rounded-control gap-2",
  md: "h-11 px-6 text-ui leading-5 rounded-surface gap-2.5",
};

const BASE =
  "inline-flex items-center justify-center font-semibold transition-colors select-none " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-ink " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

function classes(variant: ButtonVariant, size: ButtonSize, className?: string) {
  return `${BASE} ${VARIANT[variant]} ${SIZE[size]} ${className ?? ""}`;
}

type ButtonProps = ComponentProps<"button"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={classes(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}

type ButtonLinkProps = ComponentProps<typeof Link> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

/** Same surface as Button, but navigates. Use for anything that changes route. */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link className={classes(variant, size, className)} {...rest}>
      {children}
    </Link>
  );
}
