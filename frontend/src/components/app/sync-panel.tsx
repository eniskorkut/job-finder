"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  MailCheck,
  RefreshCcw,
  Square,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { SyncJobProgress, SyncRunResponse, SyncStatus } from "@/lib/types";

const ACTIVE_STATUSES = new Set(["queued", "running"]);
const POLL_INTERVAL_MS = 1500;

const kindLabels: Record<string, string> = {
  mail_scan: "Posta taraması",
  scoring: "CV analizi",
  notify: "Telegram bildirimi",
};

const statusLabels: Record<string, string> = {
  queued: "Kuyrukta",
  running: "Sürüyor",
  completed: "Tamamlandı",
  partial_failed: "Kısmi başarılı",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

const accountStatusLabels: Record<string, string> = {
  queued: "Bekliyor",
  running: "Taranıyor",
  succeeded: "Tamamlandı",
  failed: "Hata",
  skipped: "Atlandı",
};

const statusTones: Record<string, "accent" | "success" | "warning" | "danger" | "neutral"> = {
  queued: "neutral",
  running: "accent",
  completed: "success",
  partial_failed: "warning",
  failed: "danger",
  cancelled: "neutral",
};

/**
 * Manual scan control. The API answers 202 with a job id and the worker does
 * the provider calls, so this panel polls progress instead of blocking a
 * request. Polling stops as soon as the job reaches a terminal state.
 */
export function SyncPanel({
  onFinished,
  compact = false,
}: {
  onFinished?: () => void;
  compact?: boolean;
}) {
  const status = useApiQuery<SyncStatus>("/api/v1/sync/status");
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<SyncJobProgress | null>(null);
  const [starting, setStarting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const finishedRef = useRef<string | null>(null);

  // Adopt a job that is already running (page reload mid scan).
  useEffect(() => {
    if (status.data?.active_job_id && !jobId) {
      setJobId(status.data.active_job_id);
    }
  }, [status.data?.active_job_id, jobId]);

  const loadProgress = useCallback(async (id: string) => {
    try {
      const data = await api.get<SyncJobProgress>(`/api/v1/sync/jobs/${id}`);
      setProgress(data);
      return data;
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 404) {
        setJobId(null);
        setProgress(null);
      } else {
        setError(
          reason instanceof ApiError ? reason.message : "İlerleme alınamadı.",
        );
      }
      return null;
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      const data = await loadProgress(jobId!);
      if (cancelled) return;
      if (data && ACTIVE_STATUSES.has(data.job.status)) {
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } else if (data && finishedRef.current !== data.job.id) {
        finishedRef.current = data.job.id;
        status.refetch();
        onFinished?.();
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, loadProgress]);

  async function startScan() {
    setStarting(true);
    setError(null);
    setMessage(null);
    try {
      const response = await api.post<SyncRunResponse>("/api/v1/sync/run");
      setJobId(response.job_id);
      finishedRef.current = null;
      setMessage(response.message);
      await loadProgress(response.job_id);
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "Tarama başlatılamadı.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function cancelScan() {
    if (!jobId) return;
    try {
      const data = await api.post<SyncJobProgress>(`/api/v1/sync/jobs/${jobId}/cancel`);
      setProgress(data);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "İptal edilemedi.");
    }
  }

  const job = progress?.job ?? null;
  const running = job ? ACTIVE_STATUSES.has(job.status) : false;
  const queued = job?.status === "queued";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <RefreshCcw aria-hidden className="size-4" strokeWidth={1.75} />
            {job ? (kindLabels[job.kind] ?? "Manuel tarama") : "Manuel tarama"}
          </CardTitle>
          {job ? (
            <Badge variant={statusTones[job.status] ?? "neutral"}>
              {statusLabels[job.status] ?? job.status}
            </Badge>
          ) : null}
        </div>
        <CardDescription>
          {status.data?.last_sync_at
            ? `Son tarama: ${formatDateTime(status.data.last_sync_at)} (${formatRelative(status.data.last_sync_at)})`
            : "Henüz tarama yapılmadı."}
          {status.data?.scheduler_enabled && status.data?.next_auto_scan_at
            ? ` · Sonraki otomatik tarama: ${formatDateTime(status.data.next_auto_scan_at)}`
            : status.data?.scheduler_enabled
              ? " · Otomatik tarama kapalı (Tercihler'den açabilirsiniz)."
              : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={startScan} loading={starting} disabled={running}>
            <RefreshCcw aria-hidden className="size-4" strokeWidth={2} />
            Şimdi Tara
          </Button>
          {running ? (
            <Button variant="secondary" onClick={cancelScan}>
              <Square aria-hidden className="size-3.5" strokeWidth={2} />
              İptal et
            </Button>
          ) : null}
          {status.data?.connected_accounts === 0 ? (
            <span className="text-[12px] text-ink-subtle">
              Önce Entegrasyonlar ekranından bir hesap bağlayın.
            </span>
          ) : null}
        </div>

        {error ? (
          <div
            role="alert"
            className="rounded-[var(--radius-card)] bg-danger-soft px-3.5 py-2.5 text-[12.5px] leading-5 text-danger"
          >
            {error}
          </div>
        ) : null}

        {job ? (
          <div className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-surface-muted p-3.5">
            {job.kind === "scoring" ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric
                  label="Analiz"
                  value={`${job.progress.analyzed ?? 0}/${job.progress.total ?? 0}`}
                />
                <Metric
                  label="Bekleyen"
                  value={Math.max(
                    0,
                    (job.progress.total ?? 0) -
                      (job.progress.analyzed ?? 0) -
                      (job.progress.failed ?? 0) -
                      (job.progress.skipped ?? 0),
                  )}
                />
                <Metric
                  label="Başarısız"
                  value={job.progress.failed ?? 0}
                  tone={(job.progress.failed ?? 0) > 0 ? "danger" : undefined}
                />
                <Metric label="Atlanan" value={job.progress.skipped ?? 0} />
              </div>
            ) : job.kind === "notify" ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric label="Gönderilen" value={job.progress.sent ?? 0} tone="success" />
                <Metric
                  label="Başarısız"
                  value={job.progress.failed ?? 0}
                  tone={(job.progress.failed ?? 0) > 0 ? "danger" : undefined}
                />
                <Metric label="Atlanan" value={job.progress.skipped ?? 0} />
                <Metric label="Toplam" value={job.progress.total ?? 0} />
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric label="Hesap" value={`${job.accounts_processed}/${job.accounts_total}`} />
                <Metric label="Taranan mesaj" value={job.messages_scanned} />
                <Metric label="Yeni ilan" value={job.jobs_new} tone="success" />
                <Metric label="Tekrar" value={job.jobs_duplicate} />
                {!compact ? (
                  <>
                    <Metric label="Bulunan" value={job.jobs_found} />
                    <Metric label="Atlanan e-posta" value={job.messages_skipped} />
                    <Metric
                      label="Hata"
                      value={job.errors_count}
                      tone={job.errors_count ? "danger" : undefined}
                    />
                    <Metric
                      label="Deneme"
                      value={job.attempt}
                      hint={job.finished_at ? formatRelative(job.finished_at) : undefined}
                    />
                  </>
                ) : null}
              </div>
            )}

            {running ? (
              <p className="flex items-center gap-2 text-[12px] text-ink-subtle">
                <Loader2 aria-hidden className="size-3.5 animate-spin" strokeWidth={2} />
                {queued
                  ? "İş kuyrukta. İşçi süreci çalışmıyorsa: python -m app.worker"
                  : "Tarama sürüyor; ilerleme otomatik güncelleniyor."}
              </p>
            ) : null}

            {!compact && progress?.items.length ? (
              <ul className="flex flex-col gap-1.5">
                {progress.items.slice(0, 12).map((item) => (
                  <li
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow-card)]"
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-medium text-ink">
                        {item.job_title ?? "ilan"} · {item.company ?? ""}
                      </span>
                      {item.error_message ? (
                        <span className="text-danger">{item.error_message}</span>
                      ) : null}
                    </span>
                    <Badge
                      variant={
                        item.status === "succeeded"
                          ? "success"
                          : item.status === "failed"
                            ? "danger"
                            : item.status === "running"
                              ? "accent"
                              : "neutral"
                      }
                    >
                      {accountStatusLabels[item.status] ?? item.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : null}

            {!compact && progress?.accounts.length ? (
              <ul className="flex flex-col gap-1.5">
                {progress.accounts.map((account) => (
                  <li
                    key={account.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow-card)]"
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-medium text-ink">
                        {account.email_address ?? "hesap"}
                      </span>
                      {account.error_message ? (
                        <span className="text-danger">{account.error_message}</span>
                      ) : (
                        <span className="text-ink-subtle">
                          {account.messages_scanned} mesaj · {account.jobs_new} yeni ·{" "}
                          {account.jobs_duplicate} tekrar
                        </span>
                      )}
                    </span>
                    <Badge
                      variant={
                        account.status === "succeeded"
                          ? "success"
                          : account.status === "failed"
                            ? "danger"
                            : account.status === "running"
                              ? "accent"
                              : "neutral"
                      }
                    >
                      {accountStatusLabels[account.status] ?? account.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : null}

            {job.status === "partial_failed" ? (
              <p className="flex items-start gap-2 text-[12px] leading-5 text-warning">
                <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
                Bazı posta kutuları taranamadı; diğerleri tamamlandı. Hata veren
                hesapları Entegrasyonlar ekranından test edip yeniden bağlayabilirsiniz.
              </p>
            ) : null}
            {job.status === "completed" ? (
              <p className="flex items-center gap-2 text-[12px] text-success">
                <CheckCircle2 aria-hidden className="size-3.5" strokeWidth={2} />
                Tarama tamamlandı.
              </p>
            ) : null}
            {job.status === "cancelled" ? (
              <p className="text-[12px] text-ink-subtle">Tarama iptal edildi.</p>
            ) : null}
          </div>
        ) : message ? (
          <p className="text-[12px] leading-5 text-ink-subtle">{message}</p>
        ) : (
          <p className="flex items-center gap-2 text-[12px] leading-5 text-ink-subtle">
            <MailCheck aria-hidden className="size-3.5" strokeWidth={1.75} />
            Tarama kuyruğa alınır ve arka planda çalışır; bu ekran ilerlemeyi
            canlı gösterir.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "success" | "danger";
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] tracking-[0.02em] text-ink-subtle uppercase">
        {label}
      </span>
      <span
        className={cn(
          "tabular text-[15px] font-semibold",
          tone === "success" && "text-success",
          tone === "danger" && "text-danger",
          !tone && "text-ink",
        )}
      >
        {value}
      </span>
      {hint ? <span className="text-[11px] text-ink-subtle">{hint}</span> : null}
    </div>
  );
}
