"""Sender / subject filters for job alert e-mails.

Defaults target LinkedIn job alerts without hard-coding a single sender address:
the domain ``linkedin.com`` matches every regional sender, and the subject list
covers the Turkish and English phrasings. Users can replace both lists per
mailbox from the integrations screen.
"""

from __future__ import annotations

from app.integrations.parsing.dedupe import turkish_lower

DEFAULT_SENDERS: tuple[str, ...] = ("linkedin.com",)
DEFAULT_SUBJECTS: tuple[str, ...] = (
    "iş ilanı",
    "is ilani",
    "job alert",
    "job alerts",
    "iş fırsatı",
    "is firsati",
    "hiring",
    "new jobs",
)

MAX_FILTER_TERMS = 25
MAX_TERM_LENGTH = 120


def default_filters(provider: str) -> dict[str, list[str]]:
    return {"senders": list(DEFAULT_SENDERS), "subjects": list(DEFAULT_SUBJECTS)}


def sanitize_filters(raw: dict | None) -> dict[str, list[str]]:
    """Normalize user supplied filters; absence never means "match everything"."""
    raw = raw or {}
    senders = _clean_terms(raw.get("senders"))
    subjects = _clean_terms(raw.get("subjects"))
    if not senders and not subjects:
        return default_filters("")
    return {"senders": senders, "subjects": subjects}


def _clean_terms(value: object) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        return []
    seen: list[str] = []
    for item in items[:MAX_FILTER_TERMS]:
        term = item[:MAX_TERM_LENGTH]
        if term.lower() not in {existing.lower() for existing in seen}:
            seen.append(term)
    return seen


def matches_sender(sender: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    haystack = turkish_lower(sender or "")
    return any(turkish_lower(pattern) in haystack for pattern in patterns)


def matches_subject(subject: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = turkish_lower(subject or "")
    return any(turkish_lower(keyword) in haystack for keyword in keywords)


def message_matches(
    *, sender: str, subject: str, filters: dict | None
) -> tuple[bool, str | None]:
    """Return ``(matches, skip_reason)``."""
    resolved = sanitize_filters(filters)
    if not matches_sender(sender, resolved["senders"]):
        return False, "sender_filtered"
    if not matches_subject(subject, resolved["subjects"]):
        return False, "subject_filtered"
    return True, None
