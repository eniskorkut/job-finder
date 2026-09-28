"use client";

import { useState } from "react";
import { Loader2, RefreshCcw, Sparkles, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { Overview, ReanalyzeResponse } from "@/lib/types";

/**
 * Analysis status + the "re-evaluate with the current CV" action.
 *
 * The action only queues a durable scoring job (202) - the worker does the LLM
 * calls with bounded concurrency.
 */
export function AnalysisPanel({
  onQueued,
  compact = false,
}: {
  onQueued?: () => void;
  compact?: boolean;
}) {
  const overview = useApiQuery<Overview>("/api/v1/me/overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const data = overview.data;
  const llmConfigured = data?.llm?.configured !== false;
  const hasCv = data?.has_active_cv ?? false;
  const pending = data?.pending_analysis ?? 0;
  const failed = data?.failed_analysis ?? 0;

  async function reanalyze(payload: { days?: number; force?: boolean }, key: string) {
    setBusy(key);
    setMessage(null);
    setError(null);
    try {
      const response = await api.post<ReanalyzeResponse>("/api/v1/jobs/reanalyze", payload);
      setMessage(`${response.total} ilan analiz kuyruğuna alındı.`);
      overview.refetch();
      onQueued?.();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Analiz başlatılamadı.");
    } finally {
      setBusy(null);
    }
  }

  const stats = [
    { label: "Analiz edildi", value: data?.analyzed_jobs ?? 0, tone: "text-ink" },
    { label: "Bekliyor", value: pending, tone: pending ? "text-warning" : "text-ink" },
    { label: "Başarısız", value: failed, tone: failed ? "text-danger" : "text-ink" },
    { label: "Bildirildi", value: data?.notified_jobs ?? 0, tone: "text-success" },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Sparkles aria-hidden className="size-4" strokeWidth={1.75} />
            CV eşleştirme
          </CardTitle>
          <Badge variant={llmConfigured ? "success" : "warning"}>
            {llmConfigured ? (data?.llm?.model ?? "LLM hazır") : "LLM yapılandırılmadı"}
          </Badge>
        </div>
        <CardDescription>
          Puan, CV ile ilan gereksinimlerinin uyum derecesidir; işe alınma
          olasılığı değildir. Örnek (mock) kayıtlar analiz edilmez.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((item) => (
            <div key={item.label} className="flex flex-col gap-0.5">
              <span className="text-[11px] tracking-[0.02em] text-ink-subtle uppercase">
                {item.label}
              </span>
              <span className={cn("tabular text-[17px] font-semibold", item.tone)}>
                {item.value}
              </span>
            </div>
          ))}
        </div>

        {!compact ? (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[11.5px] text-ink-subtle">
            <span>
              Ortalama score:{" "}
              <strong className="tabular font-medium text-ink">
                {data?.average_score ?? "—"}
              </strong>
            </span>
            <span>
              Son manuel tarama: {data?.last_manual_scan_at ? formatDateTime(data.last_manual_scan_at) : "—"}
            </span>
            <span>
              Son otomatik tarama: {data?.last_auto_scan_at ? formatDateTime(data.last_auto_scan_at) : "—"}
            </span>
            <span>
              Sonraki otomatik tarama:{" "}
              {data?.auto_scan_enabled && data?.next_auto_scan_at
                ? formatDateTime(data.next_auto_scan_at)
                : "kapalı"}
            </span>
          </div>
        ) : null}

        {!hasCv ? (
          <p className="flex items-start gap-2 rounded-[var(--radius-card)] bg-warning-soft px-3.5 py-2.5 text-[12px] leading-5 text-warning">
            <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
            Analiz için önce CV ve Tercihler ekranından metni çıkarılabilen bir CV
            yükleyin.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={() => reanalyze({ days: 30 }, "recent")}
            loading={busy === "recent"}
            disabled={!hasCv || !llmConfigured}
          >
            <RefreshCcw aria-hidden className="size-3.5" strokeWidth={2} />
            Yeni CV ile son 30 günü değerlendir
          </Button>
          {(pending > 0 || failed > 0) ? (
            <Button
              variant="secondary"
              onClick={() => reanalyze({ days: 365, force: false }, "pending")}
              loading={busy === "pending"}
              disabled={!hasCv || !llmConfigured}
            >
              Bekleyen {pending + failed} ilanı analiz et
            </Button>
          ) : null}
        </div>

        {busy ? (
          <p className="flex items-center gap-2 text-[12px] text-ink-subtle">
            <Loader2 aria-hidden className="size-3.5 animate-spin" strokeWidth={2} />
            Analiz kuyruğa alınıyor…
          </p>
        ) : null}
        {message ? (
          <p className="rounded-[var(--radius-card)] bg-success-soft px-3.5 py-2.5 text-[12px] text-success">
            {message}
          </p>
        ) : null}
        {error ? (
          <p className="rounded-[var(--radius-card)] bg-warning-soft px-3.5 py-2.5 text-[12px] leading-5 text-warning">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
