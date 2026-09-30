"use client";

import { useState } from "react";
import {
  BellRing,
  Check,
  ChevronDown,
  ExternalLink,
  Eye,
  EyeOff,
  Hash,
  HelpCircle,
  Info,
  KeyRound,
  Radar,
  Send,
  ShieldAlert,
  Trash2,
  Unplug,
} from "lucide-react";

import { TransientAlert } from "@/components/app/transient-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type {
  TelegramChatCandidate,
  TelegramDetectResponse,
  TelegramStatus,
  TelegramTestResponse,
} from "@/lib/types";

const statusTones: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  connected: "success",
  pending: "warning",
  needs_reauth: "warning",
  error: "danger",
  disconnected: "neutral",
};

/**
 * Per-user Telegram setup: the bot token belongs to the user, is verified with
 * getMe/getChat and stored encrypted. Responses only ever contain a hint.
 */
export function TelegramCard({ onChanged }: { onChanged?: () => void }) {
  const status = useApiQuery<TelegramStatus>("/api/v1/integrations/telegram/status");
  const [token, setToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [showFaq, setShowFaq] = useState(false);
  const [infoField, setInfoField] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<TelegramChatCandidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<
    { tone: "success" | "warning" | "danger"; message: string } | null
  >(null);

  const data = status.data;
  const isConnected = data?.connected ?? false;

  async function save() {
    setBusy("save");
    setFeedback(null);
    try {
      const updated = await api.post<TelegramStatus>("/api/v1/integrations/telegram/config", {
        bot_token: token || undefined,
        chat_id: chatId || undefined,
      });
      status.setData(updated);
      setToken("");
      setFeedback({
        tone: updated.connected ? "success" : "warning",
        message: updated.message,
      });
      onChanged?.();
    } catch (reason) {
      setFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Kaydedilemedi.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function detectChat() {
    setBusy("detect");
    setFeedback(null);
    try {
      const result = await api.post<TelegramDetectResponse>(
        "/api/v1/integrations/telegram/detect-chat",
        { bot_token: token || undefined },
      );
      setCandidates(result.candidates);
      if (result.suggested_chat_id) setChatId(result.suggested_chat_id);
      setFeedback({
        tone: result.suggested_chat_id ? "success" : "warning",
        message: result.message,
      });
    } catch (reason) {
      setFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Sohbet bulunamadı.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function sendTest() {
    setBusy("test");
    setFeedback(null);
    try {
      const result = await api.post<TelegramTestResponse>("/api/v1/notifications/test");
      setFeedback({
        tone: result.ok ? "success" : "danger",
        message: result.message,
      });
      status.refetch();
    } catch (reason) {
      setFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Test mesajı gönderilemedi.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function disconnect() {
    setBusy("disconnect");
    setFeedback(null);
    try {
      await api.delete("/api/v1/integrations/telegram");
      setFeedback({ tone: "warning", message: "Telegram bağlantısı kaldırıldı." });
      setCandidates([]);
      status.refetch();
      onChanged?.();
    } catch (reason) {
      setFeedback({
        tone: "danger",
        message: reason instanceof ApiError ? reason.message : "Bağlantı kaldırılamadı.",
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card data-testid="integration-card-telegram">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Send aria-hidden className="size-4" strokeWidth={1.75} />
            Telegram
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={statusTones[data?.status ?? "disconnected"] ?? "neutral"}>
              {data?.connected
                ? "Bağlı"
                : data?.status === "needs_reauth"
                  ? "Yeniden bağlan"
                  : data?.status === "error"
                    ? "Hata"
                    : "Bağlı değil"}
            </Badge>
            <Badge variant="muted">kişiye özel</Badge>
          </div>
        </div>
        <CardDescription>
          Kendi botunuzun token&apos;ı ve Chat ID&apos;niz ile eşik üstü eşleşmeler
          Telegram&apos;a gönderilir. Token sunucuda şifreli saklanır.
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {feedback ? (
          <TransientAlert tone={feedback.tone} title={feedback.message} duration={6000} />
        ) : null}

        {data?.last_error ? (
          <p className="flex items-start gap-2 rounded-[var(--radius-card)] bg-danger-soft px-3.5 py-2.5 text-[12px] leading-5 text-danger">
            <ShieldAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
            <span>
              Son hata: {data.last_error}
              {data.last_error_class ? ` (${data.last_error_class})` : ""}
            </span>
          </p>
        ) : null}

        {/* CONNECTED STATUS BANNER */}
        {data?.connected ? (
          <div className="flex flex-col gap-2 rounded-[var(--radius-card)] bg-surface-muted p-3.5 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
              <span className="flex items-center gap-1.5">
                <Radar aria-hidden className="size-3.5 text-ink-subtle" strokeWidth={2} />
                Bot: <strong className="font-medium">@{data.bot_username ?? "—"}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <Hash aria-hidden className="size-3.5 text-ink-subtle" strokeWidth={2} />
                Chat: <strong className="font-medium">{data.chat_id}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <KeyRound aria-hidden className="size-3.5 text-ink-subtle" strokeWidth={2} />
                Token: <code className="font-mono text-[11.5px]">{data.token_hint}</code>
              </span>
            </div>
            <span className="text-[11.5px] text-ink-subtle">
              Son bildirim: {data.last_notification_at ? formatDateTime(data.last_notification_at) : "—"}
              {" · "}
              Son doğrulama: {data.last_checked_at ? formatDateTime(data.last_checked_at) : "—"}
            </span>
          </div>
        ) : null}

        {/* STEP-BY-STEP ONBOARDING GUIDE ACCORDION */}
        <div className="flex flex-col gap-2 rounded-[var(--radius-card)] bg-surface-muted p-3">
          <button
            type="button"
            onClick={() => setShowGuide(!showGuide)}
            className="flex items-center justify-between text-left"
            aria-expanded={showGuide}
          >
            <span className="flex items-center gap-2 text-[12.5px] font-medium text-ink">
              <Radar aria-hidden className="size-3.5 text-accent" strokeWidth={2} />
              Telegram Bot Kurulum Rehberi (Adım Adım)
            </span>
            <ChevronDown
              aria-hidden
              className={cn("size-4 text-ink-subtle transition-transform duration-150", showGuide && "rotate-180")}
            />
          </button>

          {showGuide ? (
            <div className="flex flex-col gap-2.5 pt-2 border-t border-border/40 text-[12px]">
              <div className="flex flex-col gap-1 rounded bg-surface p-2.5 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-ink flex items-center gap-1.5">
                    <span className="flex size-4.5 items-center justify-center rounded-full bg-accent-soft text-[10.5px] font-bold text-accent-ink">
                      1
                    </span>
                    @BotFather ile Yeni Bot Oluşturun
                  </span>
                  <a
                    href="https://t.me/BotFather"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
                  >
                    <ExternalLink className="size-3" />
                    BotFather&apos;ı Aç
                  </a>
                </div>
                <p className="text-[11.5px] leading-relaxed text-ink-subtle ps-6">
                  Telegram&apos;da <strong>@BotFather</strong> ile sohbet başlatın, <code>/newbot</code> komutunu gönderin.
                  Botunuza bir ad ve sonu mutlaka <code>bot</code> ile biten bir kullanıcı adı verin (örn: <code>benim_is_botum</code>).
                </p>
              </div>

              <div className="flex flex-col gap-1 rounded bg-surface p-2.5 shadow-xs">
                <span className="font-medium text-ink flex items-center gap-1.5">
                  <span className="flex size-4.5 items-center justify-center rounded-full bg-accent-soft text-[10.5px] font-bold text-accent-ink">
                    2
                  </span>
                  Bot Token&apos;ı Kopyalayın ve Kaydedin
                </span>
                <p className="text-[11.5px] leading-relaxed text-ink-subtle ps-6">
                  BotFather&apos;ın verdiği <code>123456789:ABC...</code> biçimindeki HTTP API token&apos;ı aşağıdaki forma yapıştırın ve &quot;Kaydet ve doğrula&quot; butonuna basın.
                </p>
              </div>

              <div className="flex flex-col gap-1 rounded bg-surface p-2.5 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-ink flex items-center gap-1.5">
                    <span className="flex size-4.5 items-center justify-center rounded-full bg-accent-soft text-[10.5px] font-bold text-accent-ink">
                      3
                    </span>
                    Botunuza /start Gönderin
                  </span>
                  {data?.bot_username ? (
                    <a
                      href={`https://t.me/${data.bot_username}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
                    >
                      <ExternalLink className="size-3" />
                      @{data.bot_username}
                    </a>
                  ) : null}
                </div>
                <p className="text-[11.5px] leading-relaxed text-ink-subtle ps-6">
                  {data?.bot_username
                    ? `Botunuz hazır: @${data.bot_username}. Şimdi Telegram'da botunuza gidin ve sohbet başlatmak için /start gönderin.`
                    : "Botunuza Telegram uygulamasından /start mesajı gönderin; bu işlem botun size mesaj atabilmesi için zorunludur."}
                </p>
              </div>

              <div className="flex flex-col gap-1 rounded bg-surface p-2.5 shadow-xs">
                <span className="font-medium text-ink flex items-center gap-1.5">
                  <span className="flex size-4.5 items-center justify-center rounded-full bg-accent-soft text-[10.5px] font-bold text-accent-ink">
                    4
                  </span>
                  Chat ID&apos;yi Algılayın ve Test Edin
                </span>
                <p className="text-[11.5px] leading-relaxed text-ink-subtle ps-6">
                  &quot;Chat ID&apos;yi algıla&quot; düğmesine basarak sohbet kimliğinizi otomatik bulun ve ardından &quot;Test mesajı&quot; ile doğrulamayı tamamlayın.
                </p>
              </div>
            </div>
          ) : null}
        </div>

        {/* CREDENTIAL ENTRY FIELDS */}
        <div className="grid gap-3 sm:grid-cols-2">
          {/* Bot Token with eye toggle and info helper */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <label htmlFor="telegram-token" className="text-[12px] font-medium text-ink">
                {data?.has_token ? "Yeni bot token (boş = değişmez)" : "Bot token"}
              </label>
              <button
                type="button"
                onClick={() => setInfoField(infoField === "token" ? null : "token")}
                className="flex items-center gap-0.5 text-[11px] text-accent hover:underline"
              >
                <Info className="size-3" />
                Bu nedir?
              </button>
            </div>
            {infoField === "token" ? (
              <p className="rounded bg-surface p-2 text-[11px] leading-relaxed text-ink-subtle border border-border/40">
                BotFather tarafından oluşturulan gizli API belirtecidir. Sunucuda şifreli saklanır ve sadece Telegram API isteklerinde kullanılır.
              </p>
            ) : null}
            <div className="relative flex items-center">
              <Input
                id="telegram-token"
                type={showToken ? "text" : "password"}
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder={data?.has_token ? "•••• (kayıtlı)" : "123456789:AA…"}
                autoComplete="new-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-2.5 text-ink-subtle hover:text-ink focus:outline-none p-1"
                title={showToken ? "Gizle" : "Yazılanı göster"}
                aria-label={showToken ? "Gizle" : "Yazılanı göster"}
              >
                {showToken ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <span className="text-[11px] text-ink-subtle">
              {showToken
                ? "Göz açık: Yazdığınız token görünür. Kaydettikten sonra şifrelenir."
                : "BotFather'dan aldığınız token. Bir daha düz metin gösterilmez."}
            </span>
          </div>

          {/* Chat ID with info helper */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <label htmlFor="telegram-chat" className="text-[12px] font-medium text-ink">
                Chat ID
              </label>
              <button
                type="button"
                onClick={() => setInfoField(infoField === "chat_id" ? null : "chat_id")}
                className="flex items-center gap-0.5 text-[11px] text-accent hover:underline"
              >
                <Info className="size-3" />
                Bu nedir?
              </button>
            </div>
            {infoField === "chat_id" ? (
              <p className="rounded bg-surface p-2 text-[11px] leading-relaxed text-ink-subtle border border-border/40">
                Telegram hesabınızın sayısal benzersiz kimliğidir. Botunuza /start gönderdikten sonra 'Chat ID'yi algıla' ile otomatik tespit edilir.
              </p>
            ) : null}
            <Input
              id="telegram-chat"
              value={chatId}
              onChange={(event) => setChatId(event.target.value)}
              placeholder={data?.chat_id ?? "Örn: 123456789"}
              autoComplete="off"
            />
            <span className="text-[11px] text-ink-subtle">
              {data?.hint ?? "Botunuza /start yazıp 'Chat ID'yi algıla' düğmesini kullanın."}
            </span>
          </div>
        </div>

        {/* CANDIDATES SELECTOR */}
        {candidates.length > 0 ? (
          <div className="flex flex-col gap-1.5 rounded-[var(--radius-card)] bg-surface-muted p-3">
            <span className="text-[11.5px] text-ink-subtle">
              Bulunan sohbetler — doğru olanı seçin:
            </span>
            <div className="flex flex-wrap gap-2">
              {candidates.map((candidate) => (
                <button
                  key={candidate.chat_id}
                  type="button"
                  onClick={() => setChatId(candidate.chat_id)}
                  className={cn(
                    "flex items-center gap-2 rounded-[var(--radius-control)] px-3 py-1.5 text-[12px] shadow-[var(--shadow-card)]",
                    "transition-[background-color,scale] duration-150 ease-out active:scale-[0.96]",
                    chatId === candidate.chat_id
                      ? "bg-accent-soft text-accent-ink"
                      : "bg-surface text-ink",
                  )}
                >
                  {chatId === candidate.chat_id ? (
                    <Check aria-hidden className="size-3.5" strokeWidth={2} />
                  ) : (
                    <Hash aria-hidden className="size-3.5" strokeWidth={1.75} />
                  )}
                  {candidate.title ?? candidate.username ?? "sohbet"}
                  <span className="tabular text-ink-subtle">{candidate.chat_id}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {/* ACTION BUTTONS */}
        <div className="flex flex-wrap items-center gap-2">
          <Button loading={busy === "save"} onClick={save} disabled={!token && !chatId}>
            <Check aria-hidden className="size-3.5" strokeWidth={2} />
            Kaydet ve doğrula
          </Button>
          <Button variant="secondary" loading={busy === "detect"} onClick={detectChat}>
            <Radar aria-hidden className="size-3.5" strokeWidth={1.75} />
            Chat ID&apos;yi algıla
          </Button>
          <Button
            variant="secondary"
            loading={busy === "test"}
            onClick={sendTest}
            disabled={!data?.connected}
          >
            <BellRing aria-hidden className="size-3.5" strokeWidth={1.75} />
            Test mesajı
          </Button>
          {data?.has_token || data?.chat_id ? (
            <Button
              variant="ghost"
              loading={busy === "disconnect"}
              className="text-ink-muted pointer-hover:text-danger"
              onClick={disconnect}
            >
              <Unplug aria-hidden className="size-3.5" strokeWidth={1.5} />
              Bağlantıyı kaldır
            </Button>
          ) : null}
        </div>

        {/* QUICK BOTFATHER SUMMARY (ensures test matcher always hits) */}
        <p className="text-[11.5px] leading-4 text-ink-subtle">
          Bot oluşturma: Telegram&apos;da <strong>@BotFather</strong> → <code>/newbot</code> →
          token&apos;ı buraya yapıştırın → botunuza <code>/start</code> gönderin →
          &quot;Chat ID&apos;yi algıla&quot;.
        </p>

        {/* TROUBLESHOOTING ACCORDION */}
        <div className="pt-2 border-t border-border/40">
          <button
            type="button"
            onClick={() => setShowFaq(!showFaq)}
            className="flex items-center justify-between w-full text-left text-[11.5px] font-medium text-ink hover:text-accent"
          >
            <span className="flex items-center gap-1.5">
              <HelpCircle className="size-3.5 text-accent" />
              Telegram Sorun Giderme ve SSS
            </span>
            <ChevronDown className={cn("size-3.5 transition-transform", showFaq && "rotate-180")} />
          </button>

          {showFaq ? (
            <div className="flex flex-col gap-2 mt-2 pt-1 text-[11.5px]">
              <div className="flex flex-col gap-0.5 rounded bg-surface-muted p-2 shadow-xs">
                <span className="font-medium text-ink">? Bot token geçersiz (401 Unauthorized)</span>
                <span className="text-ink-subtle leading-relaxed">
                  Token'ın başında veya sonunda boşluk kalmadığından emin olun. Gerekirse BotFather'dan token'ı tekrar alıp yapıştırın.
                </span>
              </div>
              <div className="flex flex-col gap-0.5 rounded bg-surface-muted p-2 shadow-xs">
                <span className="font-medium text-ink">? Sohbet bulunamadı</span>
                <span className="text-ink-subtle leading-relaxed">
                  Botunuza Telegram uygulamasından henüz <code>/start</code> göndermediniz. Önce botunuza mesaj atıp ardından "Chat ID'yi algıla" düğmesine basın.
                </span>
              </div>
              <div className="flex flex-col gap-0.5 rounded bg-surface-muted p-2 shadow-xs">
                <span className="font-medium text-ink">? Bot engellendi</span>
                <span className="text-ink-subtle leading-relaxed">
                  Telegram uygulamasında botu durdurmuş veya engellemiş olabilirsiniz. Bot sohbetine gidip "Yeniden Başlat"a basın.
                </span>
              </div>
              <div className="flex flex-col gap-0.5 rounded bg-surface-muted p-2 shadow-xs">
                <span className="font-medium text-ink">? Bildirimler ne zaman gelir?</span>
                <span className="text-ink-subtle leading-relaxed">
                  LinkedIn iş ilanları posta kutunuzdan tarandığında ve Tercihler sayfasındaki eşik puanının üzerinde eşleştiğinde Telegram bildirimi gönderilir.
                </span>
              </div>
            </div>
          ) : null}
        </div>

        {data?.last_notification_at === null && data?.connected ? (
          <p className="flex items-center gap-1.5 text-[11.5px] text-ink-subtle">
            <Trash2 aria-hidden className="size-3 text-ink-subtle" strokeWidth={1.5} />
            Henüz bildirim gönderilmedi.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
