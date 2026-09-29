"""Job enrichment orchestration service."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    LinkedInFetchForbiddenError,
    SafeWebFetcher,
    WebFetchError,
)
from app.integrations.web_search.base import SearchProvider, SearchResult
from app.integrations.web_search import get_search_provider
from app.models.job import Job
from app.repositories.jobs import JobRepository, JobWebSourceRepository
from app.services.job_enrichment.freshness import calculate_freshness, evaluate_posted_at
from app.services.job_enrichment.html_parser import ExtractedJobData, extract_job_posting
from app.services.job_enrichment.trust import (
    calculate_match_confidence,
    classify_source,
    compute_string_similarity,
)
from app.services.job_enrichment.url_utils import (
    compute_content_hash,
    extract_domain,
    is_linkedin_url,
    normalize_linkedin_job_url,
    normalize_url,
)

logger = logging.getLogger("jobhunter.enrichment")


@dataclass(slots=True)
class EnrichmentCandidate:
    url: str
    normalized_url: str
    host: str
    source_type: str
    trust_level: int
    match_confidence: str
    title: str | None
    extracted_data: ExtractedJobData | None
    http_status: int | None
    content_hash: str | None


@dataclass(slots=True)
class JobEnrichmentOutcome:
    job_id: uuid.UUID
    status: str  # "completed", "failed", "skipped"
    enrichment_status: str  # "enriched", "skipped", "not_found", "failed"
    freshness_status: str
    availability_status: str
    canonical_url: str | None = None
    description_updated: bool = False
    error_class: str | None = None
    error_message: str | None = None


class JobEnrichmentService:
    """Discovers official/ATS sources, enriches job descriptions, and tracks freshness."""

    def __init__(
        self,
        db: Session,
        *,
        search_provider: SearchProvider | None = None,
        fetcher: SafeWebFetcher | None = None,
    ) -> None:
        self.db = db
        self.search_provider = search_provider or get_search_provider()
        self.fetcher = fetcher or SafeWebFetcher()
        self.jobs = JobRepository(db)
        self.web_sources = JobWebSourceRepository(db)

    def is_enrichment_needed(self, job: Job) -> bool:
        """Decide if a job needs web discovery & enrichment."""
        desc = job.description or ""
        word_count = len(desc.split())
        is_short = word_count < settings.job_enrichment_min_words
        is_insufficient = (job.description_status or "") == "insufficient_description"
        no_canonical = not (job.canonical_url or job.company_job_url)

        # Force enrichment if pending or insufficient
        if job.enrichment_status == "pending":
            return True
        return (is_short or is_insufficient) and no_canonical

    async def enrich_job(
        self,
        job_id: uuid.UUID,
        *,
        force: bool = False,
    ) -> JobEnrichmentOutcome:
        """Run discovery, enrichment, and freshness calculation for a single job posting.
        Network operations run outside the database transaction.
        """
        # Step 1: Read snapshot from DB
        job = self.jobs.get(job_id)
        if job is None:
            return JobEnrichmentOutcome(
                job_id=job_id,
                status="failed",
                enrichment_status="failed",
                freshness_status="unknown",
                availability_status="unknown",
                error_class="not_found",
                error_message="İlan bulunamadı.",
            )

        user_id = job.user_id
        title = job.title
        company = job.company
        existing_desc = job.description or ""
        email_received_at = job.email_received_at
        discovered_at = job.discovered_at
        existing_linkedin = job.linkedin_url
        existing_url = job.url

        needs_enrichment = force or self.is_enrichment_needed(job)

        # If already adequate and not forced, just re-evaluate freshness
        if not needs_enrichment:
            date_eval = evaluate_posted_at(
                email_received_at=email_received_at,
                discovered_at=discovered_at,
            )
            freshness_res = calculate_freshness(
                effective_posted_at=job.posted_at or date_eval.effective_posted_at,
                valid_through=job.valid_through,
            )
            job.freshness_status = freshness_res.freshness_status
            job.availability_status = freshness_res.availability_status
            if job.enrichment_status == "pending":
                job.enrichment_status = "skipped"
            job.last_verified_at = datetime.now(timezone.utc)
            self.db.flush()
            return JobEnrichmentOutcome(
                job_id=job_id,
                status="completed",
                enrichment_status=job.enrichment_status,
                freshness_status=job.freshness_status,
                availability_status=job.availability_status,
            )

        # Step 2: Search for official / ATS postings
        queries = [
            f'"{company}" "{title}" careers job',
            f'"{title}" "{company}" hiring',
            f'site:greenhouse.io OR site:lever.co OR site:myworkdayjobs.com "{company}" "{title}"',
            f'"{company}" "{title}" apply',
        ][: settings.web_search_max_queries_per_job]

        search_results: list[SearchResult] = []
        for q in queries:
            try:
                results = await self.search_provider.search(
                    q, limit=settings.web_search_max_results_per_query
                )
                search_results.extend(results)
            except Exception as exc:
                logger.warning("Arama sorgusu başarısız (%s): %s", q, exc)

        # Deduplicate search results by normalized URL
        seen_urls: set[str] = set()
        candidate_urls: list[str] = []
        discovered_linkedin_url: str | None = None

        for res in search_results:
            norm = normalize_url(res.url)
            if not norm:
                continue

            # If search returns a LinkedIn URL, save it as navigation link ONLY (never fetch!)
            if is_linkedin_url(norm):
                if not discovered_linkedin_url and not existing_linkedin:
                    discovered_linkedin_url = normalize_linkedin_job_url(norm)
                continue

            if norm not in seen_urls:
                seen_urls.add(norm)
                candidate_urls.append(res.url)

        # Prioritize candidates by domain trust
        def _candidate_priority(u: str) -> int:
            _, trust, _ = classify_source(u, company)
            return trust

        candidate_urls.sort(key=_candidate_priority, reverse=True)
        # Limit to top 5 candidates
        candidate_urls = candidate_urls[:5]

        # Step 3: Fetch candidate pages
        candidates: list[EnrichmentCandidate] = []

        async def _fetch_candidate(c_url: str) -> EnrichmentCandidate | None:
            norm_c = normalize_url(c_url) or c_url
            host = extract_domain(c_url) or "unknown"
            source_type, trust, _ = classify_source(c_url, company)

            try:
                fetch_res = await self.fetcher.fetch(c_url)
                if fetch_res.status_code in {404, 410}:
                    return EnrichmentCandidate(
                        url=c_url,
                        normalized_url=norm_c,
                        host=host,
                        source_type=source_type,
                        trust_level=trust,
                        match_confidence="none",
                        title=None,
                        extracted_data=None,
                        http_status=fetch_res.status_code,
                        content_hash=None,
                    )

                extracted = extract_job_posting(fetch_res.content)
                if not extracted:
                    return None

                match_conf = calculate_match_confidence(
                    title,
                    extracted.title,
                    company,
                    extracted.company,
                    source_type=source_type,
                )
                c_hash = compute_content_hash(extracted.description)

                return EnrichmentCandidate(
                    url=c_url,
                    normalized_url=norm_c,
                    host=host,
                    source_type=source_type,
                    trust_level=trust,
                    match_confidence=match_conf,
                    title=extracted.title,
                    extracted_data=extracted,
                    http_status=fetch_res.status_code,
                    content_hash=c_hash,
                )
            except LinkedInFetchForbiddenError:
                return None
            except WebFetchError as exc:
                logger.debug("Aday sayfa çekilemedi (%s): %s", c_url, exc)
                return None
            except Exception as exc:
                logger.debug("Beklenmeyen sayfa işleme hatası (%s): %s", c_url, exc)
                return None

        if candidate_urls:
            fetched_results = await asyncio.gather(*(_fetch_candidate(u) for u in candidate_urls))
            candidates = [c for c in fetched_results if c is not None]

        # Step 4: Pick best canonical candidate
        valid_candidates = [
            c for c in candidates
            if c.extracted_data and c.match_confidence in {"high", "medium"} and c.extracted_data.description
        ]

        # Sort: trust_level desc, match_confidence high > medium, description length desc
        def _rank_key(c: EnrichmentCandidate) -> tuple[int, int, int]:
            conf_score = 2 if c.match_confidence == "high" else 1
            desc_len = len(c.extracted_data.description or "") if c.extracted_data else 0
            return (c.trust_level, conf_score, desc_len)

        valid_candidates.sort(key=_rank_key, reverse=True)
        best = valid_candidates[0] if valid_candidates else None

        # Step 5: Persist results in short DB transaction
        now = datetime.now(timezone.utc)
        desc_updated = False

        if best and best.extracted_data:
            extracted = best.extracted_data

            # Date calculation
            date_eval = evaluate_posted_at(
                json_ld_date=extracted.date_posted,
                html_meta_date=extracted.date_posted if extracted.source_type == "semantic_html" else None,
                email_received_at=email_received_at,
                discovered_at=discovered_at,
                now=now,
            )

            # Freshness calculation
            freshness_res = calculate_freshness(
                effective_posted_at=date_eval.effective_posted_at,
                valid_through=extracted.valid_through,
                is_closed=extracted.is_closed,
                now=now,
            )

            # Update job fields
            job.canonical_url = best.url
            if best.source_type == "ats":
                job.application_url = best.url
            elif best.source_type == "official":
                job.company_job_url = best.url

            # Enrich description if candidate description is richer
            if extracted.description and len(extracted.description) > len(existing_desc):
                job.description = extracted.description
                job.description_status = "ok"
                job.content_hash = best.content_hash
                desc_updated = True

            job.posted_at = date_eval.effective_posted_at
            job.posted_at_source = date_eval.posted_at_source
            job.posted_at_confidence = date_eval.posted_at_confidence
            job.valid_through = extracted.valid_through
            job.freshness_status = freshness_res.freshness_status
            job.availability_status = freshness_res.availability_status
            job.enrichment_status = "enriched"
            job.last_enriched_at = now
            job.last_verified_at = now

        else:
            # No valid candidate discovered: evaluate freshness based on email date
            date_eval = evaluate_posted_at(
                email_received_at=email_received_at,
                discovered_at=discovered_at,
                now=now,
            )
            freshness_res = calculate_freshness(
                effective_posted_at=job.posted_at or date_eval.effective_posted_at,
                valid_through=job.valid_through,
                now=now,
            )
            job.posted_at = job.posted_at or date_eval.effective_posted_at
            job.posted_at_source = job.posted_at_source or date_eval.posted_at_source
            job.posted_at_confidence = job.posted_at_confidence or date_eval.posted_at_confidence
            job.freshness_status = freshness_res.freshness_status
            job.availability_status = freshness_res.availability_status
            job.enrichment_status = "not_found"
            job.last_enriched_at = now
            job.last_verified_at = now

        # Update LinkedIn URL if discovered
        if discovered_linkedin_url and not job.linkedin_url:
            job.linkedin_url = discovered_linkedin_url

        # Record all discovered web sources for provenance
        for c in candidates:
            self.web_sources.upsert(
                user_id=user_id,
                job_id=job.id,
                url=c.url,
                normalized_url=c.normalized_url,
                host=c.host,
                source_type=c.source_type,
                trust_level=c.trust_level,
                match_confidence=c.match_confidence,
                title=c.title,
                snippet=c.extracted_data.description[:300] if (c.extracted_data and c.extracted_data.description) else None,
                http_status=c.http_status,
                content_hash=c.content_hash,
                selected_as_canonical=(best is not None and c.url == best.url),
            )

        self.db.flush()

        return JobEnrichmentOutcome(
            job_id=job_id,
            status="completed",
            enrichment_status=job.enrichment_status,
            freshness_status=job.freshness_status,
            availability_status=job.availability_status,
            canonical_url=job.canonical_url,
            description_updated=desc_updated,
        )
