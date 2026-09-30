"use client";

import { useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  HelpCircle,
  Info,
  KeyRound,
  Lock,
  Mail,
  Plug,
  RefreshCw,
  Save,
  Search,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Unplug,
} from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { TelegramCard } from "@/components/app/telegram-card";
import { TransientAlert } from "@/components/app/transient-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { connectionStatusLabels, formatDateTime, formatRelative } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type {
  AccountTestResponse,
  ConnectResponse,
  Integration,
  IntegrationsResponse,
  MailAccount,
  OAuthClientConfig,
} from "@/lib/types";

const providerLabels: Record<string, string> = {
  gmail: "Gmail",
  outlook: "Hotmail / Outlook",
  telegram: "Telegram",
};

const statusTones: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  connected: "success",
  pending: "warning",
  needs_reauth: "warning",
  error: "danger",
  disconnected: "neutral",
};

type Feedback = { tone: "success" | "warning" | "danger"; message: string };

export function IntegrationsView() {
  const integrations = useApiQuery<IntegrationsResponse>("/api/v1/integrations");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  // OAuth callbacks land here with ?oauth=success|error&reason=...
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauth = params.get("oauth");
    if (!oauth) return;
    const reason = params.get("reason") ?? "";
    const detail = params.get("detail") ?? "";
    const account = params.get("account") ?? "";
    const provider = params.get("provider") ?? "";

    if (oauth === "success") {
      setFeedback({
        tone: "success",
        message: `${providerLabels[provider] ?? provider} hesabı bağlandı: ${account}`,
      });
    } else {
      const explanations: Record<string, string> = {
        state_missing: "Yetkilendirme yanıtı eksik geldi; akışı yeniden başlatın.",
        session_missing: "Oturum bulunamadı; yeniden giriş yapıp tekrar deneyin.",
        forbidden: "Bu yetkilendirme başka bir oturuma ait; akışı yeniden başlatın.",
        validation_error: "Sağlayıcı isteği reddetti.",
        provider_error: "Sağlayıcı beklenmeyen bir hata döndürdü.",
      };
      setFeedback({
        tone: "danger",
        message:
          detail ||
          explanations[reason] ||
          "Bağlantı tamamlanamadı. Ayrıntı için sunucu günlüğüne bakın.",
      });
    }

    const url = new URL(window.location.href);
    ["oauth", "reason", "detail", "account", "created", "provider"].forEach((key) =>
      url.searchParams.delete(key),
    );
    window.history.replaceState({}, "", url.toString());
    integrations.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connect(provider: string, accountId?: string) {
    setBusyProvider(provider);
    setFeedback(null);
    try {
      const path = accountId
        ? `/api/v1/integrations/accounts/${accountId}/reconnect`
        : `/api/v1/integrations/${provider}/connect`;
      const response = await api.post<ConnectResponse>(path);
      // Full page navigation: the provider needs the real redirect flow.
      window.location.assign(response.authorization_url);
    } catch (reason) {
      setFeedback({
        tone: reason instanceof ApiError && reason.isNotImplemented ? "warning" : "danger",
        message:
          reason instanceof ApiError ? reason.message : "Bağlantı başlatılamadı.",
      });
      setBusyProvider(null);
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
        <ErrorState error={integrations.error} onRetry={integrations.refetch} />
      </Card>
    );
  }

  if (!integrations.data) return null;
  const { integrations: items, deepseek, web_search } = integrations.data;
  const mailProviders = items.filter((item) => item.category === "mail");
  const telegram = items.find((item) => item.provider === "telegram");

  return (
    <div className="flex flex-col gap-8">
      {feedback ? (
        <TransientAlert tone={feedback.tone} title="Bağlantı durumu" duration={8000}>
          {feedback.message}
        </TransientAlert>
      ) : null}

      {/* TOP SECURITY CALLOUT BANNER */}
      <SecurityBanner />

      {/* GROUP A: KİŞİSEL BAĞLANTILAR */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="text-[17px] font-semibold tracking-tight text-ink">
              Kişisel Bağlantılar
            </h2>
            <Badge variant="muted">Kullanıcıya özel</Badge>
          </div>
          <p className="text-[12.5px] leading-5 text-ink-subtle">
            LinkedIn Job Alert e-postalarınızı okumak için posta kutularınızı ve anlık iş eşleşmesi
            uyarıları için kişisel Telegram botunuzu bağlayın.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {mailProviders.map((integration) => (
            <MailProviderCard
              key={integration.provider}
              integration={integration}
              busy={busyProvider === integration.provider}
              onConnect={(accountId) => connect(integration.provider, accountId)}
              onFeedback={setFeedback}
              onRefresh={integrations.refetch}
            />
          ))}

          {telegram ? <TelegramCard onChanged={integrations.refetch} /> : null}
        </div>
      </section>

      {/* GROUP B: SUNUCU TARAFINDAN YÖNETİLEN SERVİSLER */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="text-[17px] font-semibold tracking-tight text-ink">
              Sunucu Tarafından Yönetilen Servisler
            </h2>
            <Badge variant="neutral">Merkezi altyapı</Badge>
          </div>
          <p className="text-[12.5px] leading-5 text-ink-subtle">
            Bu servisler tüm kullanıcılar için Job Finder arka plan altyapısı tarafından merkezi olarak
            çalıştırılır. Kişisel API anahtarı girilmesi gerekmez.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {/* DeepSeek / OpenCode Go LLM Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2">
                  <ServerCog aria-hidden className="size-4" strokeWidth={1.75} />
                  {deepseek.label ?? "DeepSeek / OpenAI-uyumlu LLM"}
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant={deepseek.configured ? "success" : "warning"}>
                    {deepseek.configured ? "yapılandırıldı" : "yapılandırılmadı"}
                  </Badge>
                  <Badge variant="muted">sunucu tarafından yönetilir</Badge>
                </div>
              </div>
              <CardDescription>{deepseek.note}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-[12.5px]">
              <Row label="Model" value={deepseek.model ?? "—"} />
              <Row label="Endpoint" value={deepseek.endpoint_host ?? "—"} mono />
              <Row label="Yol" value={deepseek.endpoint_path ?? "—"} mono />
              <Row label="Prompt sürümü" value={deepseek.prompt_version ?? "—"} />
              <Row
                label="Eşzamanlılık"
                value={deepseek.max_concurrency ? `en fazla ${deepseek.max_concurrency} istek` : "—"}
              />
              <Row label="Kullanım" value="Tüm kullanıcılar için ortak (sunucu anahtarı)" />
              {!deepseek.configured ? (
                <p className="rounded-[var(--radius-card)] bg-warning-soft px-3 py-2 text-[11.5px] leading-4 text-warning">
                  LLM yapılandırılmadı: backend/.env.local içinde DEEPSEEK_API_KEY,
                  DEEPSEEK_BASE_URL ve DEEPSEEK_MODEL tanımlanmalı.
                </p>
              ) : null}
              <p className="text-[11.5px] leading-4 text-ink-subtle">
                Anahtar yalnızca backend/.env.local içinde tutulur; panelden
                girilmez ve hiçbir zaman tarayıcıya gönderilmez.
              </p>
            </CardContent>
          </Card>

          {/* SearXNG Web Search Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2">
                  <Search aria-hidden className="size-4" strokeWidth={1.75} />
                  {web_search?.label ?? "SearXNG Web Araması (İş Keşfi & Zenginleştirme)"}
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant={web_search?.configured ? "success" : "neutral"}>
                    {web_search?.status === "running" ? "çalışıyor" : "yerel servis"}
                  </Badge>
                  <Badge variant="muted">sunucu tarafından yönetilir</Badge>
                </div>
              </div>
              <CardDescription>
                {web_search?.description ??
                  "Kısa iş ilanlarının resmi şirket / ATS sayfalarından tam metnini ve tazelik bilgisini bulmak için kullanılır."}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-[12.5px]">
              <Row label="Sağlayıcı" value={web_search?.provider ?? "searxng"} />
              <Row label="Servis Adresi" value={web_search?.url ?? "http://localhost:8080"} mono />
              <Row
                label="Eşzamanlılık"
                value={web_search?.max_concurrency ? `en fazla ${web_search.max_concurrency} istek` : "en fazla 2 istek"}
              />
              <Row label="Mod" value="Konteyner içi güvenli arama (SafeWebFetcher)" />
              <Row label="Kullanım" value="Tüm kullanıcılar için ortak (harici anahtar gerekmez)" />
              <p className="text-[11.5px] leading-4 text-ink-subtle">
                SearXNG yerel Docker konteyneri olarak sunucu tarafından yönetilir.
                Aramalarda kullanıcı kimliği paylaşılmaz; ticari motorlara doğrudan istek atılmaz.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}

// ----------------------------------------------------------------------
function SecurityBanner() {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-border/80 bg-surface-muted/60 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent-ink">
            <ShieldCheck className="size-4" strokeWidth={2.2} />
          </div>
          <div>
            <h3 className="text-[13.5px] font-semibold text-ink">
              Bağlantılarınız ve Verileriniz Nasıl Korunuyor?
            </h3>
            <p className="text-[11.5px] text-ink-subtle">
              Job Finder, kimlik bilgilerinizi saklarken en yüksek güvenlik standartlarını uygular.
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setOpen((prev) => !prev)}
          className="text-[12px] text-ink-muted hover:text-ink"
        >
          {open ? "Daha az bilgi" : "Güvenlik ayrıntıları"}
          <ChevronDown
            aria-hidden
            className={cn("ml-1 size-3.5 transition-transform duration-150", open && "rotate-180")}
          />
        </Button>
      </div>

      {open ? (
        <div className="grid gap-3 pt-3 border-t border-border/60 sm:grid-cols-2 lg:grid-cols-4">
          <div className="flex flex-col gap-1 rounded-[var(--radius-control)] bg-surface p-3 shadow-xs">
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink">
              <Lock className="size-3.5 text-accent" />
              Parola Paylaşımı Yok
            </div>
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              Yetkilendirme resmi Google ve Microsoft giriş ekranlarında yapılır. Şifreniz asla Job Finder sunucularına iletilmez.
            </p>
          </div>

          <div className="flex flex-col gap-1 rounded-[var(--radius-control)] bg-surface p-3 shadow-xs">
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink">
              <ShieldCheck className="size-3.5 text-accent" />
              Yalnızca Okuma İzni
            </div>
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              Yalnızca iş ilanlarını okuma izni (read-only) talep edilir. Posta silme veya gönderme yetkisi kesinlikle istenmez.
            </p>
          </div>

          <div className="flex flex-col gap-1 rounded-[var(--radius-control)] bg-surface p-3 shadow-xs">
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink">
              <KeyRound className="size-3.5 text-accent" />
              Güçlü AES Şifreleme
            </div>
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              Client Secret ve Bot Token değerleri veritabanında APP_ENCRYPTION_KEY ile şifreli tutulur ve tarayıcıya açık gönderilmez.
            </p>
          </div>

          <div className="flex flex-col gap-1 rounded-[var(--radius-control)] bg-surface p-3 shadow-xs">
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink">
              <Sparkles className="size-3.5 text-accent" />
              Kullanıcı İzolasyonu
            </div>
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              Tanımladığınız OAuth istemcileri ve bağlı e-posta hesapları tamamen hesabınıza özeldir; kullanıcılar arası veri izolasyonu vardır.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ----------------------------------------------------------------------
function MailProviderCard({
  integration,
  busy,
  onConnect,
  onFeedback,
  onRefresh,
}: {
  integration: Integration;
  busy: boolean;
  onConnect: (accountId?: string) => void;
  onFeedback: (feedback: Feedback | null) => void;
  onRefresh: () => void;
}) {
  const config = integration.oauth_client;
  const [editing, setEditing] = useState(false);
  const Icon = Mail;

  const hasConnectedAccount = integration.accounts.some(
    (a) => a.status === "connected",
  );

  return (
    <Card className="flex flex-col" data-testid={`integration-card-${integration.provider}`}>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Icon aria-hidden className="size-4" strokeWidth={1.75} />
            {integration.label}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={statusTones[integration.status] ?? "neutral"}>
              {connectionStatusLabels[integration.status] ?? integration.status}
            </Badge>
            {config?.configured ? (
              <Badge variant="success">istemci kayıtlı</Badge>
            ) : (
              <Badge variant="warning">istemci bekliyor</Badge>
            )}
            {hasConnectedAccount ? (
              <Badge variant="success">hesap bağlı</Badge>
            ) : null}
          </div>
        </div>
        <CardDescription>{integration.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        {config ? (
          <SetupPanel
            config={config}
            editing={editing || !config.configured}
            onEditingChange={setEditing}
            onSaved={() => {
              setEditing(false);
              onFeedback({
                tone: "success",
                message: `${integration.label} istemci bilgileri kaydedildi.`,
              });
              onRefresh();
            }}
            onDeleted={() => {
              onFeedback({
                tone: "warning",
                message: `${integration.label} istemci bilgileri silindi; hesaplar yeniden yetkilendirme bekliyor.`,
              });
              onRefresh();
            }}
            onError={(message) => onFeedback({ tone: "danger", message })}
          />
        ) : null}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button
            variant="secondary"
            loading={busy}
            disabled={!config?.configured}
            onClick={() => onConnect()}
          >
            <Plug aria-hidden className="size-3.5" strokeWidth={2} />
            <span>{integration.label} ile bağlan</span>
          </Button>
          <span className="text-[11.5px] leading-4 text-ink-subtle">
            {config?.configured
              ? `${integration.label} hesabınızı yetkilendirin (parola istenmez).`
              : "Önce istemci bilgilerini kaydedin."}
          </span>
        </div>

        {integration.accounts.length ? (
          <ul className="flex flex-col gap-2">
            {integration.accounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                onConnect={() => onConnect(account.id)}
                onFeedback={onFeedback}
                onRefresh={onRefresh}
              />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Mail}
            title="Bağlı hesap yok"
            description="İstemci bilgilerini kaydedip bağlanın. Aynı uygulamayla birden fazla posta kutusu ekleyebilirsiniz."
            className="py-6"
          />
        )}
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------------
function SetupPanel({
  config,
  editing,
  onEditingChange,
  onSaved,
  onDeleted,
  onError,
}: {
  config: OAuthClientConfig;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  onSaved: () => void;
  onDeleted: () => void;
  onError: (message: string) => void;
}) {
  const [showGuide, setShowGuide] = useState(!config.configured);
  const [showFaq, setShowFaq] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [clientId, setClientId] = useState(config.client_id ?? "");
  const [clientSecret, setClientSecret] = useState("");
  const [tenant, setTenant] = useState(config.tenant ?? "consumers");
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [infoField, setInfoField] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    try {
      await api.put(`/api/v1/integrations/${config.provider}/client`, {
        client_id: clientId,
        client_secret: clientSecret || undefined,
        tenant: config.provider === "outlook" ? tenant : undefined,
      });
      setClientSecret("");
      onSaved();
    } catch (reason) {
      onError(reason instanceof ApiError ? reason.message : "Kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    try {
      await api.delete(`/api/v1/integrations/${config.provider}/client`);
      setClientId("");
      setClientSecret("");
      onDeleted();
    } catch (reason) {
      onError(reason instanceof ApiError ? reason.message : "Silinemedi.");
    }
  }

  async function copyRedirect() {
    try {
      await navigator.clipboard.writeText(config.redirect_uri);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      onError("Adres panoya kopyalanamadı.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-surface-muted p-3.5">
      {/* GUIDE TOGGLE HEADER */}
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setShowGuide((value) => !value)}
          className="flex flex-1 items-center justify-between text-left hover:opacity-90"
          aria-expanded={showGuide}
        >
          <span className="flex items-center gap-2 text-[12.5px] font-medium text-ink">
            <ShieldCheck aria-hidden className="size-3.5 text-accent" strokeWidth={2} />
            <span>{config.title}</span>
            <span className="rounded bg-surface px-1.5 py-0.5 text-[10.5px] font-normal text-ink-subtle">
              ~{config.estimated_minutes ?? 5} dk
            </span>
          </span>
          <ChevronDown
            aria-hidden
            className={cn(
              "size-4 text-ink-subtle transition-[rotate] duration-150 ease-out",
              showGuide && "rotate-180",
            )}
            strokeWidth={2}
          />
        </button>
      </div>

      {/* SETUP WIZARD & GUIDE */}
      {showGuide ? (
        <div className="flex flex-col gap-3 pt-1 text-[12px] leading-5 text-ink-muted border-t border-border/40">
          {/* Prerequisites */}
          {config.prerequisites && config.prerequisites.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-subtle">
              <span className="font-medium text-ink">Önkoşullar:</span>
              {config.prerequisites.map((req, i) => (
                <span key={i} className="rounded bg-surface px-2 py-0.5 border border-border/40">
                  {req}
                </span>
              ))}
            </div>
          ) : null}

          {/* Structured Steps if available */}
          {config.structured_steps && config.structured_steps.length > 0 ? (
            <div className="flex flex-col gap-2.5">
              {config.structured_steps.map((step) => {
                const isRedirectStep =
                  step.copyable_text !== undefined ||
                  step.title.toLowerCase().includes("redirect uri");
                return (
                  <div
                    key={step.step_number}
                    className="flex flex-col gap-1.5 rounded-[var(--radius-control)] bg-surface p-2.5 shadow-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 font-medium text-ink text-[12px]">
                        <span className="flex size-5 items-center justify-center rounded-full bg-accent-soft text-[11px] font-bold text-accent-ink">
                          {step.step_number}
                        </span>
                        {step.title}
                      </span>
                      {step.action_url ? (
                        <a
                          href={step.action_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline shrink-0"
                        >
                          <ExternalLink className="size-3" />
                          {step.action_label || "Aç"}
                        </a>
                      ) : null}
                    </div>

                    <p className="text-[11.5px] leading-relaxed text-ink-subtle ps-7">
                      {step.description}
                    </p>

                    {isRedirectStep ? (
                      <div className="ms-7 flex flex-wrap items-center gap-2 pt-1">
                        <code className="rounded bg-surface-muted px-2 py-1 font-mono text-[11px] text-ink select-all break-all border border-border/60">
                          {config.redirect_uri}
                        </code>
                        <Button variant="ghost" size="sm" onClick={copyRedirect} className="h-6 px-2 text-[11px]">
                          {copied ? (
                            <Check aria-hidden className="size-3 text-success" strokeWidth={2} />
                          ) : (
                            <Copy aria-hidden className="size-3" strokeWidth={2} />
                          )}
                          {copied ? "Kopyalandı" : "Kopyala"}
                        </Button>
                      </div>
                    ) : null}

                    {step.warning ? (
                      <div className="ms-7 flex items-start gap-1.5 rounded bg-warning-soft/70 px-2 py-1.5 text-[11px] text-warning leading-relaxed">
                        <ShieldAlert className="size-3.5 shrink-0 mt-0.5" />
                        <span>{step.warning}</span>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : (
            /* Fallback to simple steps list */
            <ol className="flex list-decimal flex-col gap-1 ps-4">
              {config.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          )}

          {/* Always ensure Redirect URI is visible in the guide */}
          {(!config.structured_steps || config.structured_steps.length === 0) ? (
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-surface px-2 py-1 font-mono text-[11px] text-ink border border-border/60">
                {config.redirect_uri}
              </code>
              <Button variant="ghost" size="sm" onClick={copyRedirect}>
                {copied ? (
                  <Check aria-hidden className="size-3.5 text-success" strokeWidth={2} />
                ) : (
                  <Copy aria-hidden className="size-3.5" strokeWidth={2} />
                )}
                {copied ? "Kopyalandı" : "Kopyala"}
              </Button>
            </div>
          ) : null}

          <p className="text-[11.5px] text-ink-subtle">
            İzinler: {config.scopes.join(", ")}
          </p>

          {config.notes.map((note) => (
            <p key={note} className="text-[11.5px] text-ink-subtle">
              {note}
            </p>
          ))}

          {/* FAQ & TROUBLESHOOTING ACCORDION */}
          {(config.faq && config.faq.length > 0) || (config.troubleshooting && config.troubleshooting.length > 0) ? (
            <div className="pt-2 border-t border-border/40">
              <button
                type="button"
                onClick={() => setShowFaq((v) => !v)}
                className="flex items-center justify-between w-full text-left text-[11.5px] font-medium text-ink hover:text-accent"
              >
                <span className="flex items-center gap-1.5">
                  <HelpCircle className="size-3.5 text-accent" />
                  Sık Karşılaşılan Sorunlar ve Çözümleri (FAQ)
                </span>
                <ChevronDown
                  className={cn("size-3.5 transition-transform duration-150", showFaq && "rotate-180")}
                />
              </button>

              {showFaq ? (
                <div className="flex flex-col gap-2 mt-2 pt-1">
                  {config.faq?.map((item, idx) => (
                    <div key={idx} className="flex flex-col gap-0.5 rounded bg-surface p-2 text-[11.5px] shadow-xs">
                      <span className="font-medium text-ink flex items-center gap-1">
                        <span className="text-accent font-bold">?</span> {item.question}
                      </span>
                      <span className="text-ink-subtle leading-relaxed ps-3">{item.answer}</span>
                    </div>
                  ))}

                  {config.troubleshooting?.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col gap-0.5 rounded bg-surface p-2 text-[11.5px] border-l-2 border-warning shadow-xs"
                    >
                      <span className="font-medium text-ink flex items-center gap-1.5">
                        <ShieldAlert className="size-3.5 text-warning shrink-0" />
                        {item.title}
                      </span>
                      <span className="text-ink-subtle leading-relaxed ps-5">
                        <strong>Neden:</strong> {item.cause}
                      </span>
                      <span className="text-ink-subtle leading-relaxed ps-5">
                        <strong>Çözüm:</strong> {item.solution}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* CREDENTIAL ENTRY FORM */}
      {editing ? (
        <div className="flex flex-col gap-3 pt-2 border-t border-border/40">
          <div className="flex flex-col gap-0.5">
            <span className="text-[12px] font-medium text-ink">
              OAuth 2.0 İstemci Bilgileri
            </span>
            <span className="text-[11px] text-ink-subtle">
              Kendi Google Cloud / Microsoft Entra uygulamanızın kimlik bilgilerini girin.
            </span>
          </div>

          {/* Client ID field */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <label
                htmlFor={`client-id-${config.provider}`}
                className="text-[12px] font-medium text-ink"
              >
                Client ID
              </label>
              <button
                type="button"
                onClick={() => setInfoField(infoField === "client_id" ? null : "client_id")}
                className="flex items-center gap-0.5 text-[11px] text-accent hover:underline"
              >
                <Info className="size-3" />
                Bu nedir?
              </button>
            </div>
            {infoField === "client_id" ? (
              <p className="rounded bg-surface p-2 text-[11px] leading-relaxed text-ink-subtle border border-border/40">
                Google Cloud veya Microsoft Entra üzerinde oluşturduğunuz Web uygulamasının herkese açık kimlik numarasıdır.
              </p>
            ) : null}
            <Input
              id={`client-id-${config.provider}`}
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              autoComplete="off"
            />
          </div>

          {/* Client Secret field with show/hide password toggle */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <label
                htmlFor={`client-secret-${config.provider}`}
                className="text-[12px] font-medium text-ink"
              >
                {config.configured ? "Yeni Client Secret (boş = değişmez)" : "Client Secret"}
              </label>
              <button
                type="button"
                onClick={() => setInfoField(infoField === "client_secret" ? null : "client_secret")}
                className="flex items-center gap-0.5 text-[11px] text-accent hover:underline"
              >
                <Info className="size-3" />
                Bu nedir?
              </button>
            </div>
            {infoField === "client_secret" ? (
              <p className="rounded bg-surface p-2 text-[11px] leading-relaxed text-ink-subtle border border-border/40">
                Yalnızca uygulamanız ile sunucu arasında paylaşılan gizli şifredir. Sunucumuzda AES-128-CBC ile şifrelenir ve ekrana asla açık metin olarak dönmez.
              </p>
            ) : null}
            <div className="relative flex items-center">
              <Input
                id={`client-secret-${config.provider}`}
                type={showSecret ? "text" : "password"}
                value={clientSecret}
                onChange={(event) => setClientSecret(event.target.value)}
                placeholder={config.configured ? "•••• (kayıtlı)" : "Client secret"}
                autoComplete="new-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowSecret((v) => !v)}
                className="absolute right-2.5 text-ink-subtle hover:text-ink focus:outline-none p-1"
                title={showSecret ? "Gizle" : "Yazılanı göster"}
                aria-label={showSecret ? "Gizle" : "Yazılanı göster"}
              >
                {showSecret ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <span className="text-[11px] text-ink-subtle">
              {showSecret
                ? "Göz açık: Şu an yazdığınız secret ekranda görünür. Kaydettikten sonra şifrelenir."
                : "Sunucuda APP_ENCRYPTION_KEY ile şifrelenir; tekrar düz metin gösterilmez."}
            </span>
          </div>

          {/* Tenant field (Outlook only) */}
          {config.provider === "outlook" ? (
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <label htmlFor="tenant" className="text-[12px] font-medium text-ink">
                  Kiracı (tenant)
                </label>
                <button
                  type="button"
                  onClick={() => setInfoField(infoField === "tenant" ? null : "tenant")}
                  className="flex items-center gap-0.5 text-[11px] text-accent hover:underline"
                >
                  <Info className="size-3" />
                  Bu nedir?
                </button>
              </div>
              {infoField === "tenant" ? (
                <p className="rounded bg-surface p-2 text-[11px] leading-relaxed text-ink-subtle border border-border/40">
                  Kişisel Hotmail, Outlook veya Live hesapları için 'consumers' seçilmelidir. Kurumsal Office365 hesapları için 'common' veya şirketinizin kiracı ID&apos;si kullanılır.
                </p>
              ) : null}
              <Select
                id="tenant"
                value={tenant}
                onChange={(event) => setTenant(event.target.value)}
              >
                <option value="consumers">consumers (kişisel hesaplar)</option>
                <option value="common">common (kişisel + kurumsal)</option>
                <option value="organizations">organizations (yalnızca kurumsal)</option>
              </Select>
            </div>
          ) : null}

          {/* Save / Cancel buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              loading={saving}
              disabled={!clientId || (!config.configured && !clientSecret)}
              onClick={save}
            >
              <Save aria-hidden className="size-3.5" strokeWidth={2} />
              Kaydet
            </Button>
            {config.configured ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onEditingChange(false);
                  setClientSecret("");
                }}
              >
                Vazgeç
              </Button>
            ) : null}
          </div>
        </div>
      ) : (
        /* CONFIGURED READ-ONLY SUMMARY */
        <div className="flex flex-col gap-2 pt-2 border-t border-border/40">
          <Row label="Client ID" value={config.client_id ?? "—"} mono />
          <Row label="Client Secret" value={config.client_secret_hint ?? "—"} mono />
          {config.provider === "outlook" ? (
            <Row label="Kiracı" value={config.tenant ?? "consumers"} />
          ) : null}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => onEditingChange(true)}>
              <KeyRound aria-hidden className="size-3.5" strokeWidth={2} />
              Güncelle
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-ink-muted pointer-hover:text-danger"
              onClick={remove}
            >
              <Trash2 aria-hidden className="size-3.5" strokeWidth={1.5} />
              Bilgileri sil
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------
function AccountRow({
  account,
  onConnect,
  onFeedback,
  onRefresh,
}: {
  account: MailAccount;
  onConnect: () => void;
  onFeedback: (feedback: Feedback | null) => void;
  onRefresh: () => void;
}) {
  const [senders, setSenders] = useState((account.filters.senders ?? []).join(", "));
  const [subjects, setSubjects] = useState((account.filters.subjects ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  async function saveFilters() {
    setSaving(true);
    try {
      await api.patch(`/api/v1/integrations/accounts/${account.id}`, {
        senders: senders.split(",").map((item) => item.trim()).filter(Boolean),
        subjects: subjects.split(",").map((item) => item.trim()).filter(Boolean),
      });
      onFeedback({ tone: "success", message: "Posta filtreleri güncellendi." });
      onRefresh();
    } catch (reason) {
      onFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Filtreler kaydedilemedi.",
      });
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    try {
      const result = await api.post<AccountTestResponse>(
        `/api/v1/integrations/accounts/${account.id}/test`,
      );
      onFeedback({ tone: result.ok ? "success" : "danger", message: result.message });
      onRefresh();
    } catch (reason) {
      onFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Test edilemedi.",
      });
    } finally {
      setTesting(false);
    }
  }

  async function disconnect() {
    try {
      await api.delete(`/api/v1/integrations/accounts/${account.id}`);
      onFeedback({
        tone: "warning",
        message: "Hesabın erişim anahtarları silindi; ilanlar korunuyor.",
      });
      onRefresh();
    } catch (reason) {
      onFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Bağlantı kesilemedi.",
      });
    }
  }

  async function purge() {
    try {
      await api.delete(`/api/v1/integrations/accounts/${account.id}/purge`);
      onFeedback({ tone: "success", message: "Hesap kaydı kaldırıldı." });
      onRefresh();
    } catch (reason) {
      onFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Kayıt kaldırılamadı.",
      });
    }
  }

  const disconnected = account.status === "disconnected";

  return (
    <li className="flex flex-col gap-3 rounded-[var(--radius-control)] bg-surface p-3 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-[13px] font-medium text-ink">
            {account.email_address}
          </span>
          <span className="text-[11.5px] text-ink-subtle">
            {account.last_synced_at
              ? `Son tarama ${formatDateTime(account.last_synced_at)} (${formatRelative(account.last_synced_at)})`
              : "Hiç taranmadı"}
            {account.initial_sync_completed ? "" : " · ilk tarama sürüyor"}
          </span>
        </div>
        <Badge variant={statusTones[account.status] ?? "neutral"}>
          {connectionStatusLabels[account.status] ?? account.status}
        </Badge>
      </div>

      {account.last_error ? (
        <p className="rounded-[var(--radius-control)] bg-danger-soft px-3 py-2 text-[11.5px] leading-4 text-danger">
          {account.last_error}
        </p>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Gönderen filtreleri" htmlFor={`senders-${account.id}`}>
          <Input
            id={`senders-${account.id}`}
            value={senders}
            onChange={(event) => setSenders(event.target.value)}
            placeholder="linkedin.com, kariyer@firma.com"
            autoComplete="off"
          />
        </Field>
        <Field label="Konu filtreleri" htmlFor={`subjects-${account.id}`}>
          <Input
            id={`subjects-${account.id}`}
            value={subjects}
            onChange={(event) => setSubjects(event.target.value)}
            placeholder="iş ilanı, job alert"
            autoComplete="off"
          />
        </Field>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" loading={saving} onClick={saveFilters}>
          <Save aria-hidden className="size-3.5" strokeWidth={2} />
          Filtreleri kaydet
        </Button>
        <Button variant="ghost" size="sm" loading={testing} onClick={test}>
          <RefreshCw aria-hidden className="size-3.5" strokeWidth={1.75} />
          Bağlantıyı test et
        </Button>
        <Button variant="ghost" size="sm" onClick={onConnect}>
          <ExternalLink aria-hidden className="size-3.5" strokeWidth={1.75} />
          {disconnected ? "Yeniden bağlan" : "Yeniden yetkilendir"}
        </Button>
        {disconnected ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-ink-muted pointer-hover:text-danger"
            onClick={purge}
          >
            <Trash2 aria-hidden className="size-3.5" strokeWidth={1.5} />
            Kaydı kaldır
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="text-ink-muted pointer-hover:text-danger"
            onClick={disconnect}
          >
            <Unplug aria-hidden className="size-3.5" strokeWidth={1.5} />
            Bağlantıyı kes
          </Button>
        )}
      </div>
    </li>
  );
}

// ----------------------------------------------------------------------
function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-subtle">{label}</span>
      <span
        className={cn(
          "truncate text-right font-medium text-ink",
          mono && "font-mono text-[11.5px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}
