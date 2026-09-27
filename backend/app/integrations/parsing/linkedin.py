"""LinkedIn job alert parser.

The e-mail templates change often, so nothing here depends on a single exact
markup. The strategy is:

1. find every ``/jobs/view/`` link,
2. walk up to the smallest container that holds the card around that link,
3. read title / company / location from the card text using heuristics,
4. fall back to the URL slug, and label the posting
   ``insufficient_description`` when the alert only carried a snippet.

An alert that contains no job link is a valid "0 jobs" result, never an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from app.integrations.base import JobPostingCandidate, RawMessage
from app.integrations.parsing.dedupe import (
    linkedin_job_id,
    safe_public_url,
    title_from_slug,
    turkish_lower,
)
from app.integrations.parsing.mime import collapse_whitespace

JOB_LINK_RE = re.compile(
    r"https?://([a-z0-9-]+\.)*linkedin\.com/(?:comm/)?jobs/view/[^\s\"'<>)]+",
    re.IGNORECASE,
)
SLUG_RE = re.compile(
    r"linkedin\.com/(?:comm/)?jobs/view/(?P<slug>[^/?#\s\"'<>)]+)", re.IGNORECASE
)

TITLE_NOISE = {
    "view job",
    "view jobs",
    "see job",
    "apply",
    "apply now",
    "ilanı görüntüle",
    "ilani goruntule",
    "iş ilanını görüntüle",
    "is ilanini goruntule",
    "başvur",
    "basvur",
    "tüm ilanları gör",
    "tum ilanlari gor",
    "see all jobs",
    "kaydet",
    "save",
}

LINE_NOISE = {
    "linkedin",
    "premium",
    "unsubscribe",
    "abonelikten çık",
    "abonelikten cik",
    "e-posta tercihleri",
    "email preferences",
    "yardım",
    "help",
    "gizlilik",
    "privacy",
    "bu e-posta size ... gönderilmiştir",
    "sizin için",
    "for you",
    "yeni",
    "new",
    "günlük özet",
    "daily digest",
    "iş ilanı",
    "job alert",
    "job alerts",
    "iş ilanları",
    "is ilanlari",
    "linkedin'de görüntüle",
    "linkedin'de goruntule",
}

LOCATION_HINTS = (
    "turkiye",
    "türkiye",
    "turkey",
    "istanbul",
    "ankara",
    "izmir",
    "bursa",
    "antalya",
    "kocaeli",
    "adana",
    "konya",
    "gaziantep",
    "remote",
    "uzaktan",
    "hibrit",
    "hybrid",
    "onsite",
    "on-site",
    "ofis",
    "office",
    "avrupa",
    "europe",
    "amerika",
    "united states",
    "germany",
    "almanya",
    "netherlands",
    "hollanda",
    "united kingdom",
    "birleşik krallık",
)

HEADER_NOISE_RE = re.compile(
    r"(job alerts?|iş ilan|is ilan|new jobs?|yeni iş|yeni ilan|sizin için|size özel|"
    r"günlük özet|daily digest|recommended|for you|tüm ilan|see all|top job)",
    re.IGNORECASE,
)

SENTENCE_NOISE_RE = re.compile(
    r"(abonelik|unsubscribe|e-posta tercih|email preferences|gizlilik|privacy|"
    r"bağlantıyı görüntüle|view in browser|linkedin corporation|copyright|"
    r"bu e-posta|this email|yardım merkezi|help center)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedJob:
    title: str
    company: str
    location: str | None
    url: str | None
    job_id: str | None
    description: str | None
    description_status: str


class LinkedInAlertParser:
    provider = "linkedin"

    def __init__(self, *, min_description_chars: int = 120) -> None:
        self.min_description_chars = min_description_chars

    # ------------------------------------------------------------------
    def parse(self, message: RawMessage) -> list[JobPostingCandidate]:
        parsed: list[ParsedJob] = []
        parsed.extend(self._parse_html(message.body_html))
        if not parsed:
            parsed.extend(self._parse_text(message.body_text))
        return [self._to_candidate(job, message) for job in self._dedupe(parsed)]

    # ------------------------------------------------------------------
    def _parse_html(self, html: str | None) -> list[ParsedJob]:
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        jobs: list[ParsedJob] = []
        seen_slugs: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            if "jobs/view" not in href.lower():
                continue
            match = SLUG_RE.search(href)
            slug = match.group("slug") if match else None
            key = slug or href
            if key in seen_slugs:
                continue
            seen_slugs.add(key)
            job = self._job_from_anchor(anchor, href, slug)
            if job is not None:
                jobs.append(job)
        return jobs

    def _job_from_anchor(self, anchor: Tag, href: str, slug: str | None) -> ParsedJob | None:
        lines = self._container_lines(anchor)
        title = self._extract_title(anchor, lines, slug)
        if not title:
            return None

        fragments: list[str] = []
        for line in lines:
            fragments.extend(self._split_fragments(line))
        fragments = [fragment for fragment in fragments if not self._is_title(fragment, title)]

        company = self._extract_company(fragments)
        location = self._extract_location(fragments)

        if not company:
            company = self._company_from_slug(slug)

        body_lines = [
            fragment
            for fragment in fragments
            if fragment != company and fragment != location and not self._is_noise(fragment)
        ]
        description = collapse_whitespace("\n".join(body_lines)) or None
        status = "ok"
        if description is None or len(description) < self.min_description_chars:
            status = "insufficient_description"
            if description is None:
                description = None

        url = safe_public_url(self._clean_href(href))
        job_id = linkedin_job_id(url, slug)

        return ParsedJob(
            title=title,
            company=company or "Bilinmiyor",
            location=location,
            url=url,
            job_id=job_id,
            description=description,
            description_status=status,
        )

    # ------------------------------------------------------------------
    def _parse_text(self, text: str | None) -> list[ParsedJob]:
        """Fallback for ``text/plain`` only alerts."""
        if not text:
            return []
        jobs: list[ParsedJob] = []
        lines = [line.strip() for line in text.splitlines()]
        seen: set[str] = set()

        for index, line in enumerate(lines):
            link = JOB_LINK_RE.search(line)
            if link is None:
                continue
            href = link.group(0).rstrip(">),.")
            match = SLUG_RE.search(href)
            slug = match.group("slug") if match else None
            key = slug or href
            if key in seen:
                continue
            seen.add(key)

            # Up to three meaningful lines above the link, back in document
            # order: title / company / location (blank lines are skipped).
            collected: list[str] = []
            offset = 1
            while len(collected) < 3 and index - offset >= 0:
                candidate = self._line_at(lines, index - offset)
                offset += 1
                if not candidate or JOB_LINK_RE.search(candidate):
                    continue
                if self._is_noise(candidate):
                    continue
                collected.append(candidate)
            block = list(reversed(collected))
            title = None
            company = None
            location = None
            for candidate in block:
                if self._is_location(candidate) and location is None:
                    location = candidate
                elif title is None:
                    title = candidate
                elif company is None:
                    company = candidate
            if title is None:
                title = title_from_slug(slug)
            if not title:
                continue
            jobs.append(
                ParsedJob(
                    title=title,
                    company=company or self._company_from_slug(slug) or "Bilinmiyor",
                    location=location,
                    url=safe_public_url(href),
                    job_id=linkedin_job_id(href, slug),
                    description=None,
                    description_status="insufficient_description",
                )
            )
        return jobs

    @staticmethod
    def _line_at(lines: list[str], index: int) -> str | None:
        if 0 <= index < len(lines):
            value = lines[index].strip()
            return value or None
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _container_lines(anchor: Tag) -> list[str]:
        """Smallest ancestor that looks like a job card, as text lines."""
        best: list[str] = []
        node: Tag | None = anchor
        for _ in range(5):
            if node is None:
                break
            text = node.get_text("\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                break
            if 2 <= len(lines) <= 40 and len(text) < 1600:
                best = lines
                if len(lines) >= 3:
                    break
            node = node.parent if isinstance(node.parent, Tag) else None
        if not best:
            text = anchor.get_text("\n", strip=True)
            best = [line.strip() for line in text.splitlines() if line.strip()]
        return best

    @staticmethod
    def _extract_title(anchor: Tag, lines: list[str], slug: str | None) -> str | None:
        # Only the first line of the anchor: broken templates nest <p> inside it.
        anchor_lines = [
            line.strip()
            for line in anchor.get_text("\n", strip=True).splitlines()
            if line.strip()
        ]
        if anchor_lines:
            anchor_text = anchor_lines[0]
            if not LinkedInAlertParser._is_noise(anchor_text):
                cleaned = LinkedInAlertParser._clean_title(anchor_text)
                if cleaned:
                    return cleaned

        parent = anchor.parent if isinstance(anchor.parent, Tag) else None
        scope = parent or anchor
        for tag_name in ("h1", "h2", "h3", "h4", "strong", "b"):
            node = scope.find(tag_name)
            if node is not None:
                text = node.get_text(" ", strip=True)
                cleaned = LinkedInAlertParser._clean_title(text)
                if cleaned:
                    return cleaned

        for line in lines:
            cleaned = LinkedInAlertParser._clean_title(line)
            if cleaned and cleaned != line or (cleaned and len(cleaned.split()) >= 2):
                return cleaned
        return title_from_slug(slug)

    @staticmethod
    def _clean_title(value: str) -> str | None:
        text = " ".join(value.split())
        if not text or len(text) > 160:
            return None
        if LinkedInAlertParser._is_noise(text):
            return None
        if JOB_LINK_RE.search(text):
            return None
        if turkish_lower(text) in TITLE_NOISE:
            return None
        return text

    # ------------------------------------------------------------------
    @classmethod
    def _split_fragments(cls, line: str) -> list[str]:
        """Split on strong separators, then on commas unless the part is a
        location ("İstanbul, Türkiye" must survive intact)."""
        parts = re.split(r"\s*(?:·|\||•|—|–|;)\s*", line)
        fragments: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if cls._is_location(part):
                fragments.append(part)
                continue
            fragments.extend(
                piece.strip()
                for piece in re.split(r",(?=\s)", part)
                if piece and piece.strip()
            )
        return fragments

    @staticmethod
    def _is_noise(line: str) -> bool:
        lowered = turkish_lower(line)
        if not lowered:
            return True
        if lowered.strip(" .:-") in LINE_NOISE:
            return True
        if len(line) <= 90 and HEADER_NOISE_RE.search(line):
            return True
        if SENTENCE_NOISE_RE.search(line):
            return True
        if lowered.startswith(("http", "www.", "linkedin.com")):
            return True
        if re.fullmatch(r"[\W\d_]+", lowered):
            return True
        return False

    @staticmethod
    def _is_title(fragment: str, title: str) -> bool:
        return " ".join(fragment.split()).lower() == " ".join(title.split()).lower()

    def _extract_company(self, fragments: list[str]) -> str | None:
        for fragment in fragments:
            if self._is_noise(fragment) or len(fragment) > 120:
                continue
            if self._is_location(fragment):
                continue
            words = fragment.split()
            if not 1 <= len(words) <= 12:
                continue
            return fragment
        return None

    def _extract_location(self, fragments: list[str]) -> str | None:
        for fragment in fragments:
            if len(fragment) > 120 or self._is_noise(fragment):
                continue
            if self._is_location(fragment):
                return fragment
        return None

    @staticmethod
    def _is_location(value: str) -> bool:
        lowered = turkish_lower(value)
        return any(hint in lowered for hint in LOCATION_HINTS)

    @staticmethod
    def _company_from_slug(slug: str | None) -> str | None:
        if not slug:
            return None
        cleaned = re.sub(r"-\d{6,}$", "", slug)
        parts = cleaned.split("-at-")
        if len(parts) < 2:
            return None
        company = parts[-1].replace("-", " ").strip()
        if not company or len(company) > 100:
            return None
        return company.title()

    @staticmethod
    def _clean_href(href: str) -> str:
        return href.split("?")[0] if "?" not in href else href

    # ------------------------------------------------------------------
    @staticmethod
    def _dedupe(jobs: list[ParsedJob]) -> list[ParsedJob]:
        seen: set[str] = set()
        unique: list[ParsedJob] = []
        for job in jobs:
            key = job.job_id or job.url or turkish_lower(f"{job.title}|{job.company}")
            if key in seen:
                continue
            seen.add(key)
            unique.append(job)
        return unique

    @staticmethod
    def _to_candidate(job: ParsedJob, message: RawMessage) -> JobPostingCandidate:
        return JobPostingCandidate(
            title=job.title,
            company=job.company,
            location=job.location,
            url=job.url,
            description=job.description,
            external_id=job.job_id,
            raw_message=message,
            description_status=job.description_status,
        )
