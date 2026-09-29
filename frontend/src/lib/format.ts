const dateFormatter = new Intl.DateTimeFormat("tr-TR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("tr-TR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const relativeFormatter = new Intl.RelativeTimeFormat("tr-TR", {
  numeric: "auto",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return dateFormatter.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return dateTimeFormatter.format(date);
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  if (Math.abs(diffMinutes) < 60) {
    return relativeFormatter.format(diffMinutes, "minute");
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return relativeFormatter.format(diffHours, "hour");
  }
  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffDays) < 30) {
    return relativeFormatter.format(diffDays, "day");
  }
  return formatDate(value);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("tr-TR").format(value);
}

export const workModeLabels: Record<string, string> = {
  remote: "Uzaktan",
  hybrid: "Hibrit",
  onsite: "Ofis",
  unknown: "Belirtilmemiş",
};

export const sourceLabels: Record<string, string> = {
  mock: "Örnek veri",
  gmail: "Gmail",
  outlook: "Hotmail / Outlook",
  manual: "Elle eklendi",
};

export const statusLabels: Record<string, string> = {
  new: "Yeni",
  viewed: "İncelendi",
  saved: "Kaydedildi",
  dismissed: "Elendi",
  notified: "Bildirildi",
};

export const syncStatusLabels: Record<string, string> = {
  pending: "Bekliyor",
  running: "Sürüyor",
  success: "Başarılı",
  failed: "Başarısız",
  skipped: "Atlandı",
};

export const connectionStatusLabels: Record<string, string> = {
  disconnected: "Bağlı değil",
  pending: "Bekliyor",
  connected: "Bağlı",
  needs_reauth: "Yeniden yetki gerekli",
  error: "Hata",
};

export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return trimmed;
    }
  } catch {
    // ignore invalid URL
  }
  return null;
}

export const freshnessLabels: Record<string, string> = {
  fresh: "Taze (0-3g)",
  aging: "Güncel (4-7g)",
  stale: "Eski (8-14g)",
  expired: "Süresi doldu (>14g)",
  unknown: "Bilinmiyor",
};

export const freshnessVariants: Record<string, "success" | "warning" | "danger" | "muted"> = {
  fresh: "success",
  aging: "warning",
  stale: "warning",
  expired: "danger",
  unknown: "muted",
};

export const availabilityLabels: Record<string, string> = {
  active: "Yayında",
  closed: "Kapanmış",
  possibly_closed: "Muhtemelen kapandı (404)",
  removed: "Kaldırılmış (410)",
  unknown: "Bilinmiyor",
};

export const availabilityVariants: Record<string, "success" | "danger" | "muted" | "warning"> = {
  active: "success",
  closed: "danger",
  possibly_closed: "warning",
  removed: "danger",
  unknown: "muted",
};

export const enrichmentLabels: Record<string, string> = {
  enriched: "Zenginleştirildi",
  pending: "Zenginleştirme bekliyor",
  skipped: "Atlandı (Açıklama yeterli)",
  not_found: "Aday bulunamadı",
  failed: "Zenginleştirme hatası",
};

export const enrichmentVariants: Record<string, "accent" | "neutral" | "muted" | "danger"> = {
  enriched: "accent",
  pending: "neutral",
  skipped: "muted",
  not_found: "muted",
  failed: "danger",
};

export const sourceTypeLabels: Record<string, string> = {
  ats: "Resmi ATS",
  company_career: "Şirket Kariyer Sayfası",
  official_site: "Resmi Web Sitesi",
  external_job_board: "İlan Portalı",
  other: "Web Kaynağı",
};

