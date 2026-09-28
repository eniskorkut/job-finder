"use client";

import { useState } from "react";
import { BellRing, History, Inbox, ListChecks } from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { SkeletonRows } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import {
  formatDateTime,
  formatRelative,
  sourceLabels,
  syncStatusLabels,
} from "@/lib/format";
import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/hooks";
import type {
  NotificationEntry,
  Page,
  SyncHistoryEntry,
  SyncJob,
  SyncJobProgress,
} from "@/lib/types";

const statusTones: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  success: "success",
  failed: "danger",
  running: "warning",
  pending: "neutral",
  skipped: "neutral",
};

const kindLabels: Record<string, string> = {
  mail_scan: "Posta taraması",
  scoring: "CV analizi",
  notify: "Telegram bildirimi",
};

const jobStatusLabels: Record<string, string> = {
  queued: "Kuyrukta",
  running: "Sürüyor",
  completed: "Tamamlandı",
  partial_failed: "Kısmi başarılı",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

const jobTones: Record<string, "success" | "danger" | "warning" | "neutral" | "accent"> = {
  queued: "neutral",
  running: "accent",
  completed: "success",
  partial_failed: "warning",
  failed: "danger",
  cancelled: "neutral",
};

export function HistoryView() {
  const [tab, setTab] = useState<"jobs" | "sync" | "notifications">("jobs");
  const [source, setSource] = useState("");
  const [selectedJob, setSelectedJob] = useState<SyncJobProgress | null>(null);

  const jobs = useApiQuery<Page<SyncJob>>(
    tab === "jobs" ? "/api/v1/sync/jobs" : null,
  );
  const sync = useApiQuery<Page<SyncHistoryEntry>>(
    tab === "sync" ? "/api/v1/sync/history" : null,
  );
  const notifications = useApiQuery<Page<NotificationEntry>>(
    tab === "notifications" ? "/api/v1/notifications" : null,
  );

  const syncItems = (sync.data?.items ?? []).filter(
    (item) => !source || item.source === source,
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="Kayıt türü"
          className="inline-flex rounded-[var(--radius-card)] bg-surface-muted p-1"
        >
          {[
            { value: "jobs" as const, label: "Tarama işleri", icon: ListChecks },
            { value: "sync" as const, label: "Tarama geçmişi", icon: History },
            { value: "notifications" as const, label: "Bildirimler", icon: BellRing },
          ].map((item) => {
            const active = tab === item.value;
            const Icon = item.icon;
            return (
              <button
                key={item.value}
                type="button"
                aria-pressed={active}
                onClick={() => setTab(item.value)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-[12px] px-3 py-1.5 text-[12.5px] font-medium",
                  "transition-[background-color,color,scale] duration-150 ease-out active:scale-[0.96]",
                  active
                    ? "bg-surface text-ink shadow-[var(--shadow-card)]"
                    : "text-ink-muted pointer-hover:text-ink",
                )}
              >
                <Icon
                  aria-hidden
                  className="size-3.5"
                  strokeWidth={active ? 2 : 1.5}
                />
                {item.label}
              </button>
            );
          })}
        </div>

        {tab === "jobs" ? (
        jobs.loading ? (
          <SkeletonRows rows={3} />
        ) : jobs.error ? (
          <Card>
            <ErrorState error={jobs.error} onRetry={jobs.refetch} />
          </Card>
        ) : !jobs.data || jobs.data.items.length === 0 ? (
          <Card>
            <EmptyState
              icon={ListChecks}
              title="Henüz tarama işi yok"
              description="Paneldeki 'Şimdi Tara' düğmesiyle kalıcı bir tarama işi kuyruğa alın."
            />
          </Card>
        ) : (
          <Card>
            <CardContent className="pt-4">
              <Table>
                <THead>
                  <TR className="pointer-hover:bg-transparent">
                    <TH>İstek</TH>
                    <TH>Tür</TH>
                    <TH>Durum</TH>
                    <TH className="text-right">Hesap</TH>
                    <TH className="text-right">Mesaj</TH>
                    <TH className="text-right">Yeni</TH>
                    <TH className="text-right">Tekrar</TH>
                    <TH className="text-right">Hata</TH>
                    <TH />
                  </TR>
                </THead>
                <tbody>
                  {jobs.data.items.map((job) => (
                    <TR key={job.id}>
                      <TD className="text-[12.5px]">
                        {formatDateTime(job.requested_at)}
                        <span className="block text-[11px] text-ink-subtle">
                          {formatRelative(job.requested_at)}
                        </span>
                      </TD>
                      <TD>
                        <Badge variant="muted">{kindLabels[job.kind] ?? job.kind}</Badge>
                      </TD>
                      <TD>
                        <Badge variant={jobTones[job.status] ?? "neutral"}>
                          {jobStatusLabels[job.status] ?? job.status}
                        </Badge>
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.accounts_processed}/{job.accounts_total}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.messages_scanned}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">{job.jobs_new}</TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.jobs_duplicate}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.errors_count}
                      </TD>
                      <TD className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={async () => {
                            const data = await api.get<SyncJobProgress>(
                              `/api/v1/sync/jobs/${job.id}`,
                            );
                            setSelectedJob(data);
                          }}
                        >
                          Ayrıntı
                        </Button>
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>

              {selectedJob ? (
                <div className="mt-4 flex flex-col gap-2 rounded-[var(--radius-card)] bg-surface-muted p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12.5px] font-medium text-ink">
                      İş ayrıntısı · {selectedJob.job.id.slice(0, 8)}
                    </span>
                    <Button variant="ghost" size="sm" onClick={() => setSelectedJob(null)}>
                      Kapat
                    </Button>
                  </div>
                  {selectedJob.items?.length
                    ? selectedJob.items.map((item) => (
                        <div
                          key={item.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow-card)]"
                        >
                          <span className="flex min-w-0 flex-col">
                            <span className="truncate font-medium text-ink">
                              {item.job_title ?? "ilan"}
                              {item.company ? ` · ${item.company}` : ""}
                            </span>
                            {item.error_message ? (
                              <span className="text-danger">{item.error_message}</span>
                            ) : (
                              <span className="text-ink-subtle">deneme: {item.attempt}</span>
                            )}
                          </span>
                          <Badge
                            variant={
                              item.status === "succeeded"
                                ? "success"
                                : item.status === "failed"
                                  ? "danger"
                                  : "neutral"
                            }
                          >
                            {item.status}
                          </Badge>
                        </div>
                      ))
                    : null}
                  {selectedJob.accounts.map((account) => (
                    <div
                      key={account.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow-card)]"
                    >
                      <span className="flex flex-col">
                        <span className="font-medium text-ink">
                          {account.email_address ?? "hesap"}
                        </span>
                        <span className="text-ink-subtle">
                          {account.messages_scanned} mesaj · {account.jobs_new} yeni ·{" "}
                          {account.jobs_duplicate} tekrar · {account.messages_skipped}{" "}
                          atlandı
                        </span>
                        {account.error_message ? (
                          <span className="text-danger">{account.error_message}</span>
                        ) : null}
                      </span>
                      <Badge
                        variant={
                          account.status === "succeeded"
                            ? "success"
                            : account.status === "failed"
                              ? "danger"
                              : "neutral"
                        }
                      >
                        {account.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        )
      ) : tab === "sync" ? (
          <Select
            value={source}
            onChange={(event) => setSource(event.target.value)}
            aria-label="Kaynak filtresi"
            className="w-44"
          >
            <option value="">Tüm kaynaklar</option>
            <option value="gmail">Gmail</option>
            <option value="outlook">Hotmail / Outlook</option>
            <option value="mock">Örnek veri</option>
          </Select>
        ) : null}
      </div>

      {tab === "jobs" ? (
        jobs.loading ? (
          <SkeletonRows rows={3} />
        ) : jobs.error ? (
          <Card>
            <ErrorState error={jobs.error} onRetry={jobs.refetch} />
          </Card>
        ) : !jobs.data || jobs.data.items.length === 0 ? (
          <Card>
            <EmptyState
              icon={ListChecks}
              title="Henüz tarama işi yok"
              description="Paneldeki 'Şimdi Tara' düğmesiyle kalıcı bir tarama işi kuyruğa alın."
            />
          </Card>
        ) : (
          <Card>
            <CardContent className="pt-4">
              <Table>
                <THead>
                  <TR className="pointer-hover:bg-transparent">
                    <TH>İstek</TH>
                    <TH>Tür</TH>
                    <TH>Durum</TH>
                    <TH className="text-right">Hesap</TH>
                    <TH className="text-right">Mesaj</TH>
                    <TH className="text-right">Yeni</TH>
                    <TH className="text-right">Tekrar</TH>
                    <TH className="text-right">Hata</TH>
                    <TH />
                  </TR>
                </THead>
                <tbody>
                  {jobs.data.items.map((job) => (
                    <TR key={job.id}>
                      <TD className="text-[12.5px]">
                        {formatDateTime(job.requested_at)}
                        <span className="block text-[11px] text-ink-subtle">
                          {formatRelative(job.requested_at)}
                        </span>
                      </TD>
                      <TD>
                        <Badge variant="muted">{kindLabels[job.kind] ?? job.kind}</Badge>
                      </TD>
                      <TD>
                        <Badge variant={jobTones[job.status] ?? "neutral"}>
                          {jobStatusLabels[job.status] ?? job.status}
                        </Badge>
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.accounts_processed}/{job.accounts_total}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.messages_scanned}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">{job.jobs_new}</TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.jobs_duplicate}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {job.errors_count}
                      </TD>
                      <TD className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={async () => {
                            const data = await api.get<SyncJobProgress>(
                              `/api/v1/sync/jobs/${job.id}`,
                            );
                            setSelectedJob(data);
                          }}
                        >
                          Ayrıntı
                        </Button>
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>

              {selectedJob ? (
                <div className="mt-4 flex flex-col gap-2 rounded-[var(--radius-card)] bg-surface-muted p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12.5px] font-medium text-ink">
                      İş ayrıntısı · {selectedJob.job.id.slice(0, 8)}
                    </span>
                    <Button variant="ghost" size="sm" onClick={() => setSelectedJob(null)}>
                      Kapat
                    </Button>
                  </div>
                  {selectedJob.items?.length
                    ? selectedJob.items.map((item) => (
                        <div
                          key={item.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow-card)]"
                        >
                          <span className="flex min-w-0 flex-col">
                            <span className="truncate font-medium text-ink">
                              {item.job_title ?? "ilan"}
                              {item.company ? ` · ${item.company}` : ""}
                            </span>
                            {item.error_message ? (
                              <span className="text-danger">{item.error_message}</span>
                            ) : (
                              <span className="text-ink-subtle">deneme: {item.attempt}</span>
                            )}
                          </span>
                          <Badge
                            variant={
                              item.status === "succeeded"
                                ? "success"
                                : item.status === "failed"
                                  ? "danger"
                                  : "neutral"
                            }
                          >
                            {item.status}
                          </Badge>
                        </div>
                      ))
                    : null}
                  {selectedJob.accounts.map((account) => (
                    <div
                      key={account.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow-card)]"
                    >
                      <span className="flex flex-col">
                        <span className="font-medium text-ink">
                          {account.email_address ?? "hesap"}
                        </span>
                        <span className="text-ink-subtle">
                          {account.messages_scanned} mesaj · {account.jobs_new} yeni ·{" "}
                          {account.jobs_duplicate} tekrar · {account.messages_skipped}{" "}
                          atlandı
                        </span>
                        {account.error_message ? (
                          <span className="text-danger">{account.error_message}</span>
                        ) : null}
                      </span>
                      <Badge
                        variant={
                          account.status === "succeeded"
                            ? "success"
                            : account.status === "failed"
                              ? "danger"
                              : "neutral"
                        }
                      >
                        {account.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        )
      ) : tab === "sync" ? (
        sync.loading ? (
          <SkeletonRows rows={3} />
        ) : sync.error ? (
          <Card>
            <ErrorState error={sync.error} onRetry={sync.refetch} />
          </Card>
        ) : syncItems.length === 0 ? (
          <Card>
            <EmptyState
              icon={History}
              title="Tarama kaydı yok"
              description="Otomatik tarama 2. ve 3. aşamada açılacak. Örnek veri için: python -m app.cli seed"
            />
          </Card>
        ) : (
          <Card>
            <CardContent className="pt-4">
              <Table>
                <THead>
                  <TR className="pointer-hover:bg-transparent">
                    <TH>Tarih</TH>
                    <TH>Kaynak</TH>
                    <TH>Hesap</TH>
                    <TH className="text-right">Bulunan</TH>
                    <TH className="text-right">Yeni</TH>
                    <TH className="text-right">Eşleşme</TH>
                    <TH>Durum</TH>
                  </TR>
                </THead>
                <tbody>
                  {syncItems.map((item) => (
                    <TR key={item.id}>
                      <TD>
                        <span className="flex flex-col">
                          <span className="text-[12.5px] font-medium text-ink">
                            {formatDateTime(item.started_at)}
                          </span>
                          <span className="text-[11.5px] text-ink-subtle">
                            {formatRelative(item.started_at)}
                          </span>
                        </span>
                      </TD>
                      <TD>
                        <span className="inline-flex items-center gap-2">
                          <span className="text-[12.5px]">
                            {sourceLabels[item.source] ?? item.source}
                          </span>
                          {item.is_mock ? <Badge variant="info">Örnek</Badge> : null}
                        </span>
                      </TD>
                      <TD className="text-[12.5px] text-ink-muted">
                        {item.account_email ?? "—"}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {item.jobs_found}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {item.jobs_new}
                      </TD>
                      <TD className="tabular text-right text-[12.5px]">
                        {item.matches_created}
                      </TD>
                      <TD>
                        <Badge variant={statusTones[item.status] ?? "neutral"}>
                          {syncStatusLabels[item.status] ?? item.status}
                        </Badge>
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>
        )
      ) : notifications.loading ? (
        <SkeletonRows rows={2} />
      ) : notifications.error ? (
        <Card>
          <ErrorState error={notifications.error} onRetry={notifications.refetch} />
        </Card>
      ) : !notifications.data || notifications.data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={Inbox}
            title="Henüz bildirim gönderilmedi"
            description="Telegram bildirimleri 3. aşamada açılacak. Gönderim olmadan bu listeye kayıt düşmez."
          />
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-4">
            <Table>
              <THead>
                <TR className="pointer-hover:bg-transparent">
                  <TH>Tarih</TH>
                  <TH>Kanal</TH>
                  <TH>İlan</TH>
                  <TH>Durum</TH>
                  <TH>Mesaj</TH>
                </TR>
              </THead>
              <tbody>
                {notifications.data.items.map((item) => (
                  <TR key={item.id}>
                    <TD className="text-[12.5px]">{formatDateTime(item.created_at)}</TD>
                    <TD className="text-[12.5px] capitalize">{item.channel}</TD>
                    <TD className="text-[12.5px]">
                      {item.job_title ?? "—"}
                      {item.company ? (
                        <span className="text-ink-subtle"> · {item.company}</span>
                      ) : null}
                    </TD>
                    <TD>
                      <Badge variant={statusTones[item.status] ?? "neutral"}>
                        {syncStatusLabels[item.status] ?? item.status}
                      </Badge>
                    </TD>
                    <TD className="max-w-md text-[12px] leading-5 text-ink-muted">
                      {item.message ?? item.error_message ?? "—"}
                      {item.is_mock ? (
                        <span className="ms-1 text-ink-subtle">(örnek kayıt)</span>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
