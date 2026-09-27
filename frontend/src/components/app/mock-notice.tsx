import { Info } from "lucide-react";

import { cn } from "@/lib/cn";

/**
 * Phase 1 has no live integrations, so every screen that shows mock or
 * not-yet-implemented data says so explicitly.
 */
export function MockNotice({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-[var(--radius-card)] bg-info-soft px-3.5 py-2.5 text-[12.5px] leading-5 text-ink-muted",
        className,
      )}
    >
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-info" strokeWidth={2} />
      <p>
        {children ?? (
          <>
            Bu ekrandaki ilanlar <strong className="font-semibold">örnek veridir</strong>;
            gerçek Gmail/Hotmail hesaplarınızdan gelmez. Gerçek tarama 2. aşamada
            başlayacak.
          </>
        )}
      </p>
    </div>
  );
}
