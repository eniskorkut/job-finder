"""URL manipulation and LinkedIn URL utilities for job discovery."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LINKEDIN_JOB_ID_RE = re.compile(r"(?P<id>\d{6,})")
LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com"}

TRACKING_PREFIXES = (
    "trk",
    "tracking",
    "ref",
    "lipi",
    "midtoken",
    "midsig",
    "trkinfo",
    "src",
    "ut",
    "utm_",
)

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
    "fbclid",
    "gclid",
    "msclkid",
}


def extract_domain(url: str | None) -> str | None:
    """Extract normalized lowercase host from URL without www prefix."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        if not host:
            return None
        host = host.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return None


def is_linkedin_url(url: str | None) -> bool:
    """Check if the given URL belongs to LinkedIn."""
    if not url:
        return False
    host = extract_domain(url)
    if not host:
        return False
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def extract_linkedin_job_id(url: str | None, slug: str | None = None) -> str | None:
    """Extract the numerical LinkedIn job id from a URL, path, or query string."""
    for candidate in (slug, url):
        if not candidate:
            continue
        try:
            parts = urlsplit(candidate.strip())
            # Check path segments
            path_segments = [s for s in parts.path.split("/") if s]
            for segment in reversed(path_segments):
                match = LINKEDIN_JOB_ID_RE.search(segment)
                if match:
                    return match.group("id")
            # Check query params
            if parts.query:
                query = dict(parse_qsl(parts.query))
                for key, val in query.items():
                    if key.lower() in {"currentjobid", "jobid", "id"} and val.isdigit() and len(val) >= 6:
                        return val
        except Exception:
            # Fallback regex on raw candidate
            match = LINKEDIN_JOB_ID_RE.search(candidate)
            if match:
                return match.group("id")
    return None


def normalize_linkedin_job_url(url: str | None, job_id: str | None = None) -> str | None:
    """Produce the standard public canonical LinkedIn job URL:
    https://www.linkedin.com/jobs/view/{job_id}/
    """
    effective_id = job_id or extract_linkedin_job_id(url)
    if effective_id:
        return f"https://www.linkedin.com/jobs/view/{effective_id}/"
    if url and is_linkedin_url(url):
        return normalize_url(url)
    return None


def normalize_url(url: str | None) -> str | None:
    """Drop tracking parameters and fragments, preserve canonical URL."""
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
        and not any(key.lower().startswith(p) for p in TRACKING_PREFIXES)
    ]
    query = urlencode(kept)
    return urlunsplit(("https", host, path, query, ""))


def compute_content_hash(text: str | None) -> str | None:
    """Calculate SHA-256 hash of normalized text for deduplication/change detection."""
    if not text:
        return None
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def is_specific_job_url(url: str | None) -> bool:
    """Check if the URL path or query indicates a specific job posting rather than a general directory or board root."""
    if not url:
        return False
    try:
        parts = urlsplit(url)
        path = parts.path.lower()
        host = (parts.hostname or "").lower()
        if re.search(r"/(?:jobs?|position|posting|role|o)/[a-zA-Z0-9_\-]+", path):
            return True
        if re.search(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", path):
            return True
        segments = [s for s in path.strip("/").split("/") if s]
        if any(ats in host for ats in ("ashbyhq.com", "lever.co", "workable.com", "greenhouse.io")) and len(segments) >= 2:
            return True
        if parts.query and any(k.lower() in {"gh_jid", "job_id", "jobid", "jid"} for k, _ in parse_qsl(parts.query)):
            return True
        return False
    except Exception:
        return False


