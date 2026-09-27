"use client";

import { forwardRef } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
type Size = "sm" | "md" | "lg" | "icon";

const variants: Record<Variant, string> = {
  primary:
    "bg-accent text-white shadow-[var(--shadow-card)] pointer-hover:bg-accent-hover dark:text-[oklch(0.16_0.01_264)]",
  secondary:
    "bg-surface text-ink shadow-[var(--shadow-card)] pointer-hover:bg-surface-hover pointer-hover:shadow-[var(--shadow-card-hover)]",
  ghost: "text-ink-muted pointer-hover:bg-surface-muted pointer-hover:text-ink",
  danger: "bg-danger text-white pointer-hover:brightness-95",
  success: "bg-success text-white pointer-hover:brightness-95",
};

const sizes: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-2.5 text-[13px]",
  md: "h-9.5 gap-2 px-3.5 text-sm",
  lg: "h-11 gap-2 px-4 text-[15px]",
  icon: "size-9 justify-center",
};

// Better UI: 0.96 press scale, named transition properties only.
const tapScale = "active:not-disabled:scale-[0.96]";

/** Shared recipe so links can look like buttons without nesting them. */
export function buttonStyles({
  variant = "primary",
  size = "md",
  isStatic = false,
  className,
}: {
  variant?: Variant;
  size?: Size;
  isStatic?: boolean;
  className?: string;
} = {}) {
  return cn(
    "inline-flex select-none items-center rounded-[var(--radius-control)] font-medium whitespace-nowrap",
    "transition-[scale,background-color,color,box-shadow,opacity] duration-150 ease-out",
    "disabled:pointer-events-none disabled:opacity-50",
    variants[variant],
    sizes[size],
    !isStatic && tapScale,
    className,
  );
}

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  static?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      variant = "primary",
      size = "md",
      loading = false,
      static: isStatic = false,
      disabled,
      children,
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        data-loading={loading ? "" : undefined}
        className={buttonStyles({ variant, size, isStatic, className })}
        {...props}
      >
        {loading ? (
          <Loader2 aria-hidden className="size-4 animate-spin" strokeWidth={2} />
        ) : null}
        {children}
      </button>
    );
  },
);
