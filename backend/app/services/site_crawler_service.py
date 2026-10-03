"""Custom career websites and ATS crawler service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.parsing.dedupe import fingerprint_hash, normalize_url
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    LinkedInFetchForbiddenError,
    SafeWebFetcher,
    SSRFProtectionError,
    WebFetchError,
)
from app.models.enums import DescriptionStatus, WorkMode
from app.models.job import Job, JobMatch, JobWebSource
from app.models.user import User
from app.schemas.integration import (
    CrawlJobItem,
    CrawlSiteResponse,
    SiteVerificationItem,
    VerifySitesResponse,
)
from app.services.job_enrichment.html_parser import (
    ExtractedJobData,
    _find_job_postings_in_json,
    clean_html_content,
    extract_from_semantic_html,
    parse_iso_datetime,
)
from app.services.job_enrichment.url_utils import compute_content_hash, extract_domain

logger = logging.getLogger("jobhunter.site_crawler")


@dataclass
class CrawlFetchResult:
    success: bool
    url: str
    postings: list[ExtractedJobData]
    message: str
    is_transient: bool = False
    status_code: int | None = None


@dataclass
class _CandidatePosting:
    title: str
    company: str
    location: str | None
    description: str
    target_url: str
    normalized_target: str
    fingerprint: str
    post: ExtractedJobData


class SiteCrawlerService:
    def __init__(
        self,
        db: Session | None = None,
        fetcher: SafeWebFetcher | None = None,
    ) -> None:
        self.db = db
        self.fetcher = fetcher or SafeWebFetcher()

    @staticmethod
    def normalize_input_url(raw_url: str) -> str:
        cleaned = raw_url.strip()
        if not cleaned:
            return ""
        if not re.match(r"^https?://", cleaned, re.IGNORECASE):
            cleaned = "https://" + cleaned
        parts = urlsplit(cleaned)
        # Rebuild without fragment
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))

    async def fetch_and_parse(self, raw_url: str) -> CrawlFetchResult:
        """Phase 1: Fetch and parse postings without opening or holding any database transaction."""
        url = self.normalize_input_url(raw_url)
        if not url:
            return CrawlFetchResult(
                success=False,
                url=raw_url,
                postings=[],
                message="Geçerli bir URL adresi girilmedi.",
                is_transient=False,
            )

        try:
            fetch_result = await self.fetcher.fetch(url)
        except SSRFProtectionError as err:
            logger.warning("SSRF blocked URL: %s (%s)", url, err)
            return CrawlFetchResult(
                success=False,
                url=url,
                postings=[],
                message="Güvenlik nedeniyle bu adrese erişim engellendi (Yerel/Özel Ağ Koruması).",
                is_transient=False,
            )
        except LinkedInFetchForbiddenError:
            return CrawlFetchResult(
                success=False,
                url=url,
                postings=[],
                message="LinkedIn sayfalarının doğrudan taranması desteklenmemektedir.",
                is_transient=False,
            )
        except WebFetchError as err:
            logger.warning("Web fetch error for %s: %s", url, err)
            # Transient error if retryable status or network timeout
            is_transient = True
            return CrawlFetchResult(
                success=False,
                url=url,
                postings=[],
                message=f"Hedef siteye erişilemedi: {err}",
                is_transient=is_transient,
            )
        except Exception as err:
            logger.exception("Unexpected error fetching %s: %s", url, err)
            return CrawlFetchResult(
                success=False,
                url=url,
                postings=[],
                message=f"Beklenmeyen bir hata oluştu: {err}",
                is_transient=True,
            )

        if fetch_result.status_code != 200:
            is_transient = fetch_result.status_code in {408, 429, 500, 502, 503, 504}
            return CrawlFetchResult(
                success=False,
                url=url,
                postings=[],
                message=f"Hedef site HTTP {fetch_result.status_code} yanıtı döndürdü.",
                is_transient=is_transient,
                status_code=fetch_result.status_code,
            )

        extracted_postings = self.extract_all_postings(fetch_result.content, url)
        return CrawlFetchResult(
            success=True,
            url=url,
            postings=extracted_postings,
            message="Site başarıyla çekildi ve çözümlendi.",
            is_transient=False,
            status_code=200,
        )

    def persist_postings_batch(
        self,
        db: Session,
        user_id: uuid.UUID,
        url: str,
        postings: list[ExtractedJobData],
    ) -> CrawlSiteResponse:
        """Phase 2: Short-lived DB transaction with batch lookup and batch inserts."""
        if not postings:
            return CrawlSiteResponse(
                success=True,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message="Siteye başarıyla bağlanıldı (HTTP 200), ancak sayfada açık ilan formatı bulunamadı.",
            )

        domain = extract_domain(url) or "company"
        default_company = domain.split(".")[0].capitalize()

        candidates: list[_CandidatePosting] = []
        for post in postings:
            title = (post.title or "").strip()[:300]
            if not title:
                continue

            company = (post.company or default_company).strip()[:200]
            location = (post.location or "").strip()[:200] or None
            description = post.description or ""
            target_url = post.application_url or url
            normalized_target = normalize_url(target_url)

            fingerprint = fingerprint_hash(
                title=title,
                company=company,
                location=location,
                job_id=None,
            )

            candidates.append(
                _CandidatePosting(
                    title=title,
                    company=company,
                    location=location,
                    description=description,
                    target_url=target_url,
                    normalized_target=normalized_target,
                    fingerprint=fingerprint,
                    post=post,
                )
            )

        if not candidates:
            return CrawlSiteResponse(
                success=True,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message="Siteye başarıyla bağlanıldı (HTTP 200), ancak geçerli ilan başlığı bulunamadı.",
            )

        all_fingerprints = [c.fingerprint for c in candidates]
        all_normalized_urls = [c.normalized_target for c in candidates]

        # Batch lookup for existing jobs by fingerprint
        existing_by_fp = {
            j.fingerprint_hash: j
            for j in db.scalars(
                select(Job).where(
                    Job.user_id == user_id,
                    Job.fingerprint_hash.in_(all_fingerprints),
                )
            ).all()
            if j.fingerprint_hash
        }

        # Batch lookup for existing jobs by normalized url
        existing_by_url = {
            j.url_normalized: j
            for j in db.scalars(
                select(Job).where(
                    Job.user_id == user_id,
                    Job.url_normalized.in_(all_normalized_urls),
                )
            ).all()
            if j.url_normalized
        }

        created_jobs: list[CrawlJobItem] = []
        jobs_created_count = 0
        now = datetime.now(timezone.utc)

        new_jobs: list[Job] = []
        new_matches: list[JobMatch] = []
        new_sources: list[JobWebSource] = []

        for c in candidates:
            existing = existing_by_fp.get(c.fingerprint) or existing_by_url.get(c.normalized_target)

            if existing is None:
                jobs_created_count += 1
                job_id = uuid.uuid4()

                if c.post.date_posted:
                    posted_at = c.post.date_posted
                    posted_at_source = "web_crawler"
                    posted_at_confidence = "high"
                else:
                    posted_at = None
                    posted_at_source = "discovery_date"
                    posted_at_confidence = "low"

                desc_len = len(c.description)
                desc_status = (
                    DescriptionStatus.OK.value
                    if desc_len >= 100
                    else DescriptionStatus.INSUFFICIENT.value
                )

                job = Job(
                    id=job_id,
                    user_id=user_id,
                    source="official_ats",
                    title=c.title,
                    company=c.company,
                    location=c.location,
                    work_mode=c.post.work_mode or WorkMode.UNKNOWN.value,
                    employment_type=c.post.employment_type,
                    description=c.description,
                    url=c.target_url,
                    url_normalized=c.normalized_target,
                    canonical_url=c.target_url,
                    company_job_url=c.target_url,
                    source_url=url,
                    fingerprint_hash=c.fingerprint,
                    description_status=desc_status,
                    posted_at=posted_at,
                    posted_at_source=posted_at_source,
                    posted_at_confidence=posted_at_confidence,
                    freshness_status="active",
                    availability_status="active",
                    enrichment_status="enriched",
                    content_hash=compute_content_hash(c.description),
                    discovered_at=now,
                    is_mock=False,
                    raw_payload={
                        "source": "site_crawler",
                        "discovered_url": url,
                        "parser_source": c.post.parser_source,
                    },
                )
                new_jobs.append(job)
                # Register in mapping to prevent duplicates within the same batch
                existing_by_fp[c.fingerprint] = job
                existing_by_url[c.normalized_target] = job

                match = JobMatch(
                    user_id=user_id,
                    job_id=job_id,
                    score=None,
                    matched_skills=[],
                    missing_skills=[],
                    status="new",
                    is_mock=False,
                )
                new_matches.append(match)

                web_source = JobWebSource(
                    user_id=user_id,
                    job_id=job_id,
                    url=c.target_url,
                    normalized_url=c.normalized_target,
                    host=domain,
                    source_type="official_ats",
                    trust_level=90,
                    match_confidence="high",
                    title=c.title,
                    snippet=c.description[:200] if c.description else None,
                    http_status=200,
                    content_hash=compute_content_hash(c.description),
                    selected_as_canonical=True,
                )
                new_sources.append(web_source)

                created_jobs.append(
                    CrawlJobItem(
                        id=job_id,
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        url=job.url,
                        source=job.source,
                        is_new=True,
                    )
                )
            else:
                # Existing job: enrich description if it was insufficient
                if (
                    c.description
                    and len(c.description) > len(existing.description or "")
                    and existing.description_status == DescriptionStatus.INSUFFICIENT.value
                ):
                    existing.description = c.description
                    existing.description_status = DescriptionStatus.OK.value
                    existing.content_hash = compute_content_hash(c.description)

                created_jobs.append(
                    CrawlJobItem(
                        id=existing.id,
                        title=existing.title,
                        company=existing.company,
                        location=existing.location,
                        url=existing.url,
                        source=existing.source,
                        is_new=False,
                    )
                )

        if new_jobs:
            db.add_all(new_jobs)
        if new_matches:
            db.add_all(new_matches)
        if new_sources:
            db.add_all(new_sources)
        db.flush()

        msg = f"{len(candidates)} ilan tespit edildi; {jobs_created_count} yeni ilan sisteme eklendi."
        return CrawlSiteResponse(
            success=True,
            url=url,
            jobs_found=len(candidates),
            jobs_created=jobs_created_count,
            jobs=created_jobs,
            message=msg,
        )

    async def crawl_site(self, user: User, raw_url: str) -> CrawlSiteResponse:
        """Convenience method combining fetch_and_parse and persist_postings_batch."""
        fetch_res = await self.fetch_and_parse(raw_url)
        if not fetch_res.success:
            return CrawlSiteResponse(
                success=False,
                url=fetch_res.url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message=fetch_res.message,
            )

        if self.db is None:
            raise RuntimeError("Database session is required to persist crawled postings.")

        response = self.persist_postings_batch(
            self.db, user.id, fetch_res.url, fetch_res.postings
        )
        self.db.commit()
        return response

    def extract_all_postings(self, html: str, page_url: str) -> list[ExtractedJobData]:
        postings: list[ExtractedJobData] = []
        soup = BeautifulSoup(html, "html.parser")

        # 1. Search JSON-LD scripts
        scripts = soup.find_all("script", type=lambda t: t and "ld+json" in t.lower())
        for script in scripts:
            raw_text = script.string or script.text
            if not raw_text or not raw_text.strip():
                continue
            try:
                data = json.loads(raw_text)
                found = _find_job_postings_in_json(data)
                for jp in found:
                    title = jp.get("title") or jp.get("name")
                    if not title or not isinstance(title, str):
                        continue

                    raw_desc = jp.get("description")
                    cleaned_desc = clean_html_content(raw_desc) if raw_desc else None

                    date_posted = parse_iso_datetime(jp.get("datePosted"))
                    valid_through = parse_iso_datetime(jp.get("validThrough"))

                    company = None
                    org = jp.get("hiringOrganization")
                    if isinstance(org, dict):
                        company = org.get("name")
                    elif isinstance(org, str):
                        company = org

                    location = None
                    job_loc = jp.get("jobLocation")
                    if isinstance(job_loc, dict):
                        addr = job_loc.get("address")
                        if isinstance(addr, dict):
                            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                            location = ", ".join(p for p in parts if p)
                        elif isinstance(addr, str):
                            location = addr
                    elif isinstance(job_loc, list) and job_loc:
                        first_loc = job_loc[0]
                        if isinstance(first_loc, dict):
                            addr = first_loc.get("address")
                            if isinstance(addr, dict):
                                parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                                location = ", ".join(p for p in parts if p)

                    emp_type = jp.get("employmentType")
                    if isinstance(emp_type, list):
                        emp_type = ", ".join(str(e) for e in emp_type)
                    elif not isinstance(emp_type, str):
                        emp_type = None

                    work_mode = WorkMode.UNKNOWN.value
                    loc_type = jp.get("jobLocationType")
                    if loc_type and "telecommute" in str(loc_type).lower():
                        work_mode = WorkMode.REMOTE.value
                    elif jp.get("applicantLocationRequirements"):
                        work_mode = WorkMode.REMOTE.value

                    app_url = jp.get("directApply") or jp.get("url") or page_url
                    if isinstance(app_url, str):
                        app_url = app_url.strip()

                    postings.append(
                        ExtractedJobData(
                            title=title.strip(),
                            company=company.strip() if company else None,
                            description=cleaned_desc,
                            date_posted=date_posted,
                            valid_through=valid_through,
                            location=location,
                            employment_type=emp_type,
                            work_mode=work_mode,
                            application_url=app_url,
                            source_type="json_ld",
                            parser_source="json_ld",
                        )
                    )
            except Exception:
                continue

        if postings:
            return postings

        # 2. Semantic HTML fallback
        semantic = extract_from_semantic_html(html)
        if semantic and semantic.title:
            postings.append(semantic)
            return postings

        # 3. Job board listing items parser (Greenhouse, Lever, Workday, Ashby)
        listing_postings = self._extract_from_job_listings(soup, page_url)
        if listing_postings:
            return listing_postings

        return []

    def _extract_from_job_listings(self, soup: BeautifulSoup, page_url: str) -> list[ExtractedJobData]:
        extracted: list[ExtractedJobData] = []
        domain = extract_domain(page_url) or "company"
        default_company = domain.split(".")[0].capitalize()

        # Check common job board patterns
        candidates = soup.find_all(
            ["div", "li", "tr", "section", "article"],
            class_=lambda c: c and any(k in str(c).lower() for k in ["opening", "posting", "job-item", "career-item", "job_listing"]),
        )

        for c in candidates:
            # Find title
            heading = c.find(["h2", "h3", "h4", "h5", "a"])
            if not heading:
                continue
            title_text = heading.get_text().strip()
            if not title_text or len(title_text) < 4 or len(title_text) > 150:
                continue

            link_tag = c.find("a") if c.name != "a" else c
            href = link_tag.get("href") if link_tag else None
            app_url = urljoin(page_url, href) if href else page_url

            # Find location
            loc_tag = c.find(class_=lambda cls: cls and any(k in str(cls).lower() for k in ["location", "workplace", "city"]))
            location_text = loc_tag.get_text().strip() if loc_tag else None

            # Detect remote
            work_mode = WorkMode.UNKNOWN.value
            combined_text = c.get_text().lower()
            if "remote" in combined_text or "uzaktan" in combined_text:
                work_mode = WorkMode.REMOTE.value
            elif "hybrid" in combined_text or "hibrit" in combined_text:
                work_mode = WorkMode.HYBRID.value

            extracted.append(
                ExtractedJobData(
                    title=title_text,
                    company=default_company,
                    description=f"{title_text} pozisyonu {default_company} kariyer sayfasından aktarıldı.",
                    location=location_text,
                    work_mode=work_mode,
                    application_url=app_url,
                    source_type="semantic_html",
                    parser_source="ats_listing",
                )
            )

        return extracted

    async def verify_sites(self, sites: list[str]) -> VerifySitesResponse:
        results: list[SiteVerificationItem] = []
        active_count = 0
        concurrency = max(1, min(20, settings.site_verify_max_concurrency))
        semaphore = asyncio.Semaphore(concurrency)

        async def _check_one(raw_s: str) -> SiteVerificationItem:
            nonlocal active_count
            url = self.normalize_input_url(raw_s)
            if not url:
                return SiteVerificationItem(
                    site=raw_s,
                    status="error",
                    status_code=None,
                    jobs_found=0,
                    message="Geçersiz adres",
                )

            async with semaphore:
                try:
                    res = await self.fetcher.fetch(url)
                    if res.status_code == 200:
                        postings = self.extract_all_postings(res.content, url)
                        active_count += 1
                        return SiteVerificationItem(
                            site=raw_s,
                            status="ok",
                            status_code=200,
                            jobs_found=len(postings),
                            message=f"Bağlantı başarılı (HTTP 200), {len(postings)} ilan tespit edildi.",
                        )
                    else:
                        return SiteVerificationItem(
                            site=raw_s,
                            status="error",
                            status_code=res.status_code,
                            jobs_found=0,
                            message=f"HTTP {res.status_code}",
                        )
                except SSRFProtectionError:
                    return SiteVerificationItem(
                        site=raw_s,
                        status="error",
                        status_code=None,
                        jobs_found=0,
                        message="Güvenlik engeli (Özel Ağ)",
                    )
                except Exception as err:
                    return SiteVerificationItem(
                        site=raw_s,
                        status="error",
                        status_code=None,
                        jobs_found=0,
                        message=str(err),
                    )

        tasks = [_check_one(s) for s in sites if s.strip()]
        if tasks:
            results = await asyncio.gather(*tasks)

        msg = f"{len(results)} kaynaktan {active_count} tanesi aktif ve erişilebilir."
        return VerifySitesResponse(
            success=True,
            total_checked=len(results),
            active_sites=active_count,
            results=results,
            message=msg,
        )
