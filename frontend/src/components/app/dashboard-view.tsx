"use client";

import Link from "next/link";
import { useState } from "react";
import {
  BriefcaseBusiness,
  FileText,
  FlaskConical,
  RefreshCcw,
  Sparkles,
  Telescope,
} from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { useSession } from "@/components/app/session-provider";
import { StatCard } from "@/components/app/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonStyles } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ScoreBadge } from "@/components/ui/score";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, buildQuery } from "@/lib/api";
import { formatDateTime, workModeLabels } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { Job, JobStats, Overview, Page } from "@/lib/types";

const connectionLabels: Record<string, string> = {
  connected: "Bağlı",
  disconnected: "Bağlı değil",
  pending: "Bekliyor",
  needs_reauth: "Yetki yenile",
  error: "Hata",
};

export function DashboardView() {
  const { user } = useSession();
  const overview = useApiQuery<Overview>("/api/v1/me/overview");
  const stats = useApiQuery<JobStats>("/api/v1/jobs/stats");
  const recent = useApiQuery<Page<Job>>(
    `/api/v1/jobs${buildQuery({ sort: "score", page_size: 5 })}`,
  );

  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  async function runScan() {
    setScanning(true);
    setScanMessage(null);
    try {
      await api.post("/api/v1/sync/run");
      setScanMessage(
        "Tarama başlatıldı. (Bu mesajı görmemelisiniz; tarama henüz geliştirilmedi.)",
      );
    } catch (error) {
      setScanMessage(
        error instanceof ApiError
          ? error.message
          : "Tarama başlatılamadı.",
      );
    } finally {
      setScanning(false);
    }
  }

  const loading = overview.loading || stats.loading;
  const error = overview.error ?? stats.error;

  return (
    <div className="flex flex-col gap-6">
      <div className="stagger flex flex-col gap-1">
        <h1 className="text-xl leading-7 font-semibold tracking-[-0.01em] text-ink">
          Merhaba{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="text-[13px] text-ink-muted">
          Kişisel iş paneliniz. Örnek verilerle çalışıyor; gerçek tarama 2.
          aşamada açılacak.
        </p>
      </div>

      {error ? (
        <Card>
          <ErrorState
            error={error}
            onRetry={() => {
              overview.refetch();
              stats.refetch();
            }}
          />
        </Card>
      ) : null}

      <section className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Toplam ilan"
          value={stats.data?.total_jobs ?? 0}
          hint={stats.data?.mock_jobs ? `${stats.data.mock_jobs} örnek kayıt` : undefined}
          icon={BriefcaseBusiness}
          loading={loading}
        />
        <StatCard
          label="Yeni ilanlar"
          value={stats.data?.new_jobs ?? 0}
          hint="Henüz incelenmedi"
          icon={Telescope}
          tone="accent"
          loading={loading}
        />
        <StatCard
          label="Yüksek eşleşme"
          value={stats.data?.high_match_jobs ?? 0}
          hint={`${stats.data?.high_match_threshold ?? 70}+ puan`}
          icon={Sparkles}
          tone="success"
          loading={loading}
        />
        <StatCard
          label="Ortalama puan"
          value={stats.data?.average_score ?? "—"}
          hint="Örnek skorlar"
          icon={FileText}
          loading={loading}
        />
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div className="flex flex-col gap-1">
              <CardTitle>En yüksek eşleşmeler</CardTitle>
              <CardDescription>
                Puana göre sıralı ilk 5 ilan (örnek veri)
              </CardDescription>
            </div>
            <Link
              href="/jobs"
              className={buttonStyles({ variant: "secondary", size: "sm" })}
            >
              Tümünü gör
            </Link>
          </CardHeader>
          <CardContent>
            {recent.loading ? (
              <div className="flex flex-col gap-3">
                {[0, 1, 2].map((index) => (
                  <Skeleton key={index} className="h-12 w-full" />
                ))}
              </div>
            ) : recent.error ? (
              <ErrorState error={recent.error} onRetry={recent.refetch} />
            ) : !recent.data || recent.data.items.length === 0 ? (
              <EmptyState
                icon={BriefcaseBusiness}
                title="Henüz ilan yok"
                description="Örnek verileri yüklemek için: python -m app.cli seed"
              />
            ) : (
              <ul className="flex flex-col divide-y divide-line">
                {recent.data.items.map((job) => (
                  <li key={job.id} className="py-3 first:pt-0 last:pb-0">
                    <Link
                      href={`/jobs/${job.id}`}
                      className="flex items-center justify-between gap-4 rounded-[var(--radius-inner)] px-1 py-0.5 transition-[background-color] duration-150 ease-out pointer-hover:bg-surface-muted"
                    >
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate text-[13.5px] font-medium text-ink">
                          {job.title}
                        </span>
                        <span className="truncate text-[12px] text-ink-subtle">
                          {job.company} · {job.location ?? "—"} ·{" "}
                          {workModeLabels[job.work_mode] ?? job.work_mode}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {job.is_mock ? (
                          <Badge variant="info">Örnek</Badge>
                        ) : null}
                        <ScoreBadge score={job.match?.score ?? null} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle>Tarama</CardTitle>
              <CardDescription>
                {overview.data?.last_sync_at
                  ? `Son tarama: ${formatDateTime(overview.data.last_sync_at)}`
                  : "Henüz tarama yapılmadı"}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Button onClick={runScan} loading={scanning}>
                {scanning ? null : (
                  <RefreshCcw aria-hidden className="size-4" strokeWidth={2} />
                )}
                Şimdi Tara
              </Button>
              {scanMessage ? (
                <div
                  role="status"
                  className="rounded-[var(--radius-card)] bg-warning-soft px-3.5 py-2.5 text-[12px] leading-5 text-warning"
                >
                  {scanMessage}
                </div>
              ) : (
                <p className="text-[11.5px] leading-4 text-ink-subtle">
                  Tarama; Gmail/Hotmail okuma (2. aşama), DeepSeek skorlama ve
                  Telegram bildirimi (3. aşama) hazır olduğunda çalışacak.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Entegrasyon durumu</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2.5">
              {(overview.data?.integrations ?? []).map((integration) => (
                <div
                  key={integration.provider}
                  className="flex items-center justify-between gap-3 text-[12.5px]"
                >
                  <span className="text-ink-muted">{integration.label}</span>
                  <span className="flex items-center gap-2">
                    <Badge
                      variant={
                        integration.status === "connected" ? "success" : "neutral"
                      }
                    >
                      {connectionLabels[integration.status] ?? integration.status}
                    </Badge>
                    {integration.account_count > 1 ? (
                      <span className="text-[11.5px] text-ink-subtle">
                        {integration.account_count} hesap
                      </span>
                    ) : null}
                  </span>
                </div>
              ))}
              <Link
                href="/integrations"
                className="mt-1 text-[12.5px] font-medium text-accent-ink underline-offset-4 pointer-hover:underline"
              >
                Entegrasyonları yönet
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>CV durumu</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="flex items-center gap-2 text-[12.5px] text-ink-muted">
                <FlaskConical aria-hidden className="size-4" strokeWidth={1.5} />
                {overview.data?.has_active_cv
                  ? "Aktif CV var; eşleştirme 3. aşamada skorlanacak."
                  : "Henüz aktif CV yok."}
              </p>
              <Link
                href="/preferences"
                className={buttonStyles({ variant: "secondary", size: "sm" })}
              >
                CV ve tercihler
              </Link>
            </CardContent>
          </Card>
        </div>
      </section>

      {stats.data?.top_companies?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Şirket dağılımı</CardTitle>
            <CardDescription>En çok ilanı olan şirketler (örnek veri)</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {stats.data.top_companies.map((item) => (
              <span
                key={item.company}
                className="inline-flex items-center gap-2 rounded-full bg-surface-muted px-3 py-1 text-[12.5px] text-ink"
              >
                {item.company}
                <Badge variant="muted" className="tabular">
                  {item.count}
                </Badge>
              </span>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
