"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  Building2,
  CalendarClock,
  CircleDollarSign,
  ExternalLink,
  Globe,
  Info,
  MapPin,
  RefreshCcw,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { MockNotice } from "@/components/app/mock-notice";
import { Badge } from "@/components/ui/badge";
import { Button, buttonStyles } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreBar, ScoreBadge } from "@/components/ui/score";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  sourceLabels,
  statusLabels,
  workModeLabels,
  freshnessLabels,
  freshnessVariants,
  availabilityLabels,
  availabilityVariants,
  enrichmentLabels,
  enrichmentVariants,
  sourceTypeLabels,
} from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type {
  DimensionStatus,
  JobDetail,
  ReanalyzeResponse,
  RefreshJobResponse,
} from "@/lib/types";

const dimensionLabels: Record<string, string> = {
  experience: "Deneyim",
  title: "Pozisyon",
  location: "Lokasyon",
  work_mode: "Çalışma biçimi",
};

const dimensionTones: Record<DimensionStatus, "success" | "warning" | "danger" | "muted"> = {
  match: "success",
  partial: "warning",
  mismatch: "danger",
  unknown: "muted",
};

const dimensionText: Record<DimensionStatus, string> = {
  match: "uyumlu",
  partial: "kısmen",
  mismatch: "uyumsuz",
  unknown: "bilinmiyor",
};

