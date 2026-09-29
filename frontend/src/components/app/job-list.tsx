"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  MapPin,
  RefreshCw,
  SearchX,
  SlidersHorizontal,
  X,
} from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { Badge } from "@/components/ui/badge";
import { Button, buttonStyles } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/form";
import { ScoreBadge } from "@/components/ui/score";
import { SkeletonRows } from "@/components/ui/skeleton";
import { api, buildQuery, ApiError } from "@/lib/api";
import {
  formatRelative,
  statusLabels,
  workModeLabels,
  freshnessLabels,
  freshnessVariants,
  enrichmentLabels,
  enrichmentVariants,
  safeExternalUrl,
} from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { Job, JobFilterOptions, Page, RefreshJobResponse } from "@/lib/types";

interface Filters {
  search: string;
  company: string;
  workMode: string;
  status: string;
  minScore: string;
  maxScore: string;
  analysisStatus: string;
  notification: string;
  freshness: string;
  enrichment: string;
  sort: string;
}

const emptyFilters: Filters = {
  search: "",
  company: "",
  workMode: "",
  status: "",
  minScore: "",
  maxScore: "",
  analysisStatus: "",
  notification: "",
  freshness: "",
  enrichment: "",
  sort: "score",
};

const analysisLabels: Record<string, string> = {
  pending: "analiz bekliyor",
  running: "analiz sürüyor",
  completed: "analiz edildi",
  failed: "analiz başarısız",
  skipped: "analiz atlandı",
};

const statusVariants = {
  new: "accent",
  viewed: "neutral",
  saved: "success",
  dismissed: "muted",
  notified: "info",
} as const;

