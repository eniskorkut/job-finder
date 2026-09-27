"use client";

import { useState } from "react";
import { BellRing, History, Inbox } from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { Badge } from "@/components/ui/badge";
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
import { useApiQuery } from "@/lib/hooks";
import type { NotificationEntry, Page, SyncHistoryEntry } from "@/lib/types";

const statusTones: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  success: "success",
  failed: "danger",
  running: "warning",
  pending: "neutral",
  skipped: "neutral",
};

export function HistoryView() {
  const [tab, setTab] = useState<"sync" | "notifications">("sync");
  const [source, setSource] = useState("");

  const sync = useApiQuery<Page<SyncHistoryEntry>>("/api/v1/sync/history");
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
                  "inline-flex items-center gap-1.5 rounded-[var(--radius-control)] px-3 py-1.5 text-[12.5px] font-medium",
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

        {tab === "sync" ? (
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

      {tab === "sync" ? (
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
                  <TR className="hover:bg-transparent">
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
                <TR className="hover:bg-transparent">
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
