import { cn } from "@/lib/cn";

export function scoreTone(score: number | null | undefined) {
  if (score === null || score === undefined) return "muted" as const;
  if (score >= 85) return "success" as const;
  if (score >= 70) return "accent" as const;
  if (score >= 50) return "warning" as const;
  return "danger" as const;
}

const toneClasses = {
  success: "bg-success-soft text-success",
  accent: "bg-accent-soft text-accent-ink",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  muted: "bg-surface-muted text-ink-subtle",
} as const;

export function ScoreBadge({
  score,
  className,
  suffix = "puan",
}: {
  score: number | null | undefined;
  className?: string;
  suffix?: string;
}) {
  const tone = scoreTone(score);
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold",
        toneClasses[tone],
        className,
      )}
      title={score === null || score === undefined ? "Henüz skorlanmadı" : undefined}
    >
      {score === null || score === undefined ? "—" : score}
      {score === null || score === undefined ? null : (
        <span className="font-normal opacity-80">{suffix}</span>
      )}
    </span>
  );
}

export function ScoreBar({
  score,
  className,
}: {
  score: number | null;
  className?: string;
}) {
  const value = score ?? 0;
  const tone = scoreTone(score);
  const barColors = {
    success: "bg-success",
    accent: "bg-accent",
    warning: "bg-warning",
    danger: "bg-danger",
    muted: "bg-ink-subtle",
  } as const;
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-surface-muted",
        className,
      )}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-300 ease-out",
          barColors[tone],
        )}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}
