"use client";

import { useState } from "react";
import {
  BellRing,
  Check,
  Hash,
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
  const [candidates, setCandidates] = useState<TelegramChatCandidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<
    { tone: "success" | "warning" | "danger"; message: string } | null
  >(null);

  const data = status.data;

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

        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={data?.has_token ? "Yeni bot token (boş = değişmez)" : "Bot token"}
            hint="BotFather'dan aldığınız token. Bir daha düz metin gösterilmez."
            htmlFor="telegram-token"
          >
            <Input
              id="telegram-token"
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder={data?.has_token ? "•••• (kayıtlı)" : "123456789:AA…"}
              autoComplete="new-password"
            />
          </Field>
          <Field
            label="Chat ID"
            hint={data?.hint ?? "Botunuza /start yazıp 'Chat ID'yi algıla' düğmesini kullanın."}
            htmlFor="telegram-chat"
          >
            <Input
              id="telegram-chat"
              value={chatId}
              onChange={(event) => setChatId(event.target.value)}
              placeholder={data?.chat_id ?? "Örn: 123456789"}
              autoComplete="off"
            />
          </Field>
        </div>

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

        <p className="text-[11.5px] leading-4 text-ink-subtle">
          Bot oluşturma: Telegram&apos;da <strong>@BotFather</strong> → <code>/newbot</code> →
          token&apos;ı buraya yapıştırın → botunuza <code>/start</code> gönderin →
          &quot;Chat ID&apos;yi algıla&quot;.
        </p>
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
