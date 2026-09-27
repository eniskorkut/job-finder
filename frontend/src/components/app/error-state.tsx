"use client";

import { RefreshCw, ServerCrash } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api";

export function ErrorState({
  error,
  onRetry,
  title = "Veri yüklenemedi",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const apiError =
    error instanceof ApiError ? error : null;
  const description =
    apiError?.message ?? "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.";

  return (
    <EmptyState
      icon={ServerCrash}
      title={title}
      description={description}
      action={
        onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <RefreshCw aria-hidden className="size-3.5" strokeWidth={2} />
            Tekrar dene
          </Button>
        ) : null
      }
    />
  );
}
