"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LogOut, Radar } from "lucide-react";

import { MobileNav } from "@/components/app/mobile-nav";
import { navItems } from "@/components/app/nav";
import { SessionProvider, useSession } from "@/components/app/session-provider";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useSession();

  return (
    <nav className="flex flex-col gap-0.5">
      {navItems
        .filter((item) => !item.ownerOnly || user?.role === "owner")
        .map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2",
                "transition-[background-color,color] duration-150 ease-out",
                "pointer-hover:bg-surface-muted",
                active
                  ? "bg-accent-soft text-accent-ink"
                  : "text-ink-muted pointer-hover:text-ink",
              )}
            >
              <Icon
                aria-hidden
                className="size-4.5 shrink-0"
                strokeWidth={active ? 2 : 1.5}
              />
              <span className="flex min-w-0 flex-col">
                <span
                  className={cn(
                    "truncate text-[13px]",
                    active ? "font-semibold" : "font-medium",
                  )}
                >
                  {item.label}
                </span>
              </span>
            </Link>
          );
        })}
    </nav>
  );
}

function UserCard() {
  const { user, loading } = useSession();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  const logout = useCallback(async () => {
    setSigningOut(true);
    try {
      await api.post("/api/v1/auth/logout");
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }, [router]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-1">
        <Skeleton className="size-8 rounded-full" />
        <div className="flex flex-1 flex-col gap-1.5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-2.5 w-32" />
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex items-center gap-2.5 rounded-[var(--radius-control)] px-1 py-1">
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent-ink"
      >
        {user.username.slice(0, 2).toUpperCase()}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[13px] font-medium text-ink">
          {user.full_name ?? user.username}
        </span>
        <span className="truncate text-[11px] text-ink-subtle">
          {user.email} · {user.role === "owner" ? "owner" : "üye"}
        </span>
      </span>
      <Button
        variant="ghost"
        size="icon"
        onClick={logout}
        loading={signingOut}
        aria-label="Çıkış yap"
        title="Çıkış yap"
      >
        {signingOut ? null : (
          <LogOut aria-hidden className="size-4" strokeWidth={1.75} />
        )}
      </Button>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <span
        aria-hidden
        className="flex size-8 items-center justify-center rounded-[10px] bg-accent text-white dark:text-[oklch(0.16_0.01_264)]"
      >
        <Radar className="size-4.5" strokeWidth={2} />
      </span>
      <span className="flex flex-col">
        <span className="text-[14px] leading-4 font-semibold text-ink">
          Job Hunter
        </span>
        <span className="text-[11px] text-ink-subtle">kişisel iş paneli</span>
      </span>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { error, refetch } = useSession();
  const router = useRouter();

  // An expired session invalidates the shell immediately (except on root cockpit).
  useEffect(() => {
    if (pathname !== "/" && error && error.includes("Oturum")) {
      router.replace("/login");
    }
  }, [error, router, pathname]);

  if (pathname === "/") {
    return <main className="min-h-screen bg-[#020203] text-[#f4f4f5]">{children}</main>;
  }

  return (
    <div className="min-h-dvh bg-canvas lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-line px-3.5 py-5 lg:flex">
        <Brand />
        <NavLinks />
        <div className="mt-auto flex flex-col gap-2 border-t border-line pt-3">
          <UserCard />
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] text-ink-subtle">Aşama 1 · mock veri</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      <div className="flex min-h-dvh flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur lg:hidden">
          <MobileNav>
            <NavLinks onNavigate={() => undefined} />
          </MobileNav>
          <Brand />
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
          </div>
        </header>

        {error ? (
          <div className="border-b border-line bg-warning-soft px-4 py-2 text-[13px] text-warning lg:px-8">
            Oturum bilgisi alınamadı: {error}{" "}
            <button
              type="button"
              onClick={refetch}
              className="font-semibold underline underline-offset-2"
            >
              Tekrar dene
            </button>
          </div>
        ) : null}

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 lg:px-8 lg:py-8">
          {children}
        </main>

        <footer className="mx-auto w-full max-w-6xl px-4 pb-6 text-[11px] text-ink-subtle lg:px-8">
          Gösterilen ilanlar örnek verilerdir. Gmail, Hotmail ve Telegram
          entegrasyonları henüz geliştirilmedi.
        </footer>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}
