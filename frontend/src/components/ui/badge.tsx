import { cn } from "@/lib/cn";

type Variant =
  | "neutral"
  | "accent"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "muted";

const variants: Record<Variant, string> = {
  neutral: "bg-surface-muted text-ink-muted shadow-[var(--shadow-card)]",
  muted: "bg-transparent text-ink-subtle",
  accent: "bg-accent-soft text-accent-ink",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info",
};

export function Badge({
  variant = "neutral",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: Variant }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
