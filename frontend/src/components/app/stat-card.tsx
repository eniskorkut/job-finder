import type { LucideIcon } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral",
  loading = false,
}: {
  label: string;
  value: number | string;
  hint?: string;
  icon: LucideIcon;
  tone?: "neutral" | "accent" | "success" | "warning";
  loading?: boolean;
}) {
  const tones = {
    neutral: "bg-surface-muted text-ink-muted",
    accent: "bg-accent-soft text-accent-ink",
    success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning",
  } as const;

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-surface p-4 shadow-[var(--shadow-card)] transition-[box-shadow] duration-150 ease-out pointer-hover:shadow-[var(--shadow-card-hover)]">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12px] font-medium tracking-[0.02em] text-ink-subtle uppercase">
          {label}
        </span>
        <span
          aria-hidden
          className={cn(
            "flex size-7 items-center justify-center rounded-full",
            tones[tone],
          )}
        >
          <Icon className="size-3.5" strokeWidth={2} />
        </span>
      </div>
      {loading ? (
        <Skeleton className="h-7 w-16" />
      ) : (
        <span className="tabular text-2xl leading-7 font-semibold text-ink">
          {value}
        </span>
      )}
      {hint ? (
        <span className="text-[12px] leading-4 text-ink-subtle">{hint}</span>
      ) : null}
    </div>
  );
}
