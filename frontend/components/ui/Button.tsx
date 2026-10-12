import clsx from "clsx";
import { LoaderCircle, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-control border font-medium whitespace-nowrap transition-colors duration-150";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-teal bg-teal text-surface hover:border-teal-hover hover:bg-teal-hover",
  secondary: "border-line bg-surface text-ink hover:border-muted hover:bg-paper",
  ghost: "border-transparent bg-transparent text-ink hover:bg-teal-tint",
  danger: "border-danger bg-danger text-surface hover:border-danger-hover hover:bg-danger-hover",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-13",
  md: "h-10 px-4 text-15",
  lg: "h-12 px-6 text-18",
};

const DISABLED = "cursor-not-allowed border-line bg-paper text-muted";

/** Classes for a link that should look like a button. */
export function buttonClasses(variant: ButtonVariant = "primary", size: ButtonSize = "md"): string {
  return clsx(BASE, VARIANTS[variant], SIZES[size]);
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner and blocks clicks while an action is running. */
  loading?: boolean;
  icon?: LucideIcon;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon: Icon,
  disabled = false,
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  const iconSize = size === "lg" ? "size-5" : "size-4";
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        BASE,
        SIZES[size],
        disabled && !loading ? DISABLED : VARIANTS[variant],
        loading && "cursor-progress",
        className,
      )}
      {...rest}
    >
      {loading ? (
        <LoaderCircle aria-hidden className={clsx(iconSize, "motion-safe:animate-spin")} />
      ) : (
        Icon && <Icon aria-hidden className={iconSize} />
      )}
      {children}
    </button>
  );
}
