"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { KeyRound, Radar } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { api, ApiError } from "@/lib/api";
import type { SessionResponse } from "@/lib/types";

const isDevelopment = process.env.NODE_ENV !== "production";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next") ?? "/";

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post<SessionResponse>("/api/v1/auth/login", {
        identifier,
        password,
      });
      // Full navigation so the server components re-read the new cookie.
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
      router.refresh();
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "Giriş yapılamadı. Tekrar deneyin.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="stagger flex w-full max-w-sm flex-col gap-4">
      <div className="flex flex-col items-center gap-2 text-center">
        <span
          aria-hidden
          className="flex size-10 items-center justify-center rounded-[12px] bg-accent text-white dark:text-[oklch(0.16_0.01_264)]"
        >
          <Radar className="size-5" strokeWidth={2} />
        </span>
        <h1 className="text-lg leading-6 font-semibold text-ink">Job Hunter</h1>
        <p className="text-[13px] text-ink-muted">
          Kişisel iş ilanı eşleştirme paneli
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound aria-hidden className="size-4" strokeWidth={1.75} />
            Giriş yap
          </CardTitle>
          <CardDescription>
            Kayıt yalnızca davet bağlantısı ile açılır.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
            <Field label="Kullanıcı adı veya e-posta" htmlFor="identifier">
              <Input
                id="identifier"
                name="identifier"
                autoComplete="username"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                placeholder="ornek@example.com"
                required
              />
            </Field>
            <Field label="Parola" htmlFor="password">
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                required
              />
            </Field>

            {error ? (
              <Alert tone="danger" title="Giriş başarısız">
                {error}
              </Alert>
            ) : null}

            <Button
              type="submit"
              size="lg"
              loading={submitting}
              disabled={!identifier || !password}
              className="w-full justify-center"
            >
              {submitting ? null : <KeyRound aria-hidden className="size-4" strokeWidth={2} />}
              Giriş
            </Button>
          </form>
        </CardContent>
      </Card>

      {isDevelopment ? (
        <p className="text-center text-[11.5px] leading-5 text-ink-subtle">
          Geliştirme ortamı: örnek hesaplar <code className="font-mono">ai_hunter</code>{" "}
          ve <code className="font-mono">data_hunter</code> — parola{" "}
          <code className="font-mono">DemoParola!2026</code> (python -m app.cli seed).
        </p>
      ) : null}
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-10">
      <Suspense
        fallback={
          <div className="text-[13px] text-ink-muted">Yükleniyor…</div>
        }
      >
        <LoginForm />
      </Suspense>
    </main>
  );
}
