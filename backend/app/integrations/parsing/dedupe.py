"""Deduplication helpers.

Priority, per the phase 2 contract:

1. stable LinkedIn job id,
2. normalized real job URL,
3. fingerprint of title + company + location.

Nothing here ever looks across users: keys are always scoped by ``user_id`` at
the repository layer.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LINKEDIN_JOB_ID_RE = re.compile(r"(?P<id>\d{6,})")
TRACKING_PREFIXES = ("trk", "tracking", "ref", "lipi", "midtoken", "midsig", "trkinfo", "src", "ut")
TRACKING_PARAMS = {
    "currentjobid",
    "eid",
    "ebfg",
    "origin",
    "originalsubdomain",
    "position",
    "pagenum",
    "trackingid",
    "refid",
    "savedsearchid",
    "trk",
    "trkinfo",
    "lipi",
    "midtoken",
    "midsig",
    "recommendedflushonload",
    "alternatechannel",
    "jobssearch",
    "searchid",
    "ut",
    "src",
}


def turkish_lower(value: str) -> str:
    """Lowercase with Turkish dotted/dotless I handled, then drop diacritics."""
    table = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "Ğ": "g", "Ü": "u", "Ö": "o", "Ç": "c"})
    folded = value.translate(table).lower()
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_url(url: str | None) -> str | None:
    """Drop tracking parameters and fragments, keep the real posting URL."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None

    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in {80, 443}:
        host = f"{host}:{parts.port}"

    path = re.sub(r"/+$", "", parts.path) or "/"
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in TRACKING_PARAMS
        and not key.lower().startswith(TRACKING_PREFIXES)
    ]
    query = urlencode(kept)
    return urlunsplit(("https", host, path, query, ""))


def linkedin_job_id(url: str | None, slug: str | None = None) -> str | None:
    """Extract the stable LinkedIn job id from a URL or slug."""
    for candidate in (slug, url):
        if not candidate:
            continue
        tail = candidate.rstrip("/").rsplit("/", 1)[-1]
        tail = tail.split("?")[0]
        match = LINKEDIN_JOB_ID_RE.search(tail)
        if match:
            return match.group("id")
    if url and "currentjobid=" in url.lower():
        query = dict(parse_qsl(urlsplit(url).query))
        for key, value in query.items():
            if key.lower() == "currentjobid" and value.isdigit():
                return value
    return None


def title_from_slug(slug: str | None) -> str | None:
    """Last resort title: ``senior-ai-engineer-at-novatech-4012345678``."""
    if not slug:
        return None
    value = slug.rstrip("/").split("?")[0]
    value = re.sub(r"-\d{6,}$", "", value)
    value = value.replace("-at-", " @ ")
    words = [word for word in re.split(r"[-_\s]+", value) if word]
    if len(words) < 2:
        return None
    return " ".join(word.capitalize() for word in words)


def fingerprint_hash(
    *, title: str, company: str, location: str | None, job_id: str | None = None
) -> str:
    """Stable per-posting fingerprint used when neither id nor URL is available."""
    basis = job_id or "|".join(
        [
            turkish_lower(" ".join(title.split())),
            turkish_lower(" ".join(company.split())),
            turkish_lower(" ".join((location or "").split())),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def safe_public_url(url: str | None) -> str | None:
    """Only https links are surfaced as clickable links to the user."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return None
    return url
