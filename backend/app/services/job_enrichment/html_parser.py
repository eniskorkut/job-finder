"""HTML and JSON-LD JobPosting parser."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger("jobhunter.html_parser")

EXPIRED_PATTERNS = [
    re.compile(r"this job (?:is|has been) (?:closed|expired|filled)", re.IGNORECASE),
    re.compile(r"no longer accepting applications", re.IGNORECASE),
    re.compile(r"position (?:is|has been) closed", re.IGNORECASE),
    re.compile(r"job posting has expired", re.IGNORECASE),
    re.compile(r"ilan (?:yayından|kaldırıldı|kapanmıştır|kapandı)", re.IGNORECASE),
    re.compile(r"bu ilan artık aktif değil", re.IGNORECASE),
    re.compile(r"başvuru süresi dolmuştur", re.IGNORECASE),
]


@dataclass(slots=True)
class ExtractedJobData:
    title: str | None = None
    company: str | None = None
    description: str | None = None
    date_posted: datetime | None = None
    valid_through: datetime | None = None
    location: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    application_url: str | None = None
    source_type: str = "none"  # "json_ld" | "semantic_html" | "none"
    parser_source: str = "unknown"  # "json_ld" | "semantic_html" | "unknown"
    is_closed: bool = False
    raw_json_ld: dict | None = None


def parse_iso_datetime(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 string to timezone-aware UTC datetime."""
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned = date_str.strip()
    try:
        # Standard fromisoformat handles +00:00, Z (in 3.11+), etc.
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        # Fallback date only: YYYY-MM-DD
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", cleaned)
        if m:
            try:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(year, month, day, tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def clean_html_content(raw_html_or_text: str | None) -> str | None:
    """Convert HTML or raw text into clean, safe text without script/style tags."""
    if not raw_html_or_text:
        return None
    soup = BeautifulSoup(raw_html_or_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()

    # Replace breaks and paragraph tags with newlines
    for br in soup.find_all(["br", "p", "div", "li", "tr"]):
        br.append("\n")

    text = soup.get_text()
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned if cleaned.strip() else None


def check_is_closed(text: str | None) -> bool:
    """Check if the text indicates the job is closed or no longer accepting applications."""
    if not text:
        return False
    for pattern in EXPIRED_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _find_job_postings_in_json(obj: Any) -> list[dict]:
    """Recursively search for JobPosting objects in a JSON-LD structure."""
    found: list[dict] = []
    if isinstance(obj, dict):
        obj_type = obj.get("@type")
        if isinstance(obj_type, str) and "jobposting" in obj_type.lower():
            found.append(obj)
        elif isinstance(obj_type, list) and any("jobposting" in str(t).lower() for t in obj_type):
            found.append(obj)
        if "@graph" in obj and isinstance(obj["@graph"], list):
            found.extend(_find_job_postings_in_json(obj["@graph"]))
        for value in obj.values():
            if isinstance(value, (dict, list)):
                found.extend(_find_job_postings_in_json(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_job_postings_in_json(item))
    return found


def extract_from_json_ld(
    html: str,
    expected_title: str | None = None,
    expected_company: str | None = None,
) -> ExtractedJobData | None:
    """Extract JobPosting structured data from application/ld+json scripts.
    If multiple JobPostings are found, selects the best matching posting.
    """
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type=lambda t: t and "ld+json" in t.lower())

    all_postings: list[dict] = []
    for script in scripts:
        raw_text = script.string or script.text
        if not raw_text or not raw_text.strip():
            continue
        try:
            data = json.loads(raw_text)
        except Exception:
            continue

        job_postings = _find_job_postings_in_json(data)
        all_postings.extend(job_postings)

    if not all_postings:
        return None

    # If multiple postings, rank by title & company similarity
    if len(all_postings) > 1 and (expected_title or expected_company):
        def _score_jp(jp: dict) -> float:
            score = 0.0
            t = (jp.get("title") or jp.get("name") or "").lower()
            org = jp.get("hiringOrganization")
            c = ""
            if isinstance(org, dict):
                c = (org.get("name") or "").lower()
            elif isinstance(org, str):
                c = org.lower()

            if expected_title:
                et = expected_title.lower()
                if et in t or t in et:
                    score += 2.0
                else:
                    t_toks = set(re.findall(r"\w+", t))
                    et_toks = set(re.findall(r"\w+", et))
                    if t_toks and et_toks:
                        score += (len(t_toks & et_toks) / len(et_toks)) * 2.0

            if expected_company:
                ec = expected_company.lower()
                if ec in c or c in ec:
                    score += 1.5

            desc = jp.get("description") or ""
            if len(desc) > 100:
                score += 0.5
            return score

        all_postings.sort(key=_score_jp, reverse=True)

    jp = all_postings[0]

    title = jp.get("title") or jp.get("name")
    raw_desc = jp.get("description")
    cleaned_desc = clean_html_content(raw_desc) if raw_desc else None

    date_posted = parse_iso_datetime(jp.get("datePosted"))
    valid_through = parse_iso_datetime(jp.get("validThrough"))

    # Company
    company = None
    org = jp.get("hiringOrganization")
    if isinstance(org, dict):
        company = org.get("name")
    elif isinstance(org, str):
        company = org

    # Location
    location = None
    job_loc = jp.get("jobLocation")
    if isinstance(job_loc, dict):
        addr = job_loc.get("address")
        if isinstance(addr, dict):
            loc_parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
            location = ", ".join(p for p in loc_parts if p)
        elif isinstance(addr, str):
            location = addr
    elif isinstance(job_loc, list) and job_loc:
        first_loc = job_loc[0]
        if isinstance(first_loc, dict):
            addr = first_loc.get("address")
            if isinstance(addr, dict):
                loc_parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                location = ", ".join(p for p in loc_parts if p)

    # Employment type
    emp_type = jp.get("employmentType")
    if isinstance(emp_type, list):
        emp_type = ", ".join(str(e) for e in emp_type)
    elif not isinstance(emp_type, str):
        emp_type = None

    # Work mode
    work_mode = None
    loc_type = jp.get("jobLocationType")
    if loc_type and "telecommute" in str(loc_type).lower():
        work_mode = "remote"
    elif jp.get("applicantLocationRequirements"):
        work_mode = "remote"
    elif cleaned_desc and any(w in cleaned_desc.lower()[:300] for w in ["100% remote", "fully remote", "tamamen uzaktan"]):
        work_mode = "remote"

    # Application / Direct Apply URL
    application_url = None
    app_url = jp.get("directApply") or jp.get("url")
    if isinstance(app_url, str) and app_url.startswith("http"):
        application_url = app_url.strip()

    is_closed = False
    if valid_through and valid_through < datetime.now(timezone.utc):
        is_closed = True
    elif check_is_closed(cleaned_desc):
        is_closed = True

    return ExtractedJobData(
        title=title.strip() if title else None,
        company=company.strip() if company else None,
        description=cleaned_desc,
        date_posted=date_posted,
        valid_through=valid_through,
        location=location,
        employment_type=emp_type,
        work_mode=work_mode,
        application_url=application_url,
        source_type="json_ld",
        parser_source="json_ld",
        is_closed=is_closed,
        raw_json_ld=jp,
    )


def extract_from_semantic_html(html: str) -> ExtractedJobData | None:
    """Fallback extraction using semantic HTML elements, OpenGraph meta, and time tags."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()

    raw_html_title = soup.title.string.strip() if (soup.title and soup.title.string) else ""

    # Check for board index patterns (e.g. "Jobs at Cadence Solutions", "Careers at ...")
    # A page whose title is "Jobs at <Company>" or "Careers at <Company>" is a board index, NOT a job posting
    if raw_html_title and re.search(r"^(?:jobs|careers|open positions|open roles|opportunities)\s+(?:at|in)\s+", raw_html_title, re.IGNORECASE):
        if not re.search(r"^job application for\s+", raw_html_title, re.IGNORECASE):
            return None

    # Title: og:title -> twitter:title -> <title>
    title = None
    company = None
    og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    # Extract company from og:site_name or meta author/company
    og_site_name = soup.find("meta", property="og:site_name") or soup.find("meta", attrs={"name": "og:site_name"})
    if og_site_name and og_site_name.get("content"):
        company = og_site_name["content"].strip()
    elif not company:
        author_meta = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"name": "company"})
        if author_meta and author_meta.get("content"):
            company = author_meta["content"].strip()

    # Extract from raw HTML title if available
    if raw_html_title:
        m_app = re.search(r"job application for\s+(?P<t>.+?)\s+at\s+(?P<c>[^|\-–—]+)", raw_html_title, re.IGNORECASE)
        if m_app:
            if not company:
                company = m_app.group("c").strip()
            if not title or title.lower() in raw_html_title.lower():
                title = m_app.group("t").strip()
        else:
            m_at = re.search(r"(?P<t>.+?)\s+at\s+(?P<c>[^|\-–—]+)", raw_html_title, re.IGNORECASE)
            if m_at and not raw_html_title.lower().startswith(("jobs at", "careers at")):
                if not company:
                    company = m_at.group("c").strip()
                if not title:
                    title = m_at.group("t").strip()
            elif not title:
                title = raw_html_title

    # Clean site suffix from title (e.g. "Senior Python Engineer - Google Careers")
    if title:
        title = re.split(r"\s+[|\-–—]\s+", title)[0].strip()

    # If title still starts with "Jobs at" or "Careers at", this is a directory page, not a job posting
    if title and re.search(r"^(?:jobs|careers|open positions|open roles)\s+at\s+", title, re.IGNORECASE):
        return None

    # Date posted
    date_posted = None
    date_meta = (
        soup.find("meta", property="article:published_time")
        or soup.find("meta", attrs={"name": "pubdate"})
        or soup.find("meta", attrs={"name": "publish-date"})
        or soup.find("meta", attrs={"name": "date"})
    )
    if date_meta and date_meta.get("content"):
        date_posted = parse_iso_datetime(date_meta["content"])

    if not date_posted:
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            date_posted = parse_iso_datetime(time_tag["datetime"])

    # Description container
    desc_el = (
        soup.find(attrs={"itemprop": "description"})
        or soup.find("div", class_=lambda c: c and any(k in str(c).lower() for k in ["job-description", "jobdescription", "posting-description", "job_description"]))
        or soup.find("section", class_=lambda c: c and any(k in str(c).lower() for k in ["job-description", "jobdescription", "description"]))
        or soup.find("article")
        or soup.find("main")
    )

    cleaned_desc = None
    if desc_el:
        for br in desc_el.find_all(["br", "p", "div", "li", "tr"]):
            br.append("\n")
        text = desc_el.get_text()
        lines = [line.strip() for line in text.splitlines()]
        cleaned_desc = "\n".join(line for line in lines if line)

    is_closed = check_is_closed(cleaned_desc) or check_is_closed(soup.get_text())

    # Remote detection
    work_mode = None
    full_text = ((title or "") + " " + (cleaned_desc or "")).lower()
    if any(k in full_text[:400] for k in ["remote", "uzaktan", "telecommute", "work from home"]):
        work_mode = "remote"

    if not title and not cleaned_desc:
        return None

    return ExtractedJobData(
        title=title,
        company=None,
        description=cleaned_desc,
        date_posted=date_posted,
        valid_through=None,
        location=None,
        employment_type=None,
        work_mode=work_mode,
        application_url=None,
        source_type="semantic_html",
        parser_source="semantic_html",
        is_closed=is_closed,
        raw_json_ld=None,
    )


def extract_job_posting(
    html: str,
    expected_title: str | None = None,
    expected_company: str | None = None,
) -> ExtractedJobData | None:
    """Main entrypoint: attempt JSON-LD first, fallback to semantic HTML."""
    if not html or not html.strip():
        return None
    try:
        json_ld_data = extract_from_json_ld(
            html,
            expected_title=expected_title,
            expected_company=expected_company,
        )
        if json_ld_data and json_ld_data.description and len(json_ld_data.description) >= 60:
            return json_ld_data
    except Exception as exc:
        logger.debug("JSON-LD ayrıştırma hatası: %s", exc)

    try:
        return extract_from_semantic_html(html)
    except Exception as exc:
        logger.debug("Semantik HTML ayrıştırma hatası: %s", exc)
        return None
