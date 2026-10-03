import type { Job, JobDetail } from "@/lib/types";
import { resolveCityFromLocation } from "./city-coordinates";
import type { Dossier } from "./types";

export function mapJobToDossier(job: Job | JobDetail): Dossier {
  const city = resolveCityFromLocation(job.location);

  let scoreText = "Uyum Hesaplanıyor";
  if (job.match && typeof job.match.score === "number") {
    scoreText = `${Math.round(job.match.score)}% CV UYUMU`;
  }

  let freshnessText = "GÜNCEL";
  if (job.freshness_status === "fresh") {
    freshnessText = "YENİ EKLENDİ";
  } else if (job.freshness_status === "aging") {
    freshnessText = "GÜNCEL";
  } else if (job.freshness_status === "stale") {
    freshnessText = "ARŞİVDE";
  }

  let workModeLabel = "Ofis";
  if (job.work_mode === "remote") workModeLabel = "Uzaktan Çalışma";
  else if (job.work_mode === "hybrid") workModeLabel = "Hibrit";
  else if (job.work_mode === "onsite") workModeLabel = "Ofiste";

  let sourceLabel = "Resmi ATS Kaynağı";
  if (job.source === "gmail") sourceLabel = "Gmail İş Alarmı";
  else if (job.source === "outlook") sourceLabel = "Outlook İş Alarmı";
  else if (job.source === "official_ats") sourceLabel = "Resmi ATS";
  else if (job.source === "mock") sourceLabel = "Örnek Veri";

  let telegramText = "Telegram Beklemede";
  if (job.match?.status === "notified" || job.match?.notified_at) {
    telegramText = "Telegram Bildirimi İletildi";
  }

  const skills: string[] = [];
  if (job.match?.matched_skills && Array.isArray(job.match.matched_skills)) {
    skills.push(...job.match.matched_skills);
  }

  const appUrl =
    job.application_url ||
    job.canonical_url ||
    job.company_job_url ||
    job.url ||
    job.linkedin_url ||
    "";

  return {
    id: job.id,
    title: job.title,
    company: job.company,
    location: job.location || "Konum bilinmiyor",
    salary: job.salary_text || "Belirtilmemiş",
    score: scoreText,
    ref: `REF-${job.id.slice(0, 6).toUpperCase()}`,
    freshness: freshnessText,
    analysis:
      job.description ||
      "Özel kariyer kaynağından aktarılan iş ilanı detayları.",
    skills,
    tier: workModeLabel,
    source: sourceLabel,
    telegram: telegramText,
    cityKey: city.key,
    cityName: city.name,
    application_url: appUrl,
  };
}
