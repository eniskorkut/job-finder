"""Custom career websites and ATS crawler service."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

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


class SiteCrawlerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.fetcher = SafeWebFetcher()

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

    async def crawl_site(self, user: User, raw_url: str) -> CrawlSiteResponse:
        url = self.normalize_input_url(raw_url)
        if not url:
            return CrawlSiteResponse(
                success=False,
                url=raw_url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message="Geçerli bir URL adresi girilmedi.",
            )

        try:
            fetch_result = await self.fetcher.fetch(url)
        except SSRFProtectionError as err:
            logger.warning("SSRF blocked URL: %s (%s)", url, err)
            return CrawlSiteResponse(
                success=False,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message="Güvenlik nedeniyle bu adrese erişim engellendi (Yerel/Özel Ağ Koruması).",
            )
        except LinkedInFetchForbiddenError:
            return CrawlSiteResponse(
                success=False,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message="LinkedIn sayfalarının doğrudan taranması desteklenmemektedir.",
            )
        except WebFetchError as err:
            logger.warning("Web fetch error for %s: %s", url, err)
            return CrawlSiteResponse(
                success=False,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message=f"Hedef siteye erişilemedi: {err}",
            )
        except Exception as err:
            logger.exception("Unexpected error fetching %s: %s", url, err)
            return CrawlSiteResponse(
                success=False,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message=f"Beklenmeyen bir hata oluştu: {err}",
            )

        if fetch_result.status_code != 200:
            return CrawlSiteResponse(
                success=False,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message=f"Hedef site HTTP {fetch_result.status_code} yanıtı döndürdü.",
            )

        extracted_postings = self.extract_all_postings(fetch_result.content, url)
        if not extracted_postings:
            return CrawlSiteResponse(
                success=True,
                url=url,
                jobs_found=0,
                jobs_created=0,
                jobs=[],
                message="Siteye başarıyla bağlanıldı (HTTP 200), ancak sayfada açık ilan formatı bulunamadı.",
            )

        created_jobs: list[CrawlJobItem] = []
        jobs_created_count = 0
        now = datetime.now(timezone.utc)
        domain = extract_domain(url) or "company"
        default_company = domain.split(".")[0].capitalize()

        for post in extracted_postings:
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

            # Check if job already exists for this user
            existing = self.db.scalars(
                select(Job).where(
                    Job.user_id == user.id,
                    Job.fingerprint_hash == fingerprint,
                )
            ).first()

            is_new = False
            if existing is None:
                # Also check normalized URL
                existing = self.db.scalars(
                    select(Job).where(
                        Job.user_id == user.id,
                        Job.url_normalized == normalized_target,
                    )
                ).first()

            if existing is None:
                is_new = True
                jobs_created_count += 1
                job = Job(
                    user_id=user.id,
                    source="official_ats",
                    title=title,
                    company=company,
                    location=location,
                    work_mode=post.work_mode or WorkMode.UNKNOWN.value,
                    employment_type=post.employment_type,
                    description=description,
                    url=target_url,
                    url_normalized=normalized_target,
                    canonical_url=target_url,
                    company_job_url=target_url,
                    source_url=url,
                    fingerprint_hash=fingerprint,
                    description_status=DescriptionStatus.OK.value if len(description) >= 100 else DescriptionStatus.INSUFFICIENT.value,
                    posted_at=post.date_posted or now,
                    posted_at_source="web_crawler",
                    posted_at_confidence="high",
                    freshness_status="active",
                    availability_status="available",
                    enrichment_status="enriched",
                    content_hash=compute_content_hash(description),
                    discovered_at=now,
                    is_mock=False,
                    raw_payload={
                        "source": "site_crawler",
                        "discovered_url": url,
                        "parser_source": post.parser_source,
                    },
                )
                self.db.add(job)
                self.db.flush()

                # Create JobMatch
                match = JobMatch(
                    user_id=user.id,
                    job_id=job.id,
                    score=None,
                    matched_skills=[],
                    missing_skills=[],
                    status="new",
                    is_mock=False,
                )
                self.db.add(match)

                # Add JobWebSource
                web_source = JobWebSource(
                    user_id=user.id,
                    job_id=job.id,
                    url=target_url,
                    normalized_url=normalized_target,
                    host=domain,
                    source_type="official_ats",
                    trust_level=90,
                    match_confidence="high",
                    title=title,
                    snippet=description[:200] if description else None,
                    http_status=200,
                    content_hash=compute_content_hash(description),
                    selected_as_canonical=True,
                )
                self.db.add(web_source)
                self.db.flush()

                created_jobs.append(
                    CrawlJobItem(
                        id=job.id,
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
                    description
                    and len(description) > len(existing.description or "")
                    and existing.description_status == DescriptionStatus.INSUFFICIENT.value
                ):
                    existing.description = description
                    existing.description_status = DescriptionStatus.OK.value
                    existing.content_hash = compute_content_hash(description)
                    self.db.flush()

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

        self.db.commit()

        msg = f"{len(extracted_postings)} ilan tespit edildi; {jobs_created_count} yeni ilan sisteme eklendi."
        return CrawlSiteResponse(
            success=True,
            url=url,
            jobs_found=len(extracted_postings),
            jobs_created=jobs_created_count,
            jobs=created_jobs,
            message=msg,
        )

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
        # Pattern A: Greenhouse / Lever links: <a href=".../jobs/..." class="...">
        # Pattern B: elements with data-job-id or class containing "opening", "job-item", "posting"
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
        semaphore = asyncio.Semaphore(4)

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
