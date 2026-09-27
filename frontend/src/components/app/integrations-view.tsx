"use client";

import { useState } from "react";
import {
  Bot,
  Cable,
  CircleDot,
  Mail,
  Plug,
  Send,
  ServerCog,
  Trash2,
} from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { connectionStatusLabels, formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { Integration, IntegrationsResponse } from "@/lib/types";

const providerIcons = {
  gmail: Mail,
  outlook: Mail,
  telegram: Send,
} as const;

const statusTones: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  connected: "success",
  pending: "warning",
  needs_reauth: "warning",
  error: "danger",
  disconnected: "neutral",
};

export function IntegrationsView() {
  const integrations = useApiQuery<IntegrationsResponse>("/api/v1/integrations");
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingProvider, setPendingProvider] = useState<string | null>(null);

  async function connect(provider: string) {
    setPendingProvider(provider);
    setActionError(null);
    try {
      await api.post(`/api/v1/integrations/${provider}/connect`);
      // Unreachable in phase 1: the API answers 501.
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? `${error.message}${error.isNotImplemented ? " Aşama 2/3 tamamlanınca buradan bağlanabileceksiniz." : ""}`
          : "Bağlantı başlatılamadı.",
      );
    } finally {
      setPendingProvider(null);
    }
  }

  async function removeAccount(provider: string, accountId: string) {
    setActionError(null);
    try {
      await api.delete(`/api/v1/integrations/${provider}/accounts/${accountId}`);
      integrations.refetch();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Kayıt kaldırılamadı.",
      );
    }
  }

  if (integrations.loading) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {[0, 1, 2].map((index) => (
          <Card key={index} className="p-5">
            <div className="flex flex-col gap-3">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-9 w-28" />
            </div>
          </Card>
        ))}
      </div>
    );
  }

  if (integrations.error) {
    return (
      <Card>
        <ErrorState
          error={integrations.error}
          onRetry={integrations.refetch}
        />
      </Card>
    );
  }

  if (!integrations.data) return null;
  const { integrations: items, deepseek } = integrations.data;

  return (
    <div className="flex flex-col gap-5">
      {actionError ? (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-[var(--radius-card)] bg-warning-soft px-3.5 py-3 text-[13px] leading-5 text-warning"
        >
          <Cable aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={2} />
          <p>{actionError}</p>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((integration) => (
          <IntegrationCard
            key={integration.provider}
            integration={integration}
            pending={pendingProvider === integration.provider}
            onConnect={() => connect(integration.provider)}
            onRemoveAccount={(accountId) =>
              removeAccount(integration.provider, accountId)
            }
          />
        ))}

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <ServerCog aria-hidden className="size-4" strokeWidth={1.75} />
                DeepSeek (ortak)
              </CardTitle>
              <Badge variant={deepseek.configured ? "warning" : "neutral"}>
                3. aşama
              </Badge>
            </div>
            <CardDescription>{deepseek.note}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[12.5px]">
              <dt className="text-ink-subtle">Model</dt>
              <dd className="font-medium text-ink">{deepseek.model}</dd>
              <dt className="text-ink-subtle">Base URL</dt>
              <dd className="truncate font-mono text-[12px] text-ink">
                {deepseek.base_url}
              </dd>
              <dt className="text-ink-subtle">API anahtarı</dt>
              <dd className="font-medium text-ink">
                {deepseek.configured ? "tanımlı" : "tanımlı değil"}
              </dd>
              <dt className="text-ink-subtle">Kullanım</dt>
              <dd className="font-medium text-ink">
                Tüm kullanıcılar için ortak
              </dd>
            </dl>
            <p className="text-[12px] leading-4 text-ink-subtle">
              Anahtarı backend/.env.local içine DEEPSEEK_API_KEY olarak ekleyin.
              Skorlama 3. aşamada açılacak; şu an hiçbir dış istek yapılmıyor.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function IntegrationCard({
  integration,
  pending,
  onConnect,
  onRemoveAccount,
}: {
  integration: Integration;
  pending: boolean;
  onConnect: () => void;
  onRemoveAccount: (accountId: string) => void;
}) {
  const Icon = providerIcons[integration.provider] ?? CircleDot;
  const tone = statusTones[integration.status] ?? "neutral";

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Icon aria-hidden className="size-4" strokeWidth={1.75} />
            {integration.label}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={tone}>
              {connectionStatusLabels[integration.status] ?? integration.status}
            </Badge>
            <Badge variant="muted">
              {integration.phase === "phase-2" ? "2. aşama" : "3. aşama"}
            </Badge>
          </div>
        </div>
        <CardDescription>{integration.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-3">
        {integration.accounts.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {integration.accounts.map((account) => (
              <li
                key={account.id}
                className="flex items-center justify-between gap-3 rounded-[var(--radius-control)] bg-surface-muted px-3 py-2.5"
              >
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-[12.5px] font-medium text-ink">
                    {account.email_address}
                  </span>
                  <span className="text-[11.5px] text-ink-subtle">
                    {account.display_name ?? "hesap"} ·{" "}
                    {connectionStatusLabels[account.status] ?? account.status}
                    {account.last_synced_at
                      ? ` · son tarama ${formatDateTime(account.last_synced_at)}`
                      : " · hiç taranmadı"}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`${account.email_address} kaydını kaldır`}
                  title="Kaydı kaldır"
                  className="text-ink-muted pointer-hover:text-danger"
                  onClick={() => onRemoveAccount(account.id)}
                >
                  <Trash2 aria-hidden className="size-4" strokeWidth={1.5} />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12.5px] text-ink-subtle">
            Bu sağlayıcı için tanımlı hesap yok.{" "}
            {integration.provider === "gmail"
              ? "Gmail"
              : integration.provider === "outlook"
                ? "Hotmail/Outlook"
                : "Telegram"}{" "}
            hesabınızı 2. ve 3. aşamada bağlayabileceksiniz.
          </p>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
          <Button
            variant="secondary"
            size="sm"
            loading={pending}
            onClick={onConnect}
            className={cn(!integration.available && "opacity-80")}
          >
            <Plug aria-hidden className="size-3.5" strokeWidth={2} />
            {integration.provider === "telegram" ? "Bağla" : "Bağlan"}
          </Button>
          {integration.unavailable_reason ? (
            <span className="text-[11.5px] leading-4 text-ink-subtle">
              {integration.unavailable_reason}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function IntegrationsEmptyState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-6 text-[13px] text-ink-muted">
        <Bot aria-hidden className="size-4" strokeWidth={1.75} />
        Henüz entegrasyon tanımı yok.
      </CardContent>
    </Card>
  );
}
