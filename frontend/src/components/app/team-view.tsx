"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Link2, MailPlus, ShieldAlert, Trash2 } from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { TransientAlert } from "@/components/app/transient-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/form";
import { SkeletonRows } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { Invitation } from "@/lib/types";

const statusTones = {
  pending: "accent",
  used: "success",
  expired: "muted",
} as const;

const statusLabels = {
  pending: "Bekliyor",
  used: "Kullanıldı",
  expired: "Süresi doldu",
} as const;

export function TeamView() {
  const invitations = useApiQuery<Invitation[]>("/api/v1/auth/invitations");
  const [email, setEmail] = useState("");
  const [ttl, setTtl] = useState(48);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  async function create() {
    setCreating(true);
    setError(null);
    try {
      const invitation = await api.post<Invitation>("/api/v1/auth/invitations", {
        email,
        expires_in_hours: ttl,
      });
      setCreated(invitation);
      setEmail("");
      invitations.refetch();
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "Davet oluşturulamadı.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function copyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setError("Bağlantı panoya kopyalanamadı. Elle seçip kopyalayın.");
    }
  }

  async function revoke(id: string) {
    setError(null);
    try {
      await api.delete(`/api/v1/auth/invitations/${id}`);
      invitations.refetch();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Davet iptal edilemedi.");
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-3 rounded-[var(--radius-card)] bg-info-soft px-3.5 py-3 text-[12.5px] leading-5 text-ink-muted">
        <ShieldAlert
          aria-hidden
          className="mt-0.5 size-4 shrink-0 text-info"
          strokeWidth={2}
        />
        <p>
          Herkese açık kayıt kapalıdır. İkinci kullanıcı yalnızca bu ekrandan
          (veya <code className="font-mono">python -m app.cli invite</code>{" "}
          komutundan) üretilen <strong className="font-semibold">süreli ve tek
          kullanımlık</strong> bağlantı ile hesap açabilir.
        </p>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-[var(--radius-card)] bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger"
        >
          {error}
        </div>
      ) : null}

      {created?.invite_url ? (
        <TransientAlert
          tone="success"
          title="Davet bağlantısı oluşturuldu"
          duration={8000}
        >
          <span className="flex flex-wrap items-center gap-2">
            <code className="max-w-full truncate rounded bg-surface px-2 py-1 font-mono text-[11.5px] text-ink">
              {created.invite_url}
            </code>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => copyLink(created.invite_url!)}
            >
              {copied ? (
                <Check aria-hidden className="size-3.5" strokeWidth={2} />
              ) : (
                <Copy aria-hidden className="size-3.5" strokeWidth={2} />
              )}
              {copied ? "Kopyalandı" : "Kopyala"}
            </Button>
            <span className="text-[11.5px] text-ink-subtle">
              {formatDateTime(created.expires_at)} tarihine kadar geçerli, bir kez
              kullanılabilir.
            </span>
          </span>
        </TransientAlert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Yeni davet</CardTitle>
          <CardDescription>
            Davet yalnızca belirtilen e-posta adresiyle kabul edilebilir.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid items-end gap-4 md:grid-cols-[1.6fr_1fr_auto]">
          <Field label="E-posta" htmlFor="invite-email">
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="davetli@example.com"
              autoComplete="off"
            />
          </Field>
          <Field label="Geçerlilik" htmlFor="invite-ttl">
            <Select
              id="invite-ttl"
              value={ttl}
              onChange={(event) => setTtl(Number(event.target.value))}
            >
              <option value={12}>12 saat</option>
              <option value={24}>24 saat</option>
              <option value={48}>48 saat</option>
              <option value={168}>7 gün</option>
            </Select>
          </Field>
          <Button onClick={create} loading={creating} disabled={!email}>
            {creating ? null : (
              <MailPlus aria-hidden className="size-4" strokeWidth={2} />
            )}
            Davet oluştur
          </Button>
        </CardContent>
      </Card>

      {invitations.loading ? (
        <SkeletonRows rows={2} />
      ) : invitations.error ? (
        <Card>
          <ErrorState error={invitations.error} onRetry={invitations.refetch} />
        </Card>
      ) : !invitations.data || invitations.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={Link2}
            title="Henüz davet oluşturulmadı"
            description="İkinci kullanıcı için yukarıdan bir davet bağlantısı üretin."
          />
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Davetler</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {invitations.data.map((invitation) => (
                <li
                  key={invitation.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-control)] bg-surface-muted px-3.5 py-3"
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-[13px] font-medium text-ink">
                      {invitation.email}
                    </span>
                    <span className="text-[11.5px] text-ink-subtle">
                      Oluşturma {formatRelative(invitation.created_at)} · bitiş{" "}
                      {formatDateTime(invitation.expires_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={statusTones[invitation.status]}>
                      {statusLabels[invitation.status]}
                    </Badge>
                    {invitation.status === "pending" ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`${invitation.email} davetini iptal et`}
                        title="İptal et"
                        className="text-ink-muted pointer-hover:text-danger"
                        onClick={() => revoke(invitation.id)}
                      >
                        <Trash2 aria-hidden className="size-4" strokeWidth={1.5} />
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
