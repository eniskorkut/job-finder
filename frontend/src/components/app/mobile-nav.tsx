"use client";

import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/cn";

/**
 * Mobile navigation drawer. Uses the iOS-like drawer curve and can be
 * interrupted mid-flight because it is a transition, not a keyframe.
 */
export function MobileNav({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      triggerRef.current?.focus();
    };
  }, [open]);

  return (
    <div className={cn("lg:hidden", className)}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Menüyü aç"
        aria-expanded={open}
        className="inline-flex size-9 items-center justify-center rounded-[var(--radius-control)] text-ink-muted transition-[scale,background-color,color] duration-150 ease-out active:scale-[0.96] pointer-hover:bg-surface-muted pointer-hover:text-ink"
      >
        <Menu aria-hidden className="size-5" strokeWidth={1.75} />
      </button>

      <div
        aria-hidden={!open}
        onClick={() => setOpen(false)}
        className={cn(
          "fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]",
          "transition-[opacity] duration-200 ease-out",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Ana menü"
        tabIndex={-1}
        inert={!open}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col gap-1 overflow-y-auto bg-surface p-4 outline-none",
          "transition-[translate,opacity] duration-300",
          open ? "translate-x-0 opacity-100" : "-translate-x-full opacity-0",
        )}
        style={{ transitionTimingFunction: "var(--ease-drawer)" }}
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">Job Hunter</span>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Menüyü kapat"
            className="inline-flex size-8 items-center justify-center rounded-[var(--radius-control)] text-ink-muted transition-[background-color,color] duration-150 ease-out pointer-hover:bg-surface-muted pointer-hover:text-ink"
          >
            <X aria-hidden className="size-4.5" strokeWidth={1.75} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
