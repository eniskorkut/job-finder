"""Telegram message rendering.

HTML parse mode is used because escaping is unambiguous, and the message is
kept short: score, company, location, skills, a trimmed rationale and a link.
"""

from __future__ import annotations

import html

from app.core.config import settings
from app.models.job import Job, JobMatch

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


def build_match_message(
    *,
    job: Job,
    match: JobMatch,
    score_threshold: int | None = None,
    site_url: str | None = None,
) -> str:
    title = truncate(job.title, 120)
    company = truncate(job.company, 80)
    location = truncate(job.location or "Belirtilmemiş", 80)
    work_mode = {
        "remote": "Uzaktan",
        "hybrid": "Hibrit",
        "onsite": "Ofis",
        "unknown": "Belirtilmemiş",
    }.get(job.work_mode, job.work_mode)

    lines: list[str] = [
        f"{score_emoji(match.score)} <b>{escape(title)}</b> — %{match.score or 0} eşleşme",
        "",
        f"<b>Şirket:</b> {escape(company)}",
        f"<b>Lokasyon:</b> {escape(location)} / {escape(work_mode)}",
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

    if job.url and job.url.startswith("https://"):
        lines += ["", f'<a href="{escape(job.url)}">İlanı aç</a>']

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
