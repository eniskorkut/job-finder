"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MailCheck, Radar, ShieldX, UserPlus } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { InvitationPublic, SessionResponse } from "@/lib/types";

export function InviteAcceptView({ token }: { token: string }) {
  const router = useRouter();
  const invitation = useApiQuery<InvitationPublic>(
    `/api/v1/auth/invitations/${token}/inspect`,
  );

  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const mismatch = confirm.length > 0 && confirm !== password;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post<SessionResponse>(
        "/api/v1/auth/invitations/accept",
        {
          token,
          username,
          full_name: fullName || null,
          password,
        },
        { skipCsrf: true },
      );
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "Davet kabul edilemedi. Bağlantı süresi dolmuş olabilir.",
      );
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-10">
      <div className="stagger flex w-full max-w-md flex-col gap-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <span
            aria-hidden
            className="flex size-10 items-center justify-center rounded-[12px] bg-accent text-white dark:text-[oklch(0.16_0.01_264)]"
          >
            <Radar className="size-5" strokeWidth={2} />
          </span>
          <h1 className="text-lg leading-6 font-semibold text-ink">Job Hunter</h1>
        </div>

        {invitation.loading ? (
          <Card className="p-5">
            <div className="flex flex-col gap-3">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          </Card>
        ) : invitation.error || !invitation.data?.is_valid ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldX aria-hidden className="size-4" strokeWidth={1.75} />
                Davet geçersiz
              </CardTitle>
              <CardDescription>
                {invitation.data?.message ??
                  "Bu davet bağlantısı geçersiz, kullanılmış veya süresi dolmuş. Yeni bir davet isteyin."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                variant="secondary"
                onClick={() => router.replace("/login")}
              >
                Giriş ekranına dön
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MailCheck aria-hidden className="size-4" strokeWidth={1.75} />
                Davetlisiniz
              </CardTitle>
              <CardDescription>
                {invitation.data.invited_by ?? "Job Hunter"} sizi davet etti:{" "}
                <strong className="font-medium text-ink">
                  {invitation.data.email}
                </strong>
                <br />
                Bağlantı {formatDateTime(invitation.data.expires_at)} tarihine
                kadar ve yalnızca bir kez geçerli.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
                <Field label="Kullanıcı adı" htmlFor="username">
                  <Input
                    id="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    autoComplete="username"
                    pattern="[A-Za-z0-9_.\-]{3,50}"
                    title="3-50 karakter: harf, rakam, nokta, tire, alt çizgi"
                    required
                  />
                </Field>
                <Field label="Ad Soyad (opsiyonel)" htmlFor="full-name">
                  <Input
                    id="full-name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    autoComplete="name"
                  />
                </Field>
                <Field
                  label="Parola"
                  hint="En az 10 karakter."
                  htmlFor="new-password"
                >
                  <Input
                    id="new-password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="new-password"
                    minLength={10}
                    required
                  />
                </Field>
                <Field
                  label="Parola (tekrar)"
                  error={mismatch ? "Parolalar eşleşmiyor." : null}
                  htmlFor="confirm-password"
                >
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </Field>

                {error ? (
                  <Alert tone="danger" title="Kayıt tamamlanamadı">
                    {error}
                  </Alert>
                ) : null}

                <Button
                  type="submit"
                  size="lg"
                  loading={submitting}
                  disabled={!username || password.length < 10 || mismatch}
                  className="w-full justify-center"
                >
                  {submitting ? null : (
                    <UserPlus aria-hidden className="size-4" strokeWidth={2} />
                  )}
                  Hesabımı oluştur
                </Button>
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  );
}
