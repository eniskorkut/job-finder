"use client";

import { useRef, useState } from "react";
import {
  AlertTriangle,
  Download,
  Eye,
  FileText,
  ScanText,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { ErrorState } from "@/components/app/error-state";
import { TransientAlert } from "@/components/app/transient-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import type { CV, CVPreview } from "@/lib/types";

const ACCEPTED = ".pdf,.doc,.docx,.txt,.md";

export function CVManager() {
  const cvs = useApiQuery<CV[]>("/api/v1/cvs");
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [feedback, setFeedback] = useState<
    { tone: "success" | "danger"; message: string } | null
  >(null);
  const [preview, setPreview] = useState<CVPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);

  async function upload(file: File) {
    setUploading(true);
    setFeedback(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      await api.upload<CV>("/api/v1/cvs", formData);
      cvs.refetch();
      setFeedback({ tone: "success", message: `${file.name} yüklendi.` });
    } catch (error) {
      setFeedback({
        tone: "danger",
        message:
          error instanceof ApiError ? error.message : "Dosya yüklenemedi.",
      });
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function activate(cv: CV) {
    try {
      await api.patch<CV>(`/api/v1/cvs/${cv.id}`, { is_active: true });
      cvs.refetch();
    } catch (error) {
      setFeedback({
        tone: "danger",
        message: error instanceof ApiError ? error.message : "Güncellenemedi.",
      });
    }
  }

  async function openPreview(cv: CV) {
    setPreviewLoading(cv.id);
    setFeedback(null);
    try {
      const data = await api.get<CVPreview>(`/api/v1/cvs/${cv.id}/preview`);
      setPreview(data);
    } catch (error) {
      setFeedback({
        tone: "danger",
        message: error instanceof ApiError ? error.message : "Metin okunamadı.",
      });
    } finally {
      setPreviewLoading(null);
    }
  }

  async function remove(cv: CV) {
    try {
      await api.delete(`/api/v1/cvs/${cv.id}`);
      cvs.refetch();
      setFeedback({ tone: "success", message: `${cv.filename} silindi.` });
    } catch (error) {
      setFeedback({
        tone: "danger",
        message: error instanceof ApiError ? error.message : "Silinemedi.",
      });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>CV dosyaları</CardTitle>
        <CardDescription>
          PDF, DOC, DOCX, TXT veya MD. En fazla 10 MB. Metin çıkarımı ve
          otomatik skorlama 2. ve 3. aşamada eklenecek.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {feedback ? (
          <TransientAlert
            tone={feedback.tone}
            title={feedback.message}
          />
        ) : null}

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files?.[0];
            if (file) void upload(file);
          }}
          className={cn(
            "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] px-4 py-8 text-center",
            "border border-dashed transition-[background-color,border-color] duration-150 ease-out",
            dragging
              ? "border-accent bg-accent-soft"
              : "border-line-strong bg-surface-muted",
          )}
        >
          <UploadCloud
            aria-hidden
            className="size-5 text-ink-subtle"
            strokeWidth={1.5}
          />
          <p className="text-[13px] text-ink-muted">
            CV dosyanızı buraya sürükleyin veya
          </p>
          <Button
            variant="secondary"
            size="sm"
            loading={uploading}
            onClick={() => inputRef.current?.click()}
          >
            Dosya seç
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className="sr-only"
            aria-label="CV dosyası seç"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
        </div>

        {cvs.loading ? (
          <SkeletonRows rows={2} />
        ) : cvs.error ? (
          <ErrorState error={cvs.error} onRetry={cvs.refetch} />
        ) : !cvs.data || cvs.data.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="Henüz CV yüklenmedi"
            description="Eşleştirme puanları aktif CV üzerinden hesaplanacak."
          />
        ) : (
          <ul className="stagger flex flex-col gap-2">
            {cvs.data.map((cv) => (
              <li
                key={cv.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-control)] bg-surface-muted px-3.5 py-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    aria-hidden
                    className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-inner)] bg-surface text-ink-muted shadow-[var(--shadow-card)]"
                  >
                    <FileText className="size-4" strokeWidth={1.5} />
                  </span>
                  <div className="flex min-w-0 flex-col">
                    <span className="flex items-center gap-2 truncate text-[13px] font-medium text-ink">
                      {cv.filename}
                      {cv.is_active ? (
                        <Badge variant="success">Aktif</Badge>
                      ) : (
                        <Badge variant="muted">Arşiv</Badge>
                      )}
                    </span>
                    <span className="truncate text-[11.5px] text-ink-subtle">
                      {formatBytes(cv.size_bytes)} · {formatDateTime(cv.created_at)} ·{" "}
                      {extractionLabels[cv.extraction_status] ?? cv.extraction_status}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <a
                    href={`/api/v1/cvs/${cv.id}/download`}
                    className="inline-flex size-8 items-center justify-center rounded-[var(--radius-control)] text-ink-muted transition-[background-color,color,scale] duration-150 ease-out active:scale-[0.96] pointer-hover:bg-surface pointer-hover:text-ink"
                    aria-label={`${cv.filename} indir`}
                    title="İndir"
                  >
                    <Download aria-hidden className="size-4" strokeWidth={1.5} />
                  </a>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={previewLoading === cv.id}
                    onClick={() => openPreview(cv)}
                  >
                    <Eye aria-hidden className="size-3.5" strokeWidth={1.75} />
                    Metni gör
                  </Button>
                  {cv.is_active ? null : (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => activate(cv)}
                    >
                      Aktif yap
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(cv)}
                    aria-label={`${cv.filename} sil`}
                    title="Sil"
                    className="text-ink-muted pointer-hover:text-danger"
                  >
                    <Trash2 aria-hidden className="size-4" strokeWidth={1.5} />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {preview ? (
          <div className="flex flex-col gap-2 rounded-[var(--radius-card)] bg-surface-muted p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-[12.5px] font-medium text-ink">
                <ScanText aria-hidden className="size-3.5" strokeWidth={2} />
                {preview.filename} · çıkarılan metin
              </span>
              <span className="flex items-center gap-2">
                <Badge
                  variant={
                    preview.extraction_status === "ok"
                      ? "success"
                      : preview.extraction_status === "failed"
                        ? "danger"
                        : "warning"
                  }
                >
                  {extractionLabels[preview.extraction_status] ?? preview.extraction_status}
                </Badge>
                <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>
                  Kapat
                </Button>
              </span>
            </div>

            <span className="tabular text-[11.5px] text-ink-subtle">
              {preview.character_count} karakter · {preview.line_count} satır ·
              metin yalnızca sizin hesabınızda saklanır
            </span>

            {preview.extraction_warning ? (
              <p className="flex items-start gap-2 rounded-[var(--radius-control)] bg-warning-soft px-3 py-2 text-[12px] leading-5 text-warning">
                <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
                {preview.extraction_warning}
              </p>
            ) : null}

            {preview.has_extracted_text ? (
              <pre className="max-h-72 overflow-auto rounded-[var(--radius-control)] bg-surface p-3 font-mono text-[11.5px] leading-5 whitespace-pre-wrap text-ink shadow-[var(--shadow-card)]">
                {preview.text}
              </pre>
            ) : (
              <p className="text-[12px] text-ink-subtle">
                Bu dosyadan metin çıkarılamadı.
              </p>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

const extractionLabels: Record<string, string> = {
  ok: "metin çıkarıldı",
  ocr_required: "OCR gerekli",
  unsupported: "desteklenmeyen biçim",
  empty: "metin boş",
  failed: "çıkarım başarısız",
  pending: "metin çıkarılmadı",
};