export function JobList({
  initialFilters = emptyFilters,
  pageSize = 8,
}: {
  initialFilters?: Filters;
  pageSize?: number;
}) {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [debouncedSearch, setDebouncedSearch] = useState(filters.search);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(filters.search), 300);
    return () => clearTimeout(timer);
  }, [filters.search]);

  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);

  const query = useMemo(
    () =>
      buildQuery({
        search: debouncedSearch,
        company: filters.company,
        work_mode: filters.workMode,
        status: filters.status,
        min_score: filters.minScore,
        max_score: filters.maxScore,
        analysis_status: filters.analysisStatus,
        notification: filters.notification,
        freshness_status: filters.freshness,
        enrichment_status: filters.enrichment,
        sort: filters.sort,
        page,
        page_size: pageSize,
      }),
    [
      debouncedSearch,
      filters.company,
      filters.workMode,
      filters.status,
      filters.minScore,
      filters.maxScore,
      filters.analysisStatus,
      filters.notification,
      filters.freshness,
      filters.enrichment,
      filters.sort,
      page,
      pageSize,
    ],
  );

  const jobs = useApiQuery<Page<Job>>(`/api/v1/jobs${query}`);
  const options = useApiQuery<JobFilterOptions>("/api/v1/jobs/filters");

  const activeFilterCount = [
    filters.search,
    filters.company,
    filters.workMode,
    filters.status,
    filters.minScore,
    filters.maxScore,
    filters.analysisStatus,
    filters.notification,
    filters.freshness,
  ].filter(Boolean).length;

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  }

  async function updateStatus(job: Job, status: "saved" | "dismissed") {
    try {
      await api.patch<Job>(`/api/v1/jobs/${job.id}`, { status });
      jobs.refetch();
    } catch {
      // Mutations surface their own state on the next fetch; keep the row.
    }
  }

  async function handleRefresh(jobId: string) {
    setRefreshingId(jobId);
    setRefreshNotice(null);
    try {
      const res = await api.post<RefreshJobResponse>(`/api/v1/jobs/${jobId}/refresh`);
      setRefreshNotice(res.message || "Tazeleme başlatıldı.");
      jobs.refetch();
    } catch (err) {
      setRefreshNotice(
        err instanceof ApiError ? err.message : "Tazeleme başlatılamadı.",
      );
    } finally {
      setRefreshingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-3">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-[12px] font-medium text-ink-subtle">
            <SlidersHorizontal aria-hidden className="size-3.5" strokeWidth={2} />
            Filtreler
            {activeFilterCount > 0 ? (
              <button
                type="button"
                onClick={() => {
                  setFilters(emptyFilters);
                  setPage(1);
                }}
                className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-accent-ink"
              >
                <X aria-hidden className="size-3" strokeWidth={2} />
                Temizle ({activeFilterCount})
              </button>
            ) : null}
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <Input
              type="search"
              value={filters.search}
              onChange={(event) => update("search", event.target.value)}
              placeholder="Başlık, şirket veya açıklama ara…"
              aria-label="İlan ara"
            />
            <Select
              value={filters.company}
              onChange={(event) => update("company", event.target.value)}
              aria-label="Şirket"
            >
              <option value="">Tüm şirketler</option>
              {(options.data?.companies ?? []).map((company) => (
                <option key={company} value={company}>
                  {company}
                </option>
              ))}
            </Select>
            <Select
              value={filters.workMode}
              onChange={(event) => update("workMode", event.target.value)}
              aria-label="Çalışma modeli"
            >
              <option value="">Tüm çalışma modelleri</option>
              <option value="remote">Uzaktan</option>
              <option value="hybrid">Hibrit</option>
              <option value="onsite">Ofis</option>
            </Select>
            <Select
              value={filters.status}
              onChange={(event) => update("status", event.target.value)}
              aria-label="Durum"
            >
              <option value="">Tüm durumlar</option>
              {Object.entries(statusLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Select
              value={filters.minScore}
              onChange={(event) => update("minScore", event.target.value)}
              aria-label="Minimum eşleşme puanı"
            >
              <option value="">Minimum puan yok</option>
              {[50, 60, 70, 80, 90].map((value) => (
                <option key={value} value={value}>
                  {value}+ puan
                </option>
              ))}
            </Select>
            <Select
              value={filters.maxScore}
              onChange={(event) => update("maxScore", event.target.value)}
              aria-label="Maksimum eşleşme puanı"
            >
              <option value="">Maksimum puan yok</option>
              {[50, 60, 70, 80, 90].map((value) => (
                <option key={value} value={value}>
                  {value} ve altı
                </option>
              ))}
            </Select>
            <Select
              value={filters.analysisStatus}
              onChange={(event) => update("analysisStatus", event.target.value)}
              aria-label="Analiz durumu"
            >
              <option value="">Tüm analiz durumları</option>
              <option value="pending">Analiz bekliyor</option>
              <option value="running">Analiz sürüyor</option>
              <option value="completed">Analiz edildi</option>
              <option value="failed">Analiz başarısız</option>
            </Select>
            <Select
              value={filters.notification}
              onChange={(event) => update("notification", event.target.value)}
              aria-label="Bildirim durumu"
            >
              <option value="">Tüm bildirim durumları</option>
              <option value="sent">Bildirildi</option>
              <option value="pending">Bildirilmedi</option>
            </Select>
            <Select
              value={filters.freshness}
              onChange={(event) => update("freshness", event.target.value)}
              aria-label="Tazelik durumu"
            >
              <option value="">Tüm tazelik durumları</option>
              <option value="fresh">Taze (0-3 gün)</option>
              <option value="aging">Güncel (4-7 gün)</option>
              <option value="stale">Eski (8-14 gün)</option>
              <option value="expired">Süresi doldu (&gt;14 gün)</option>
            </Select>
            <Select
              value={filters.enrichment}
              onChange={(event) => update("enrichment", event.target.value)}
              aria-label="Zenginleştirme durumu"
            >
              <option value="">Tüm zenginleştirme durumları</option>
              <option value="enriched">Zenginleştirilmiş olanlar</option>
              <option value="pending">Zenginleştirme bekleyenler</option>
              <option value="skipped">Atlananlar (Yeterli açıklama)</option>
              <option value="not_found">Kaynak bulunamayanlar</option>
              <option value="failed">Hata verenler</option>
            </Select>
            <Select
              value={filters.sort}
              onChange={(event) => update("sort", event.target.value)}
              aria-label="Sıralama"
            >
              <option value="recent">Keşfe göre (en yeni)</option>
              <option value="posted_at">Yayın tarihine göre</option>
              <option value="freshness">Tazelik durumuna göre</option>
              <option value="score">Puan (yüksek → düşük)</option>
              <option value="score_asc">Puan (düşük → yüksek)</option>
              <option value="confidence">Güven (yüksek → düşük)</option>
              <option value="company">Şirket (A → Z)</option>
              <option value="title">Başlık (A → Z)</option>
              <option value="oldest">En eski</option>
            </Select>
          </div>
        </div>
      </Card>

      {refreshNotice ? (
        <div className="flex items-center justify-between rounded-[var(--radius-card)] bg-accent-soft px-3.5 py-2 text-[12.5px] text-accent-ink">
          <span>{refreshNotice}</span>
          <button
            type="button"
            onClick={() => setRefreshNotice(null)}
            className="ml-2 text-accent-ink hover:opacity-75"
          >
            <X aria-hidden className="size-3.5" strokeWidth={2} />
          </button>
        </div>
      ) : null}

      {jobs.loading ? (
        <SkeletonRows rows={4} />
      ) : jobs.error ? (
        <Card>
          <ErrorState error={jobs.error} onRetry={jobs.refetch} />
        </Card>
      ) : !jobs.data || jobs.data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={activeFilterCount > 0 ? SearchX : BriefcaseBusiness}
            title={
              activeFilterCount > 0
                ? "Bu filtrelerle ilan bulunamadı"
                : "Henüz ilan yok"
            }
            description={
              activeFilterCount > 0
                ? "Filtreleri gevşetip tekrar deneyin."
                : "Örnek verileri yüklemek için: python -m app.cli seed"
            }
            action={
              activeFilterCount > 0 ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setFilters(emptyFilters);
                    setPage(1);
                  }}
                >
                  Filtreleri temizle
                </Button>
              ) : null
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          <ul className="stagger flex flex-col gap-2.5">
            {jobs.data.items.map((job) => (
              <li key={job.id}>
                <Card className="p-4 transition-[box-shadow] duration-150 ease-out pointer-hover:shadow-[var(--shadow-card-hover)]">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-col gap-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          href={`/jobs/${job.id}`}
                          className="truncate text-[15px] font-semibold text-ink transition-[color] duration-150 ease-out pointer-hover:text-accent-ink"
                        >
                          {job.title}
                        </Link>
                        {job.is_mock ? (
                          <Badge variant="info">Örnek veri</Badge>
                        ) : null}
                        {job.freshness_status ? (
                          <Badge
                            variant={
                              freshnessVariants[job.freshness_status] ?? "neutral"
                            }
                          >
                            {freshnessLabels[job.freshness_status] ?? job.freshness_status}
                          </Badge>
                        ) : null}
                        {job.availability_status === "closed" ? (
                          <Badge variant="danger">Kapanmış</Badge>
                        ) : null}
                        {job.enrichment_status === "enriched" ? (
                          <Badge variant="accent">Zenginleştirildi</Badge>
                        ) : null}
                        {job.match ? (
                          <Badge
                            variant={
                              statusVariants[
                                job.match.status as keyof typeof statusVariants
                              ] ?? "neutral"
                            }
                          >
                            {statusLabels[job.match.status] ?? job.match.status}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-muted">
                        <span className="font-medium">{job.company}</span>
                        {job.location ? (
                          <span className="inline-flex items-center gap-1">
                            <MapPin aria-hidden className="size-3.5" strokeWidth={1.5} />
                            {job.location}
                          </span>
                        ) : null}
                        <span>{workModeLabels[job.work_mode] ?? job.work_mode}</span>
                        <span title={job.discovered_at}>
                          {formatRelative(job.discovered_at)}
                        </span>
                        {job.match?.confidence !== null && job.match?.confidence !== undefined ? (
                          <span className="text-ink-subtle">
                            güven %{job.match.confidence}
                          </span>
                        ) : null}
                        {job.match?.notified_at ? (
                          <Badge variant="info">bildirildi</Badge>
                        ) : null}
                      </div>

                      {(() => {
                        const safeLi = safeExternalUrl(job.linkedin_url);
                        const safeApp = safeExternalUrl(
                          job.canonical_url || job.application_url || job.company_job_url,
                        );
                        if (!safeLi && !safeApp) return null;
                        return (
                          <div className="mt-1 flex flex-wrap items-center gap-3 pt-1 border-t border-line/30">
                            {safeLi ? (
                              <a
                                href={safeLi}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-[12px] font-medium text-accent-ink underline-offset-2 pointer-hover:underline"
                              >
                                <ExternalLink aria-hidden className="size-3" strokeWidth={2} />
                                LinkedIn&apos;de Aç
                              </a>
                            ) : null}
                            {safeApp ? (
                              <a
                                href={safeApp}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-[12px] font-medium text-accent-ink underline-offset-2 pointer-hover:underline"
                              >
                                <ExternalLink aria-hidden className="size-3" strokeWidth={2} />
                                Başvuru / Kaynak
                              </a>
                            ) : null}
                          </div>
                        );
                      })()}
                    </div>

                    <div className="flex items-center gap-2">
                      {!job.is_mock &&
                      job.match?.analysis_status &&
                      job.match.analysis_status !== "completed" ? (
                        <Badge
                          variant={
                            job.match.analysis_status === "failed"
                              ? "danger"
                              : job.match.analysis_status === "running"
                                ? "accent"
                                : "muted"
                          }
                        >
                          {analysisLabels[job.match.analysis_status] ?? job.match.analysis_status}
                        </Badge>
                      ) : null}
                      <ScoreBadge score={job.match?.score ?? null} />
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={refreshingId === job.id}
                        onClick={() => handleRefresh(job.id)}
                        title="Web araması ve keşif ile ilanı tazele"
                      >
                        <RefreshCw aria-hidden className="size-3.5" strokeWidth={1.75} />
                        Tazele
                      </Button>
                      {job.match?.status === "dismissed" ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => updateStatus(job, "saved")}
                        >
                          Geri al
                        </Button>
                      ) : (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => updateStatus(job, "dismissed")}
                        >
                          Ele
                        </Button>
                      )}
                      <Link
                        href={`/jobs/${job.id}`}
                        className={buttonStyles({ size: "sm" })}
                      >
                        Detay
                      </Link>
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ul>

          <div className="flex items-center justify-between gap-3 pt-1">
            <p className="tabular text-[12.5px] text-ink-subtle">
              {jobs.data.total} ilandan{" "}
              {(jobs.data.page - 1) * jobs.data.page_size + 1}–
              {Math.min(jobs.data.page * jobs.data.page_size, jobs.data.total)}{" "}
              arası
            </p>
            <div className="flex items-center gap-1.5">
              <Button
                variant="secondary"
                size="sm"
                disabled={jobs.data.page <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                <ChevronLeft aria-hidden className="size-3.5" strokeWidth={2} />
                Önceki
              </Button>
              <span className="tabular px-1 text-[12.5px] text-ink-muted">
                {jobs.data.page} / {jobs.data.pages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={jobs.data.page >= jobs.data.pages}
                onClick={() => setPage((value) => value + 1)}
              >
                Sonraki
                <ChevronRight aria-hidden className="size-3.5" strokeWidth={2} />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
