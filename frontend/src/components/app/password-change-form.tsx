"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";

import { TransientAlert } from "@/components/app/transient-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { api, ApiError } from "@/lib/api";

const MIN_LENGTH = 10;

export function PasswordChangeForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<
    { tone: "success" | "danger"; message: string } | null
  >(null);

  const mismatch = confirm.length > 0 && confirm !== next;
  const tooShort = next.length > 0 && next.length < MIN_LENGTH;
  const disabled =
    !current || next.length < MIN_LENGTH || confirm !== next || !confirm;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (disabled) return;
    setSaving(true);
    setFeedback(null);
    try {
      await api.post("/api/v1/auth/password", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      setFeedback({
        tone: "success",
        message: "Parola güncellendi. Diğer tüm oturumlar kapatıldı.",
      });
    } catch (error) {
      setFeedback({
        tone: "danger",
        message:
          error instanceof ApiError ? error.message : "Parola güncellenemedi.",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound aria-hidden className="size-4" strokeWidth={1.75} />
          Hesap ve güvenlik
        </CardTitle>
        <CardDescription>
          Parolanız Argon2id ile saklanır. Parola değiştiğinde bu tarayıcı
          dışındaki tüm oturumlar kapatılır.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {feedback ? (
          <TransientAlert tone={feedback.tone} title={feedback.message} />
        ) : null}

        <form onSubmit={submit} className="grid gap-4 md:grid-cols-3" noValidate>
          <Field label="Mevcut parola" htmlFor="current-password">
            <Input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
          </Field>
          <Field
            label="Yeni parola"
            hint={`En az ${MIN_LENGTH} karakter.`}
            error={tooShort ? `En az ${MIN_LENGTH} karakter olmalı.` : null}
            htmlFor="next-password"
          >
            <Input
              id="next-password"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
          </Field>
          <Field
            label="Yeni parola (tekrar)"
            error={mismatch ? "Parolalar eşleşmiyor." : null}
            htmlFor="confirm-password"
          >
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
          </Field>

          <div className="md:col-span-3 md:flex md:justify-end">
            <Button type="submit" loading={saving} disabled={disabled}>
              Parolayı güncelle
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
