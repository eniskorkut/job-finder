"use client";

import { useEffect, useState } from "react";
import { Plus, Save, X } from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { TransientAlert } from "@/components/app/transient-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApiQuery } from "@/lib/hooks";
import type { Preferences } from "@/lib/types";

const workModeOptions = [
  { value: "remote", label: "Uzaktan" },
  { value: "hybrid", label: "Hibrit" },
  { value: "onsite", label: "Ofis" },
];

function ChipInput({
  values,
  onChange,
  placeholder,
  id,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
  id: string;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const value = draft.trim();
    if (!value) return;
    if (!values.includes(value)) onChange([...values, value]);
    setDraft("");
  }

  return (
    <div className="flex flex-col gap-2">
      {values.length ? (
        <div className="flex flex-wrap gap-1.5">
          {values.map((value) => (
            <span
              key={value}
              className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-[12px] text-ink"
            >
              {value}
              <button
                type="button"
                onClick={() => onChange(values.filter((item) => item !== value))}
                aria-label={`${value} kaldır`}
                className="text-ink-subtle transition-[color] duration-150 ease-out pointer-hover:text-danger"
              >
                <X aria-hidden className="size-3" strokeWidth={2} />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <Input
          id={id}
          value={draft}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === ",") {
              event.preventDefault();
              commit();
            }
          }}
        />
        <Button variant="secondary" size="icon" onClick={commit} aria-label="Ekle">
          <Plus aria-hidden className="size-4" strokeWidth={2} />
        </Button>
      </div>
    </div>
  );
}

function SegmentedControl({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: string; label: string }[];
  value: string[];
  onChange: (value: string[]) => void;
  label: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex rounded-[var(--radius-card)] bg-surface-muted p-1"
    >
      {options.map((option) => {
        const active = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() =>
              onChange(
                active
                  ? value.filter((item) => item !== option.value)
                  : [...value, option.value],
              )
            }
            className={cn(
              // concentric: 16px outer - 4px padding = 12px inner
              "rounded-[12px] px-3 py-1.5 text-[12.5px] font-medium",
              "transition-[background-color,color,scale] duration-150 ease-out active:scale-[0.96]",
              active
                ? "bg-surface text-ink shadow-[var(--shadow-card)]"
                : "text-ink-muted pointer-hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function PreferencesForm() {
  const preferences = useApiQuery<Preferences>("/api/v1/preferences");
  const [draft, setDraft] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<
    { tone: "success" | "danger"; message: string } | null
  >(null);

  useEffect(() => {
    if (preferences.data) setDraft(preferences.data);
  }, [preferences.data]);

  async function save() {
    if (!draft) return;
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await api.put<Preferences>("/api/v1/preferences", {
        desired_titles: draft.desired_titles,
        locations: draft.locations,
        work_modes: draft.work_modes,
        keywords_include: draft.keywords_include,
        keywords_exclude: draft.keywords_exclude,
        min_match_score: draft.min_match_score,
        daily_scan_enabled: draft.daily_scan_enabled,
        scan_interval_hours: draft.scan_interval_hours,
        notify_telegram: draft.notify_telegram,
      });
      preferences.setData(updated);
      setDraft(updated);
      setFeedback({ tone: "success", message: "Tercihler kaydedildi." });
    } catch (error) {
      setFeedback({
        tone: "danger",
        message:
          error instanceof ApiError ? error.message : "Tercihler kaydedilemedi.",
      });
    } finally {
      setSaving(false);
    }
  }

  if (preferences.loading || !draft) {
    return (
      <Card className="p-5">
        <div className="flex flex-col gap-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-2/3" />
        </div>
      </Card>
    );
  }

  if (preferences.error) {
    return (
      <Card>
        <ErrorState error={preferences.error} onRetry={preferences.refetch} />
      </Card>
    );
  }

  function patch(partial: Partial<Preferences>) {
    setDraft((prev) => (prev ? { ...prev, ...partial } : prev));
  }

  return (
    <div className="flex flex-col gap-5">
      {feedback ? (
        <TransientAlert tone={feedback.tone} title={feedback.message} />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Pozisyon tercihleri</CardTitle>
          <CardDescription>
            Bu başlıklar 2. aşamada gelen e-postaların filtrelenmesinde
            kullanılacak.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <Field
            label="Hedef pozisyonlar"
            hint="Enter ile ekleyin. Örn: AI Engineer"
            htmlFor="desired-titles"
          >
            <ChipInput
              id="desired-titles"
              values={draft.desired_titles}
              onChange={(values) => patch({ desired_titles: values })}
              placeholder="Pozisyon ekle…"
            />
          </Field>
          <Field
            label="Lokasyonlar"
            hint="Örn: İstanbul, Remote"
            htmlFor="locations"
          >
            <ChipInput
              id="locations"
              values={draft.locations}
              onChange={(values) => patch({ locations: values })}
              placeholder="Lokasyon ekle…"
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Çalışma modeli ve eşleşme</CardTitle>
          <CardDescription>
            Dashboard'daki "yüksek eşleşmeli ilan" sayısı bu eşik değeri
            kullanır.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <Field label="Çalışma modeli" htmlFor="work-modes">
            <SegmentedControl
              label="Çalışma modeli"
              options={workModeOptions}
              value={draft.work_modes}
              onChange={(values) => patch({ work_modes: values })}
            />
          </Field>

          <Field
            label={`Minimum eşleşme puanı: ${draft.min_match_score}`}
            hint="Bu puanın altındaki ilanlar bildirilmez."
            htmlFor="min-score"
          >
            <div className="flex items-center gap-3">
              <input
                id="min-score"
                type="range"
                min={0}
                max={100}
                step={5}
                value={draft.min_match_score}
                onChange={(event) =>
                  patch({ min_match_score: Number(event.target.value) })
                }
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-muted accent-[var(--accent)]"
              />
              <Badge variant="accent" className="tabular w-12 justify-center">
                {draft.min_match_score}
              </Badge>
            </div>
          </Field>

          <div className="grid gap-5 md:grid-cols-2">
            <Field label="Dahil edilecek kelimeler" htmlFor="keywords-include">
              <ChipInput
                id="keywords-include"
                values={draft.keywords_include}
                onChange={(values) => patch({ keywords_include: values })}
                placeholder="Örn: Python"
              />
            </Field>
            <Field label="Hariç tutulacak kelimeler" htmlFor="keywords-exclude">
              <ChipInput
                id="keywords-exclude"
                values={draft.keywords_exclude}
                onChange={(values) => patch({ keywords_exclude: values })}
                placeholder="Örn: satış"
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tarama ve bildirim</CardTitle>
          <CardDescription>
            Otomatik tarama, worker süreci içindeki zamanlayıcı ile çalışır
            (en sık 1 saatte bir). Eşik üstü yeni eşleşmeler Telegram&apos;a gönderilir.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-[13px] font-medium text-ink">
                Günlük otomatik tarama
              </span>
              <span className="text-[12px] text-ink-subtle">
                İlk tarama, kaydettiğiniz anda bir aralık sonrası için planlanır;
                hemen taramak için &quot;Şimdi Tara&quot; düğmesini kullanın.
              </span>
            </div>
            <Switch
              label="Günlük otomatik tarama"
              checked={draft.daily_scan_enabled}
              onCheckedChange={(value) => patch({ daily_scan_enabled: value })}
            />
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-[13px] font-medium text-ink">
                Telegram bildirimi
              </span>
              <span className="text-[12px] text-ink-subtle">
                Eşik üstü eşleşmeler kendi botunuz üzerinden gönderilir.
              </span>
            </div>
            <Switch
              label="Telegram bildirimi"
              checked={draft.notify_telegram}
              onCheckedChange={(value) => patch({ notify_telegram: value })}
            />
          </div>

          <Field
            label="Tarama sıklığı"
            hint="Kaynak servisleri yormamak için istekler arasında beklenecek süre uygulanır."
            htmlFor="scan-interval"
          >
            <Select
              id="scan-interval"
              value={draft.scan_interval_hours}
              onChange={(event) =>
                patch({ scan_interval_hours: Number(event.target.value) })
              }
            >
              <option value={1}>Saatte bir (en sık)</option>
              <option value={3}>3 saatte bir</option>
              <option value={6}>6 saatte bir</option>
              <option value={12}>12 saatte bir</option>
              <option value={24}>Günde bir</option>
              <option value={48}>2 günde bir</option>
              <option value={168}>Haftada bir</option>
            </Select>
          </Field>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        <Button variant="secondary" onClick={() => setDraft(preferences.data)}>
          Geri al
        </Button>
        <Button onClick={save} loading={saving}>
          {saving ? null : <Save aria-hidden className="size-4" strokeWidth={2} />}
          Kaydet
        </Button>
      </div>
    </div>
  );
}
