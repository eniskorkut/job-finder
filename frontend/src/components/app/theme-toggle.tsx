"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/cn";

type Theme = "light" | "dark";

const STORAGE_KEY = "jh-theme";

/**
 * Theme flip changes color on nearly every element at once. Every transition
 * on those properties would fire together and smear the switch, so
 * transitions are disabled for the swap and restored on the next frame.
 */
function applyTheme(next: Theme) {
  const override = document.createElement("style");
  override.append(
    document.createTextNode("*,*::before,*::after{transition:none !important}"),
  );
  document.head.append(override);

  document.documentElement.classList.toggle("dark", next === "dark");
  void document.body.offsetHeight; // force a synchronous style flush

  requestAnimationFrame(() => {
    requestAnimationFrame(() => override.remove());
  });
}

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç"}
      title={theme === "dark" ? "Açık tema" : "Koyu tema"}
      className={cn(
        "relative inline-flex size-9 items-center justify-center rounded-[var(--radius-control)]",
        "text-ink-muted transition-[scale,background-color,color] duration-150 ease-out",
        "active:scale-[0.96] pointer-hover:bg-surface-muted pointer-hover:text-ink",
        className,
      )}
    >
      {/* Both icons stay in the DOM; opacity/scale/blur cross-fades them. */}
      <Sun
        aria-hidden
        strokeWidth={1.75}
        className={cn(
          "absolute size-4.5 transition-[opacity,scale,filter] duration-200 ease-out",
          theme === "dark"
            ? "scale-100 opacity-100 blur-0"
            : "scale-25 opacity-0 blur-[4px]",
        )}
      />
      <Moon
        aria-hidden
        strokeWidth={1.75}
        className={cn(
          "absolute size-4.5 transition-[opacity,scale,filter] duration-200 ease-out",
          theme === "light" || theme === null
            ? "scale-100 opacity-100 blur-0"
            : "scale-25 opacity-0 blur-[4px]",
        )}
      />
    </button>
  );
}