export function JobDetailView({ jobId }: { jobId: string }) {
  const job = useApiQuery<JobDetail>(`/api/v1/jobs/${jobId}`);
  const [status, setStatus] = useState<string | null>(null);
  const [savingStatus, setSavingStatus] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [analysisMessage, setAnalysisMessage] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  async function reanalyze() {
    setAnalyzing(true);
    setAnalysisMessage(null);
    setRefreshMessage(null);
    setActionError(null);
    try {
      const response = await api.post<ReanalyzeResponse>(`/api/v1/jobs/${jobId}/reanalyze`);
      setAnalysisMessage(
        `${response.message} İlerlemeyi Tarama Geçmişi ekranından izleyebilirsiniz.`,
      );
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Analiz başlatılamadı.",
      );
    } finally {
      setAnalyzing(false);
    }
  }

  async function refreshJob() {
    setRefreshing(true);
    setRefreshMessage(null);
    setAnalysisMessage(null);
    setActionError(null);
    try {
      const response = await api.post<RefreshJobResponse>(`/api/v1/jobs/${jobId}/refresh`);
      setRefreshMessage(
        `${response.message} İlerlemeyi Tarama Geçmişi ekranından izleyebilirsiniz.`,
      );
      job.refetch();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Tazeleme başlatılamadı.",
      );
    } finally {
      setRefreshing(false);
    }
  }

  async function changeStatus(next: "saved" | "dismissed" | "viewed") {
    setSavingStatus(true);
    setActionError(null);
    try {
      const updated = await api.patch<JobDetail>(`/api/v1/jobs/${jobId}`, {
        status: next,
      });
      setStatus(updated.match?.status ?? next);
      job.setData({ ...job.data!, match: updated.match });
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Durum güncellenemedi.",
      );
    } finally {
      setSavingStatus(false);
    }
  }

  if (job.loading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-6 w-40" />
        <Card className="p-5">
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        </Card>
      </div>
    );
  }

  if (job.error) {
    return (
      <Card>
        <ErrorState
          error={job.error}
          onRetry={job.refetch}
          title="İlan yüklenemedi"
        />
      </Card>
    );
  }

  if (!job.data) return null;
  const data = job.data;
  const currentStatus = status ?? data.match?.status ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/jobs"
          className={buttonStyles({ variant: "ghost", size: "sm" })}
        >
          <ArrowLeft aria-hidden className="size-3.5" strokeWidth={2} />
          İlanlara dön
        </Link>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            loading={refreshing}
            onClick={refreshJob}
            title="Web araması ve keşif ile ilanı tazele"
          >
            <RefreshCw aria-hidden className="size-3.5" strokeWidth={2} />
            Tazele (Keşif & Zenginleştir)
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={analyzing}
            onClick={reanalyze}
            title="CV ile yeniden değerlendir"
          >
            <RefreshCcw aria-hidden className="size-3.5" strokeWidth={2} />
            Tekrar değerlendir
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={savingStatus}
            onClick={() => changeStatus("saved")}
            disabled={currentStatus === "saved"}
          >
            Kaydet
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={savingStatus}
            onClick={() => changeStatus("dismissed")}
            disabled={currentStatus === "dismissed"}
          >
            Ele
          </Button>
        </div>
      </div>

      {data.is_mock ? <MockNotice /> : null}
      {refreshMessage ? (
        <div className="rounded-[var(--radius-card)] bg-accent-soft px-3.5 py-2.5 text-[12.5px] leading-5 text-accent-ink">
          {refreshMessage}
        </div>
      ) : null}
      {analysisMessage ? (
        <div className="rounded-[var(--radius-card)] bg-success-soft px-3.5 py-2.5 text-[12.5px] leading-5 text-success">
          {analysisMessage}
        </div>
      ) : null}
      {actionError ? (
        <div
          role="alert"
          className="rounded-[var(--radius-card)] bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger"
        >
          {actionError}
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="flex flex-col gap-5">
          <Card className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg leading-6 font-semibold text-ink">
                {data.title}
              </h1>
              {data.is_mock ? <Badge variant="info">Örnek veri</Badge> : null}
              {data.freshness_status ? (
                <Badge
                  variant={
                    freshnessVariants[data.freshness_status] ?? "neutral"
                  }
                >
                  {freshnessLabels[data.freshness_status] ?? data.freshness_status}
                </Badge>
              ) : null}
              {data.availability_status ? (
                <Badge
                  variant={
                    availabilityVariants[data.availability_status] ?? "neutral"
                  }
                >
                  {availabilityLabels[data.availability_status] ?? data.availability_status}
                </Badge>
              ) : null}
              {data.enrichment_status === "enriched" ? (
                <Badge variant="accent">Zenginleştirildi</Badge>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px] text-ink-muted">
              <span className="inline-flex items-center gap-1.5">
                <Building2 aria-hidden className="size-4" strokeWidth={1.5} />
                {data.company}
              </span>
              {data.location ? (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin aria-hidden className="size-4" strokeWidth={1.5} />
                  {data.location}
                </span>
              ) : null}
              <Badge>{workModeLabels[data.work_mode] ?? data.work_mode}</Badge>
              {data.seniority ? <Badge>{data.seniority}</Badge> : null}
              {data.employment_type ? <Badge>{data.employment_type}</Badge> : null}
            </div>

            {/* Prominent external link action buttons */}
            {(data.linkedin_url || data.canonical_url || data.application_url || data.company_job_url) ? (
              <div className="mt-4 flex flex-wrap items-center gap-2.5">
                {data.linkedin_url ? (
                  <a
                    href={data.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonStyles({ variant: "secondary", size: "sm" })}
                  >
                    LinkedIn&apos;de Aç
                    <ExternalLink aria-hidden className="size-3.5" strokeWidth={2} />
                  </a>
                ) : null}
                {(data.canonical_url || data.application_url || data.company_job_url) ? (
                  <a
                    href={data.canonical_url || data.application_url || data.company_job_url!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonStyles({ size: "sm" })}
                  >
                    Resmi İlan / Başvuru Sayfası
                    <ExternalLink aria-hidden className="size-3.5" strokeWidth={2} />
                  </a>
                ) : null}
              </div>
            ) : null}

            {data.salary_text ? (
              <p className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-ink">
                <CircleDollarSign aria-hidden className="size-4" strokeWidth={1.5} />
                {data.salary_text}
              </p>
            ) : null}

            <div className="mt-5 border-t border-line pt-5">
              <h2 className="mb-2 text-[13px] font-semibold text-ink">
                İlan detayı
              </h2>
              <p className="text-[13.5px] leading-6 whitespace-pre-line text-ink-muted">
                {data.description ?? "Bu ilan için açıklama bulunmuyor."}
              </p>
            </div>

            {data.url ? (
              <div className="mt-5 border-t border-line pt-4">
                <a
                  href={data.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 text-[13px] font-medium text-accent-ink underline-offset-4 pointer-hover:underline"
                >
                  İlan kaynağını aç
                  <ExternalLink aria-hidden className="size-3.5" strokeWidth={2} />
                </a>
                {data.is_mock ? (
                  <p className="mt-1 text-[11.5px] text-ink-subtle">
                    Örnek veri olduğu için bu bağlantı gerçek bir ilana gitmez.
                  </p>
                ) : null}
              </div>
            ) : null}
          </Card>

          {/* Web Sources Provenance Section */}
          {data.web_sources && data.web_sources.length > 0 ? (
            <Card className="p-5">
              <CardHeader className="p-0 pb-4">
                <CardTitle className="flex items-center justify-between text-base font-semibold">
                  <span className="flex items-center gap-2">
                    <Globe aria-hidden className="size-4 text-accent-ink" strokeWidth={2} />
                    Keşfedilen Web Kaynakları ({data.web_sources.length})
                  </span>
                  <span className="text-[12px] font-normal text-ink-subtle">
                    Doğrulama ve kaynak izi
                  </span>
                </CardTitle>
              </CardHeader>
              <div className="flex flex-col gap-3">
                {data.web_sources.map((source) => (
                  <div
                    key={source.id}
                    className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface-muted/30 p-3.5 text-[12.5px]"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-ink">{source.host}</span>
                        <Badge variant="neutral">
                          {sourceTypeLabels[source.source_type] ?? source.source_type}
                        </Badge>
                        {source.selected_as_canonical ? (
                          <Badge variant="success">✓ Kanonik Kaynak</Badge>
                        ) : null}
                        {source.http_status ? (
                          <span className="tabular text-[11.5px] text-ink-subtle">
                            HTTP {source.http_status}
                          </span>
                        ) : null}
                      </div>
                      <div className="flex items-center gap-2.5">
                        <span className="text-[12px] text-ink-subtle">
                          Güven:{" "}
                          <strong className="font-medium text-ink">
                            {source.trust_level}/10
                          </strong>
                        </span>
                        <span className="text-[12px] text-ink-subtle">
                          Eşleşme:{" "}
                          <strong className="font-medium text-ink">
                            {source.match_confidence}
                          </strong>
                        </span>
                      </div>
                    </div>

                    {source.title ? (
                      <p className="font-medium text-ink line-clamp-1">{source.title}</p>
                    ) : null}

                    {source.snippet ? (
                      <p className="line-clamp-2 text-ink-muted">{source.snippet}</p>
                    ) : null}

                    <div className="mt-1 flex flex-wrap items-center justify-between gap-2 border-t border-line/40 pt-1.5">
                      <span className="text-[11.5px] text-ink-subtle">
                        Keşif: {formatDateTime(source.discovered_at)}
                      </span>
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-medium text-accent-ink underline-offset-2 pointer-hover:underline"
                      >
                        Kaynağa Git
                        <ExternalLink aria-hidden className="size-3" strokeWidth={2} />
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle>Eşleşme</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <ScoreBadge score={data.match?.score ?? null} />
                <span className="text-[12px] text-ink-subtle">
                  {data.match?.model === "mock-fixture"
                    ? "örnek skor"
                    : (data.match?.model ?? "skorlanmadı")}
                </span>
              </div>
              {data.match?.confidence !== null && data.match?.confidence !== undefined ? (
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-ink-subtle">Güven</span>
                  <span className="tabular font-medium text-ink">
                    %{data.match.confidence}
                  </span>
                </div>
              ) : null}
              <ScoreBar score={data.match?.score ?? null} />

              {data.match?.analysis_status && data.match.analysis_status !== "completed" ? (
                <p className="text-[12.5px] leading-5 text-ink-subtle">
                  Durum:{" "}
                  <strong className="font-medium">
                    {data.match.analysis_status === "failed"
                      ? "analiz başarısız"
                      : data.match.analysis_status === "running"
                        ? "analiz sürüyor"
                        : "analiz bekliyor"}
                  </strong>
                  {data.match.analysis_error ? ` — ${data.match.analysis_error}` : ""}
                </p>
              ) : null}

              {data.match?.rationale ? (
                <p className="text-[13px] leading-5 text-ink-muted">
                  {data.match.rationale}
                </p>
              ) : (
                <p className="text-[13px] text-ink-subtle">
                  Bu ilan için eşleşme gerekçesi yok.
                </p>
              )}

              {data.match?.match_details &&
              Object.keys(data.match.match_details).length > 0 ? (
                <div className="flex flex-col gap-2">
                  {(["title", "experience", "location", "work_mode"] as const).map((key) => {
                    const dimension = data.match?.match_details?.[key];
                    if (!dimension) return null;
                    return (
                      <div key={key} className="flex items-start justify-between gap-3">
                        <span className="text-[12px] text-ink-subtle">
                          {dimensionLabels[key]}
                        </span>
                        <span className="flex max-w-[70%] flex-col items-end gap-0.5 text-right">
                          <Badge variant={dimensionTones[dimension.status]}>
                            {dimensionText[dimension.status]}
                          </Badge>
                          {dimension.reason ? (
                            <span className="text-[11.5px] leading-4 text-ink-muted">
                              {dimension.reason}
                            </span>
                          ) : null}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {data.match?.insufficient_information ? (
                <p className="flex items-start gap-2 rounded-[var(--radius-control)] bg-warning-soft px-3 py-2 text-[11.5px] leading-4 text-warning">
                  <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
                  İlan metni kısıtlı olduğu için değerlendirme sınırlı; güven puanı
                  düşük tutuldu.
                </p>
              ) : null}

              {data.match?.analysis_status === "completed" ? (
                <p className="flex items-start gap-2 text-[11.5px] leading-4 text-ink-subtle">
                  <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.75} />
                  Bu puan işe alınma ihtimali değildir; CV ile ilan gereksinimleri
                  arasındaki uyumu gösterir.
                </p>
              ) : null}

              {data.match?.matched_skills?.length ? (
                <div className="flex flex-col gap-1.5">
                  <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-ink-subtle">
                    <Sparkles aria-hidden className="size-3.5" strokeWidth={2} />
                    Örtüşen yetkinlikler
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {data.match.matched_skills.map((skill) => (
                      <Badge key={skill} variant="success">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              {data.match?.missing_skills?.length ? (
                <div className="flex flex-col gap-1.5">
                  <span className="text-[12px] font-medium text-ink-subtle">
                    Eksik görünen yetkinlikler
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {data.match.missing_skills.map((skill) => (
                      <Badge key={skill} variant="warning">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Kayıt bilgisi</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2.5 text-[12.5px] text-ink-muted">
              <Row
                icon={<CalendarClock aria-hidden className="size-3.5" strokeWidth={1.5} />}
                label="Bulunma"
                value={formatDateTime(data.discovered_at)}
              />
              <Row
                icon={<CalendarClock aria-hidden className="size-3.5" strokeWidth={1.5} />}
                label="Yayınlanma"
                value={formatDate(data.posted_at)}
              />
              <Row label="Kaynak" value={sourceLabels[data.source] ?? data.source} />
              <Row
                label="Durum"
                value={statusLabels[currentStatus ?? ""] ?? "—"}
              />
              {data.freshness_status ? (
                <Row
                  label="Tazelik"
                  value={freshnessLabels[data.freshness_status] ?? data.freshness_status}
                />
              ) : null}
              {data.availability_status ? (
                <Row
                  label="İlan yayında mı?"
                  value={availabilityLabels[data.availability_status] ?? data.availability_status}
                />
              ) : null}
              {data.enrichment_status ? (
                <Row
                  label="Zenginleştirme"
                  value={enrichmentLabels[data.enrichment_status] ?? data.enrichment_status}
                />
              ) : null}
              {data.posted_at_source ? (
                <Row label="Tarih kaynağı" value={data.posted_at_source} />
              ) : null}
              {data.posted_at_confidence ? (
                <Row label="Tarih güveni" value={data.posted_at_confidence} />
              ) : null}
              {data.email_received_at ? (
                <Row
                  label="E-posta geliş zamanı"
                  value={formatDateTime(data.email_received_at)}
                />
              ) : null}
              {data.valid_through ? (
                <Row
                  label="Son geçerlilik"
                  value={formatDate(data.valid_through)}
                />
              ) : null}
              {data.last_verified_at ? (
                <Row
                  label="Son doğrulama"
                  value={formatDateTime(data.last_verified_at)}
                />
              ) : null}
              {data.last_enriched_at ? (
                <Row
                  label="Son zenginleştirme"
                  value={formatDateTime(data.last_enriched_at)}
                />
              ) : null}
              <Row
                label="E-posta hesabı"
                value={data.mail_account_email ?? "Taranmadı (örnek veri)"}
              />
              {data.analysis_cv ? (
                <>
                  <Row label="Kullanılan CV" value={data.analysis_cv.filename ?? "—"} />
                  <Row
                    label="CV sürümü"
                    value={data.analysis_cv.checksum?.slice(0, 12) ?? "—"}
                  />
                  <Row label="Model" value={data.analysis_cv.model ?? "—"} />
                  <Row
                    label="Analiz zamanı"
                    value={formatDateTime(data.analysis_cv.analyzed_at)}
                  />
                  <Row
                    label="Prompt sürümü"
                    value={data.analysis_cv.prompt_version ?? "—"}
                  />
                </>
              ) : null}
              {data.sources.length > 0 ? (
                <Row
                  label="Kaynak iletiler"
                  value={data.sources
                    .map((source) => source.account_email ?? source.provider)
                    .join(", ")}
                />
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="inline-flex items-center gap-1.5 text-ink-subtle">
        {icon}
        {label}
      </span>
      <span className="text-right font-medium text-ink">{value}</span>
    </div>
  );
}
