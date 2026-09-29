"""Source trust classification, ATS detection, and title similarity matching."""

from __future__ import annotations

import difflib
import re
import unicodedata
from urllib.parse import urlsplit

from app.services.job_enrichment.url_utils import extract_domain

# Known ATS patterns: (domain regex or suffix, trust_level, source_name)
ATS_PATTERNS = [
    (re.compile(r"(?:boards|job-boards)\.greenhouse\.io$", re.IGNORECASE), 95, "Greenhouse"),
    (re.compile(r"jobs\.lever\.co$", re.IGNORECASE), 95, "Lever"),
    (re.compile(r".*\.myworkdayjobs\.com$", re.IGNORECASE), 90, "Workday"),
    (re.compile(r"jobs\.smartrecruiters\.com$", re.IGNORECASE), 90, "SmartRecruiters"),
    (re.compile(r"jobs\.ashbyhq\.com$", re.IGNORECASE), 90, "Ashby"),
    (re.compile(r".*\.teamtailor\.com$", re.IGNORECASE), 85, "Teamtailor"),
    (re.compile(r"apply\.workable\.com$", re.IGNORECASE), 85, "Workable"),
    (re.compile(r".*\.breezy\.hr$", re.IGNORECASE), 85, "Breezy HR"),
    (re.compile(r".*\.bamboohr\.com$", re.IGNORECASE), 85, "BambooHR"),
    (re.compile(r"jobs\.jobvite\.com$", re.IGNORECASE), 85, "Jobvite"),
    (re.compile(r"recruiting\.ultipro\.com$", re.IGNORECASE), 85, "UKG"),
    (re.compile(r".*\.icims\.com$", re.IGNORECASE), 85, "iCIMS"),
]

AGGREGATOR_PATTERNS = [
    re.compile(r".*\b(?:indeed|glassdoor|ziprecruiter|monster|careerbuilder|kariyer|yenibiris)\.[a-z]+$", re.IGNORECASE),
]


def normalize_text_for_match(text: str | None) -> str:
    """Normalize text by folding Turkish characters, dropping diacritics, and stripping punctuation."""
    if not text:
        return ""
    table = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "Ğ": "g", "Ü": "u", "Ö": "o", "Ç": "c"})
    folded = text.translate(table).lower()
    decomposed = unicodedata.normalize("NFKD", folded)
    cleaned = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Replace non-alphanumeric with spaces
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def classify_source(url: str, company: str | None = None) -> tuple[str, int, str]:
    """Classify a URL into (source_type, trust_level, provenance_label).
    source_type is one of: "ats", "official", "aggregator", "unknown".
    """
    host = extract_domain(url)
    if not host:
        return "unknown", 0, "Unknown"

    # 1. ATS detection
    for pattern, trust, name in ATS_PATTERNS:
        if pattern.search(host):
            return "ats", trust, name

    # 2. Aggregators
    for pattern in AGGREGATOR_PATTERNS:
        if pattern.search(host):
            return "aggregator", 40, "Aggregator"

    # 3. Official company site heuristic
    if company:
        norm_company = normalize_text_for_match(company)
        company_tokens = [t for t in norm_company.split() if t not in {"inc", "corp", "llc", "ltd", "gmbh", "co", "ai", "tech"}]
        norm_host = re.sub(r"[^a-z0-9]", "", host.split(".")[0])
        # Direct match or token match
        if norm_company and (norm_company.replace(" ", "") in norm_host or norm_host in norm_company.replace(" ", "")):
            return "official", 90, company.strip()
        for token in company_tokens:
            if len(token) >= 4 and token in host:
                return "official", 85, company.strip()

    # Path check: careers/jobs
    try:
        path = urlsplit(url).path.lower()
        if any(keyword in path for keyword in ["career", "careers", "job", "jobs", "apply"]):
            return "official", 75, "Official Site"
    except Exception:
        pass

    return "unknown", 30, host


def compute_string_similarity(str1: str, str2: str) -> float:
    """Compute token-set aware string similarity between 0.0 and 1.0."""
    norm1 = normalize_text_for_match(str1)
    norm2 = normalize_text_for_match(str2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0

    # SequenceMatcher ratio
    seq_ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()

    # Token set Jaccard
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    if not tokens1 or not tokens2:
        jaccard = 0.0
    else:
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)

    return max(seq_ratio, jaccard)


def calculate_match_confidence(
    expected_title: str,
    extracted_title: str | None,
    expected_company: str,
    extracted_company: str | None,
    source_type: str = "unknown",
) -> str:
    """Calculate match confidence: 'high', 'medium', 'low', 'none'."""
    if not extracted_title:
        return "none"

    title_sim = compute_string_similarity(expected_title, extracted_title)

    company_sim = 0.0
    if extracted_company:
        company_sim = compute_string_similarity(expected_company, extracted_company)
    elif source_type in {"ats", "official"}:
        company_sim = 0.8  # Bonus if found directly on official/ATS source

    if title_sim >= 0.80 and company_sim >= 0.60:
        return "high"
    elif title_sim >= 0.70 or (title_sim >= 0.60 and source_type == "ats"):
        return "high"
    elif title_sim >= 0.55:
        return "medium"
    elif title_sim >= 0.35:
        return "low"
    return "none"
