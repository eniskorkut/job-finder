import {
  AlertTriangle,
  CheckCircle2,
  Info,
  OctagonAlert,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "danger";

const tones: Record<Tone, { wrapper: string; icon: LucideIcon }> = {
  info: { wrapper: "bg-info-soft text-info", icon: Info },
  success: { wrapper: "bg-success-soft text-success", icon: CheckCircle2 },
  warning: { wrapper: "bg-warning-soft text-warning", icon: AlertTriangle },
  danger: { wrapper: "bg-danger-soft text-danger", icon: OctagonAlert },
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
  action,
}: {
  tone?: Tone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}) {
  const { wrapper, icon: Icon } = tones[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-[var(--radius-card)] p-3.5",
        wrapper,
        className,
      )}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={2} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {title ? (
          <p className="text-[13px] leading-5 font-semibold">{title}</p>
        ) : null}
        {children ? (
          <div className="text-[13px] leading-5 text-ink-muted">{children}</div>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
