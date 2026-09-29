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


LEGAL_SUFFIXES = {
    "inc", "corp", "corporation", "llc", "ltd", "limited", "as", "a.s", "gmbh",
    "company", "co", "technology", "technologies", "holding", "group", "ve", "and", "the",
}

GENERIC_TOKENS = {
    "ai", "tech", "global", "jobs", "careers", "career", "job", "app", "dev",
    "cloud", "solutions", "services", "digital", "consulting", "international", "holding",
}


def extract_ats_tenant(url: str) -> str | None:
    """Extract company/tenant identifier from known ATS URLs."""
    try:
        parsed = urlsplit(url)
        host = (parsed.netloc or "").lower().split(":")[0]
        path_parts = [p for p in parsed.path.split("/") if p]
    except Exception:
        return None

    # boards.greenhouse.io/{tenant}/... or job-boards.greenhouse.io/{tenant}/...
    if "greenhouse.io" in host:
        return path_parts[0] if path_parts else None

    # jobs.lever.co/{tenant}/...
    if "lever.co" in host:
        return path_parts[0] if path_parts else None

    # {tenant}.myworkdayjobs.com/...
    if "myworkdayjobs.com" in host:
        return host.split(".myworkdayjobs.com")[0].split(".")[-1]

    # {tenant}.teamtailor.com/...
    if "teamtailor.com" in host:
        return host.split(".teamtailor.com")[0].split(".")[-1]

    # {tenant}.bamboohr.com/...
    if "bamboohr.com" in host:
        return host.split(".bamboohr.com")[0].split(".")[-1]

    # {tenant}.breezy.hr/...
    if "breezy.hr" in host:
        return host.split(".breezy.hr")[0].split(".")[-1]

    # jobs.smartrecruiters.com/{tenant}/...
    if "smartrecruiters.com" in host:
        return path_parts[0] if path_parts else None

    # apply.workable.com/{tenant}/...
    if "workable.com" in host:
        return path_parts[0] if path_parts else None

    # jobs.ashbyhq.com/{tenant}/...
    if "ashbyhq.com" in host:
        return path_parts[0] if path_parts else None

    return None


def classify_source(url: str, company: str | None = None) -> tuple[str, int, str]:
    """Classify a URL into (source_type, trust_level, provenance_label).
    source_type is one of: "ats", "official", "aggregator", "unknown".

    Official requires a strong company-domain relationship. Path alone (/jobs/)
    never makes an unknown domain official.
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
        company_tokens = [t for t in norm_company.split() if t not in LEGAL_SUFFIXES]
        # Meaningful tokens excluding generic industry words
        distinct_tokens = [t for t in company_tokens if t not in GENERIC_TOKENS and len(t) >= 3]

        # Extract base domain label (e.g. openai from careers.openai.com or openai.com)
        host_parts = host.lower().split(".")
        base_label = host_parts[-2] if len(host_parts) >= 2 else host_parts[0]

        is_official = False
        trust_val = 85

        # Direct match with company name or distinct company token
        core_unified = "".join(company_tokens)
        if core_unified and core_unified == base_label:
            is_official = True
            trust_val = 90
        elif distinct_tokens:
            for token in distinct_tokens:
                if token == base_label or (len(token) >= 4 and f"{token}." in host):
                    is_official = True
                    trust_val = 90
                    break

        if is_official:
            try:
                path = urlsplit(url).path.lower()
                if any(keyword in path for keyword in ["career", "careers", "job", "jobs", "apply"]) or "careers" in host or "jobs" in host:
                    trust_val = 95
            except Exception:
                pass
            return "official", trust_val, company.strip()

    # Path check without company domain match is UNKNOWN (never official!)
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
    url: str | None = None,
) -> str:
    """Calculate match confidence: 'high', 'medium', 'low', 'none'."""
    if not extracted_title:
        return "none"

    title_sim = compute_string_similarity(expected_title, extracted_title)
    if title_sim < 0.40:
        return "none"

    company_sim = 0.0
    if extracted_company:
        company_sim = compute_string_similarity(expected_company, extracted_company)
    elif url:
        tenant = extract_ats_tenant(url)
        if tenant:
            tenant_sim = compute_string_similarity(expected_company, tenant)
            if tenant_sim >= 0.60:
                company_sim = tenant_sim
        elif source_type == "official":
            company_sim = 0.85

    # Wrong company: if extracted company is present and similarity is low, penalize
    if extracted_company and company_sim < 0.35:
        return "low" if title_sim >= 0.75 else "none"

    # High confidence: requires high title AND verified company identity
    if title_sim >= 0.75 and company_sim >= 0.60:
        return "high"

    # High title match but missing/unverified company identity -> medium maximum!
    if title_sim >= 0.70:
        return "medium"

    if title_sim >= 0.55:
        return "medium" if company_sim >= 0.50 else "low"

    if title_sim >= 0.40:
        return "low"

    return "none"
