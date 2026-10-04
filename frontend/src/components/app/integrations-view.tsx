"use client";

import { useEffect, useState } from "react";
import {
  ChevronDown,
  ExternalLink,
  KeyRound,
  Lock,
  Mail,
  Plug,
  RefreshCw,
  Save,
  Search,
  ServerCog,
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
import { Field, Input } from "@/components/ui/form";
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
        access_denied: "Sağlayıcı yetkilendirmesi iptal edildi veya reddedildi.",
        invalid_client: "Sunucuda tanımlı istemci kimlik bilgileri geçersiz. Lütfen sistem yöneticisine başvurun.",
        redirect_uri_mismatch: "Yönlendirme adresi sağlayıcı ayarlarıyla uyuşmuyor. Lütfen sistem yöneticisine başvurun.",
        not_a_test_user: "Google uygulaması test modunda ve hesabınız test kullanıcıları listesinde değil.",
        oauth_not_configured: "Entegrasyon henüz yönetici tarafından yapılandırılmamış.",
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
  const Icon = Mail;
  const isGmail = integration.provider === "gmail";
  const title = isGmail ? "GOOGLE / GMAIL" : "OUTLOOK / HOTMAIL";
  const description = isGmail
    ? "LinkedIn iş bildirimlerinizi ve desteklenen kariyer e-postalarını Gmail üzerinden okuyun."
    : "Hotmail, Outlook.com ve Live posta kutunuzdaki iş bildirimlerini Microsoft Graph üzerinden okuyun.";
  const buttonLabel = isGmail ? "Gmail Bağla" : "Outlook / Hotmail Bağla";
  const isConfigured = integration.configured ?? false;

  const connectedAccounts = integration.accounts.filter(
    (a) => a.status === "connected",
  );
  const hasConnectedAccount = connectedAccounts.length > 0;

  return (
    <Card className="flex flex-col" data-testid={`integration-card-${integration.provider}`}>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Icon aria-hidden className="size-4" strokeWidth={1.75} />
            {title}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={hasConnectedAccount ? "success" : isConfigured ? "neutral" : "warning"}>
              {hasConnectedAccount ? "BAĞLI" : isConfigured ? "BAĞLI DEĞİL" : "YAPILANDIRILMAMIŞ"}
            </Badge>
            <Badge variant="muted">Yalnızca posta okuma</Badge>
          </div>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        {/* Security and privacy notes */}
        <div className="rounded-[var(--radius-control)] bg-surface-muted p-3 text-[11.5px] leading-relaxed text-ink-subtle space-y-1">
          {isGmail ? (
            <>
              <p>Google parolanız Job Finder ile paylaşılmaz.</p>
              <p>Yalnızca posta okuma izni istenir.</p>
              <p>Job Finder yalnızca iş bildirimlerini bulmak için e-posta okuma izni kullanır.</p>
            </>
          ) : (
            <>
              <p>Microsoft parolanız Job Finder ile paylaşılmaz.</p>
              <p>Yalnızca posta okuma izni istenir.</p>
            </>
          )}
        </div>

        {/* Connect button */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button
            variant="secondary"
            loading={busy}
            disabled={!isConfigured}
            onClick={() => onConnect()}
          >
            <Plug aria-hidden className="size-3.5" strokeWidth={2} />
            <span>{buttonLabel}</span>
          </Button>
          {!isConfigured ? (
            <span className="text-[11.5px] leading-4 text-warning">
              Yönetici tarafından yapılandırılmamış.
            </span>
          ) : (
            <span className="text-[11.5px] leading-4 text-ink-subtle">
              {isGmail
                ? "Google hesabınızı yetkilendirin (parola istenmez)."
                : "Microsoft hesabınızı yetkilendirin (parola istenmez)."}
            </span>
          )}
        </div>

        {/* Accounts list */}
        {integration.accounts.length ? (
          <ul className="flex flex-col gap-2">
            {integration.accounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                providerLabel={integration.label}
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
            description="Hesabınızı bağlayın. Birden fazla posta kutusu ekleyebilirsiniz."
            className="py-6"
          />
        )}
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------------
function AccountRow({
  account,
  providerLabel,
  onConnect,
  onFeedback,
  onRefresh,
}: {
  account: MailAccount;
  providerLabel: string;
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

  const isConnected = account.status === "connected";
  const disconnected = account.status === "disconnected";

  return (
    <li className="flex flex-col gap-3 rounded-[var(--radius-control)] bg-surface p-3 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-2">
            <span className="truncate text-[13px] font-medium text-ink">
              {account.email_address}
            </span>
            <Badge variant="muted" className="text-[10px]">
              {providerLabel}
            </Badge>
            <Badge variant="muted" className="text-[10px]">
              Yalnızca posta okuma
            </Badge>
          </div>
          <span className="text-[11.5px] text-ink-subtle">
            {account.last_synced_at
              ? `Son tarama ${formatDateTime(account.last_synced_at)} (${formatRelative(account.last_synced_at)})`
              : "Hiç taranmadı"}
            {account.initial_sync_completed ? "" : " · ilk tarama sürüyor"}
          </span>
        </div>
        <Badge variant={isConnected ? "success" : statusTones[account.status] ?? "neutral"}>
          {isConnected ? "BAĞLI" : connectionStatusLabels[account.status] ?? account.status}
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
          Bağlantıyı Test Et
        </Button>
        <Button variant="ghost" size="sm" onClick={onConnect}>
          <ExternalLink aria-hidden className="size-3.5" strokeWidth={1.75} />
          {disconnected ? "Yeniden bağlan" : "Yeniden Yetkilendir"}
        </Button>
        {disconnected ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-ink-muted pointer-hover:text-danger"
            onClick={purge}
          >
            <Trash2 aria-hidden className="size-3.5" strokeWidth={1.5} />
            Kaydı Kaldır
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="text-ink-muted pointer-hover:text-danger"
            onClick={disconnect}
          >
            <Unplug aria-hidden className="size-3.5" strokeWidth={1.5} />
            Bağlantıyı Kaldır
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
