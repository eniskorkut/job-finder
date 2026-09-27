"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  Building2,
  CalendarClock,
  CircleDollarSign,
  ExternalLink,
  MapPin,
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
} from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { JobDetail } from "@/lib/types";

export function JobDetailView({ jobId }: { jobId: string }) {
  const job = useApiQuery<JobDetail>(`/api/v1/jobs/${jobId}`);
  const [status, setStatus] = useState<string | null>(null);
  const [savingStatus, setSavingStatus] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

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
      {actionError ? (
        <div
          role="alert"
          className="rounded-[var(--radius-card)] bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger"
        >
          {actionError}
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <Card className="p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg leading-6 font-semibold text-ink">
              {data.title}
            </h1>
            {data.is_mock ? <Badge variant="info">Örnek veri</Badge> : null}
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
              <ScoreBar score={data.match?.score ?? null} />

              {data.match?.rationale ? (
                <p className="text-[13px] leading-5 text-ink-muted">
                  {data.match.rationale}
                </p>
              ) : (
                <p className="text-[13px] text-ink-subtle">
                  Bu ilan için eşleşme gerekçesi yok.
                </p>
              )}

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
              <Row
                label="E-posta hesabı"
                value={data.mail_account_email ?? "Taranmadı (örnek veri)"}
              />
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
