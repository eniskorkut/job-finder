"""Telegram message rendering with freshness and official provenance links.

HTML parse mode is used because escaping is unambiguous, and the message is
structured: score, company, location, freshness, skills, a trimmed rationale,
official application link, and LinkedIn navigation link.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from app.core.config import settings
from app.models.job import Job, JobMatch
from app.services.job_enrichment.url_utils import is_linkedin_url

NO_HIRING_DISCLAIMER = (
    "Bu puan işe alınma ihtimali değildir; CV ile ilan gereksinimlerinin "
    "uyum derecesini gösterir."
)


def escape(value: str | None) -> str:
    return html.escape(value or "", quote=False)


def truncate(value: str | None, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def score_emoji(score: int | None) -> str:
    if score is None:
        return "⚪"
    if score >= 85:
        return "🎯"
    if score >= 70:
        return "✅"
    if score >= 50:
        return "🔸"
    return "🔹"


def format_relative_date(dt: datetime | None, now: datetime | None = None) -> str:
    """Format relative date in Turkish (e.g. 'Bugün (yeni)', 'Dün', '3 gün önce')."""
    if dt is None:
        return "Belirtilmemiş"
    current_time = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = current_time - dt
    days = diff.days
    if days <= 0:
        hours = max(0, int(diff.total_seconds() // 3600))
        if hours <= 1:
            return "Bugün (yeni)"
        return f"Bugün ({hours} saat önce)"
    elif days == 1:
        return "Dün"
    elif days < 30:
        return f"{days} gün önce"
    elif days < 365:
        months = max(1, days // 30)
        return f"{months} ay önce"
    return f"{max(1, days // 365)} yıl önce"


def build_match_message(
    *,
    job: Job,
    match: JobMatch,
    score_threshold: int | None = None,
    site_url: str | None = None,
    now: datetime | None = None,
) -> str:
    title = truncate(job.title, 120)
    company = truncate(job.company, 80)
    location = truncate(job.location or "Belirtilmemiş", 80)
    job_work_mode = getattr(job, "work_mode", "unknown") or "unknown"
    work_mode = {
        "remote": "Uzaktan",
        "hybrid": "Hibrit",
        "onsite": "Ofis",
        "unknown": "Belirtilmemiş",
    }.get(job_work_mode, job_work_mode)

    freshness_val = getattr(job, "freshness_status", "unknown") or "unknown"
    freshness_label = {
        "fresh": "🟢 Taze (Son 3 gün)",
        "aging": "🟡 4-7 gün önce",
        "stale": "🟠 1-2 hafta önce",
        "expired": "🔴 Süresi geçmiş",
        "unknown": "⚪ Belirtilmemiş",
    }.get(freshness_val, "⚪ Belirtilmemiş")

    rel_posted = format_relative_date(getattr(job, "posted_at", None), now=now)

    lines: list[str] = [
        f"{score_emoji(match.score)} <b>{escape(title)}</b> — %{match.score or 0} eşleşme",
        "",
        f"<b>Şirket:</b> {escape(company)}",
        f"<b>Lokasyon:</b> {escape(location)} / {escape(work_mode)}",
        f"<b>Yayın / Güncellik:</b> {escape(rel_posted)} · {freshness_label}",
    ]

    if match.confidence is not None:
        lines.append(f"<b>Güven:</b> %{match.confidence}")

    matched = [truncate(skill, 40) for skill in (match.matched_skills or [])][:8]
    missing = [truncate(skill, 40) for skill in (match.missing_skills or [])][:8]
    if matched:
        lines += ["", f"<b>Eşleşen:</b> {escape(' · '.join(matched))}"]
    if missing:
        lines.append(f"<b>Eksik:</b> {escape(' · '.join(missing))}")

    rationale = truncate(match.rationale, 420)
    if rationale:
        lines += ["", f"<b>Değerlendirme:</b>\n{escape(rationale)}"]

    if match.insufficient_information:
        lines += ["", "⚠️ İlan metni kısıtlı olduğu için değerlendirme sınırlıdır."]

    # Link buttons/links: Official ATS/Company first, LinkedIn navigation second (HTTPS only)
    link_parts: list[str] = []
    app_link = (
        getattr(job, "application_url", None)
        or getattr(job, "company_job_url", None)
        or getattr(job, "canonical_url", None)
    )
    if app_link and app_link.startswith("https://"):
        link_parts.append(f'<a href="{escape(app_link)}">Resmi Başvuru Sayfası</a>')

    job_url = getattr(job, "url", None)
    li_link = getattr(job, "linkedin_url", None) or (job_url if (job_url and is_linkedin_url(job_url)) else None)
    if li_link and li_link.startswith("https://"):
        link_parts.append(f'<a href="{escape(li_link)}">LinkedIn İlanı</a>')
    elif job_url and job_url.startswith("https://") and job_url != app_link:
        link_parts.append(f'<a href="{escape(job_url)}">Kaynak İlan</a>')

    if link_parts:
        lines += ["", " · ".join(link_parts)]

    if score_threshold is not None:
        lines += ["", f"<i>Eşik: %{score_threshold} · {escape(NO_HIRING_DISCLAIMER)}</i>"]
    else:
        lines += ["", f"<i>{escape(NO_HIRING_DISCLAIMER)}</i>"]

    message = "\n".join(lines)
    limit = settings.telegram_max_message_chars
    if len(message) > limit:
        message = message[: limit - 1].rstrip() + "…"
    return message


def build_test_message(*, username: str | None) -> str:
    who = f"@{truncate(username, 40)}" if username else "botunuz"
    return (
        "✅ <b>Job Hunter bağlantı testi</b>\n\n"
        f"{escape(who)} üzerinden bildirim gönderimi çalışıyor.\n"
        "Eşleşme puanı eşiğin üzerinde olan ilanlar bu sohbete düşecek."
    )


def build_detect_hint(*, bot_username: str | None) -> str:
    bot = f"@{truncate(bot_username, 40)}" if bot_username else "botunuza"
    return (
        f"Telegram'da {escape(bot)} hesabına <code>/start</code> yazın, "
        "ardından \"Chat ID'yi algıla\" düğmesine basın."
    )
