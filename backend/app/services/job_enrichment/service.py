"""Job enrichment orchestration service (decoupled architecture)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    LinkedInFetchForbiddenError,
    SafeWebFetcher,
    WebFetchError,
)
from app.integrations.web_search import get_search_provider
from app.integrations.web_search.base import SearchProvider, SearchResult, SearchUnavailableError
from app.models.enums import EnrichmentStatus
from app.models.job import Job, JobMatch, JobWebSource
from app.repositories.jobs import JobRepository, JobWebSourceRepository
from app.services.job_enrichment.dtos import (
    DiscoveredWebSourceDTO,
    EnrichmentCandidate,
    ExistingWebSourceCache,
    JobEnrichmentOutcome,
    JobEnrichmentResult,
    JobEnrichmentSnapshot,
)
from app.services.job_enrichment.freshness import calculate_freshness, evaluate_posted_at
from app.services.job_enrichment.html_parser import ExtractedJobData, extract_job_posting
from app.services.job_enrichment.trust import (
    calculate_match_confidence,
    classify_source,
    compute_string_similarity,
    extract_ats_tenant,
)
from app.services.job_enrichment.url_utils import (
    compute_content_hash,
    extract_domain,
    is_linkedin_url,
    normalize_linkedin_job_url,
    normalize_url,
)

logger = logging.getLogger("jobhunter.enrichment")


def is_enrichment_needed(
    snapshot: JobEnrichmentSnapshot,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> bool:
    """Decide if a job needs web discovery & enrichment based on TTL, content quality, and status."""
    if force:
        return True

    current_time = now or datetime.now(timezone.utc)

    # 1. Search disabled: do not automatically requeue
    if snapshot.enrichment_status == EnrichmentStatus.SEARCH_DISABLED.value:
        return False

    # 2. Enriched TTL check (default 24 hours)
    if snapshot.enrichment_status == EnrichmentStatus.ENRICHED.value and snapshot.last_enriched_at:
        last = snapshot.last_enriched_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if current_time - last < timedelta(hours=settings.job_enrichment_ttl_hours):
            return False
        return True

    # 3. Not found TTL check (12 hours)
    if snapshot.enrichment_status == EnrichmentStatus.NOT_FOUND.value and snapshot.last_enriched_at:
        last = snapshot.last_enriched_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if current_time - last < timedelta(hours=12):
            return False
        return True

    # 4. Search unavailable, fetch failed, or failed TTL check (1 hour)
    if snapshot.enrichment_status in (
        EnrichmentStatus.SEARCH_UNAVAILABLE.value,
        EnrichmentStatus.FETCH_FAILED.value,
        EnrichmentStatus.FAILED.value,
    ) and snapshot.last_enriched_at:
        last = snapshot.last_enriched_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if current_time - last < timedelta(hours=1):
            return False
        return True

    # 5. Content quality check
    desc = snapshot.description or ""
    word_count = len(desc.split())
    is_short = word_count < settings.job_enrichment_min_words
    is_insufficient = snapshot.description_status == "insufficient_description"
    no_canonical = not (snapshot.canonical_url or snapshot.company_job_url)

    if snapshot.enrichment_status == EnrichmentStatus.PENDING.value:
        return True
    return (is_short or is_insufficient) and no_canonical


def build_search_queries(
    company: str,
    title: str,
    existing_linkedin: str | None = None,
    max_queries: int | None = None,
) -> list[str]:
    """Generate prioritized search queries for official/ATS discovery and LinkedIn fallback."""
    limit = max_queries or settings.web_search_max_queries_per_job
    queries = [
        f'"{company}" "{title}" careers job',
        f'site:greenhouse.io OR site:lever.co OR site:myworkdayjobs.com "{company}" "{title}"',
        f'"{company}" "{title}" apply',
    ]
    if not existing_linkedin:
        queries.append(f'site:linkedin.com/jobs/view "{company}" "{title}"')
    else:
        queries.append(f'"{title}" "{company}" hiring')

    if len(queries) < limit and not existing_linkedin:
        queries.append(f'"{title}" "{company}" hiring')

    return queries[:limit]


async def execute_enrichment_flow(
    snapshot: JobEnrichmentSnapshot,
    search_provider: SearchProvider,
    fetcher: SafeWebFetcher,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> JobEnrichmentResult:
    """Pure async network flow: web discovery, page fetching, and ranking.
    Runs completely detached with ZERO database calls or locks.
    """
    current_time = now or datetime.now(timezone.utc)
    job_id = snapshot.job_id
    title = snapshot.title
    company = snapshot.company
    existing_desc = snapshot.description or ""
    email_received_at = snapshot.email_received_at
    discovered_at = snapshot.discovered_at
    existing_linkedin = snapshot.linkedin_url

    # Check search provider availability before doing any network calls
    provider_available = getattr(search_provider, "available", True)
    if not provider_available:
        date_eval = evaluate_posted_at(
            email_received_at=email_received_at,
            discovered_at=discovered_at,
            now=current_time,
        )
        freshness_res = calculate_freshness(
            effective_posted_at=snapshot.posted_at or date_eval.effective_posted_at,
            valid_through=snapshot.valid_through,
            availability_status=snapshot.availability_status,
            now=current_time,
        )
        return JobEnrichmentResult(
            job_id=job_id,
            status="completed",
            enrichment_status=EnrichmentStatus.SEARCH_DISABLED.value,
            freshness_status=freshness_res.freshness_status,
            availability_status=freshness_res.availability_status,
            canonical_url=snapshot.canonical_url,
            company_job_url=snapshot.company_job_url,
            application_url=snapshot.application_url,
            linkedin_url=snapshot.linkedin_url,
            posted_at=snapshot.posted_at or date_eval.effective_posted_at,
            posted_at_source=snapshot.posted_at_source or date_eval.posted_at_source,
            posted_at_confidence=snapshot.posted_at_confidence or date_eval.posted_at_confidence,
            valid_through=snapshot.valid_through,
            location=snapshot.location,
            work_mode=snapshot.work_mode,
            employment_type=snapshot.employment_type,
            new_description=None,
            new_content_hash=None,
            description_updated=False,
            discovered_sources=[],
            last_verified_at=current_time,
            last_enriched_at=current_time,
        )

    needs_enrichment = force or is_enrichment_needed(snapshot, force=force, now=current_time)

    # If already adequate and not forced, re-evaluate freshness only
    if not needs_enrichment:
        date_eval = evaluate_posted_at(
            email_received_at=email_received_at,
            discovered_at=discovered_at,
            now=current_time,
        )
        freshness_res = calculate_freshness(
            effective_posted_at=snapshot.posted_at or date_eval.effective_posted_at,
            valid_through=snapshot.valid_through,
            availability_status=snapshot.availability_status,
            now=current_time,
        )
        return JobEnrichmentResult(
            job_id=job_id,
            status="completed",
            enrichment_status=EnrichmentStatus.SKIPPED.value if snapshot.enrichment_status == EnrichmentStatus.PENDING.value else snapshot.enrichment_status,
            freshness_status=freshness_res.freshness_status,
            availability_status=freshness_res.availability_status,
            canonical_url=snapshot.canonical_url,
            company_job_url=snapshot.company_job_url,
            application_url=snapshot.application_url,
            linkedin_url=snapshot.linkedin_url,
            posted_at=snapshot.posted_at or date_eval.effective_posted_at,
            posted_at_source=snapshot.posted_at_source or date_eval.posted_at_source,
            posted_at_confidence=snapshot.posted_at_confidence or date_eval.posted_at_confidence,
            valid_through=snapshot.valid_through,
            location=snapshot.location,
            work_mode=snapshot.work_mode,
            employment_type=snapshot.employment_type,
            new_description=None,
            new_content_hash=None,
            description_updated=False,
            discovered_sources=[],
            last_verified_at=current_time,
            last_enriched_at=snapshot.last_enriched_at,
        )

    # Step 1: Search for official / ATS postings
    queries = build_search_queries(
        company=company,
        title=title,
        existing_linkedin=existing_linkedin,
        max_queries=settings.web_search_max_queries_per_job,
    )

    async def _execute_single_query(q_str: str) -> tuple[list[SearchResult], bool]:
        try:
            res = await search_provider.search(
                q_str, limit=settings.web_search_max_results_per_query
            )
            return res, False
        except SearchUnavailableError as exc:
            logger.warning("Arama sağlayıcısı yanıt vermedi (%s): %s", q_str, exc)
            return [], True
        except Exception as exc:
            logger.warning("Arama sorgusu başarısız (%s): %s", q_str, exc)
            return [], False

    query_results = await asyncio.gather(*(_execute_single_query(q) for q in queries))
    search_results: list[SearchResult] = []
    search_unavailable_count = 0
    for res_list, is_unavail in query_results:
        search_results.extend(res_list)
        if is_unavail:
            search_unavailable_count += 1

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

    # Prioritize candidate URLs by domain trust
    def _candidate_priority(u: str) -> int:
        _, trust, _ = classify_source(u, company)
        return trust

    # Include pre-existing canonical or company URLs for re-verification
    for existing_url in (snapshot.canonical_url, snapshot.company_job_url):
        if existing_url and not is_linkedin_url(existing_url):
            norm_ex = normalize_url(existing_url)
            if norm_ex and norm_ex not in seen_urls:
                seen_urls.add(norm_ex)
                candidate_urls.append(existing_url)

    candidate_urls.sort(key=_candidate_priority, reverse=True)
    candidate_urls = candidate_urls[:5]

    # Step 2: Fetch candidate pages with conditional ETag / Last-Modified
    verified_urls = {
        normalize_url(u)
        for u in (snapshot.canonical_url, snapshot.company_job_url)
        if u and normalize_url(u)
    }
    candidates: list[EnrichmentCandidate] = []
    existing_cache: dict[str, ExistingWebSourceCache] = {
        s.normalized_url: s for s in snapshot.existing_sources if s.normalized_url
    }
    fetch_error_count = 0

    async def _fetch_candidate(c_url: str) -> EnrichmentCandidate | None:
        nonlocal fetch_error_count
        norm_c = normalize_url(c_url) or c_url
        host = extract_domain(c_url) or "unknown"
        source_type, trust, _ = classify_source(c_url, company)
        prev = existing_cache.get(norm_c)

        try:
            fetch_res = await fetcher.fetch(
                c_url,
                etag=prev.etag if prev else None,
                last_modified=prev.last_modified if prev else None,
            )

            # 304 Not Modified
            if fetch_res.status_code == 304 or fetch_res.is_not_modified:
                is_prev_canonical = bool(prev and prev.selected_as_canonical) or (
                    bool(snapshot.canonical_url and norm_c in verified_urls)
                )
                return EnrichmentCandidate(
                    url=c_url,
                    normalized_url=norm_c,
                    host=host,
                    source_type=source_type,
                    trust_level=trust,
                    match_confidence="high" if is_prev_canonical else "medium",
                    title=snapshot.title,
                    extracted_data=None,
                    http_status=304,
                    content_hash=prev.content_hash if prev else snapshot.content_hash,
                    etag=fetch_res.etag or (prev.etag if prev else None),
                    last_modified=fetch_res.last_modified or (prev.last_modified if prev else None),
                    is_not_modified=True,
                )

            # 404 / 410 handling
            if fetch_res.status_code in {404, 410}:
                tenant = extract_ats_tenant(c_url)
                tenant_match = bool(tenant and compute_string_similarity(company, tenant) >= 0.60)
                is_prev_verified = bool(norm_c in verified_urls)
                conf = "high" if (tenant_match or is_prev_verified) else "none"
                return EnrichmentCandidate(
                    url=c_url,
                    normalized_url=norm_c,
                    host=host,
                    source_type=source_type,
                    trust_level=trust,
                    match_confidence=conf,
                    title=None,
                    extracted_data=None,
                    http_status=fetch_res.status_code,
                    content_hash=None,
                    etag=fetch_res.etag,
                    last_modified=fetch_res.last_modified,
                    is_not_modified=False,
                )

            extracted = extract_job_posting(
                fetch_res.content,
                expected_title=title,
                expected_company=company,
            )
            if not extracted:
                return None

            match_conf = calculate_match_confidence(
                title,
                extracted.title,
                company,
                extracted.company,
                source_type=source_type,
                url=c_url,
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
                etag=fetch_res.etag,
                last_modified=fetch_res.last_modified,
                is_not_modified=False,
            )
        except LinkedInFetchForbiddenError:
            return None
        except WebFetchError as exc:
            fetch_error_count += 1
            logger.debug("Aday sayfa çekilemedi (%s): %s", c_url, exc)
            return None
        except Exception as exc:
            fetch_error_count += 1
            logger.debug("Beklenmeyen sayfa işleme hatası (%s): %s", c_url, exc)
            return None

    if candidate_urls:
        fetched_results = await asyncio.gather(*(_fetch_candidate(u) for u in candidate_urls))
        candidates = [c for c in fetched_results if c is not None]

    # Convert candidates to DiscoveredWebSourceDTO for provenance
    best_candidate_url: str | None = None
    discovered_sources: list[DiscoveredWebSourceDTO] = []

    # Step 3: Pick best canonical candidate (ranking: confidence > trust > length)
    valid_candidates = [
        c
        for c in candidates
        if (
            (c.extracted_data and c.match_confidence in {"high", "medium"} and c.extracted_data.description)
            or (c.is_not_modified and c.match_confidence in {"high", "medium"})
        )
    ]

    def _rank_key(c: EnrichmentCandidate) -> tuple[int, int, int]:
        conf_score = 3 if c.match_confidence == "high" else (2 if c.match_confidence == "medium" else 1)
        desc_len = 0
        if c.extracted_data and c.extracted_data.description:
            desc_len = len(c.extracted_data.description)
        elif c.is_not_modified and snapshot.description:
            desc_len = len(snapshot.description)
        return (conf_score, c.trust_level, desc_len)

    valid_candidates.sort(key=_rank_key, reverse=True)
    best = valid_candidates[0] if valid_candidates else None
    if best:
        best_candidate_url = best.url

    for c in candidates:
        snippet_text = (
            c.extracted_data.description[:300]
            if (c.extracted_data and c.extracted_data.description)
            else (snapshot.description[:300] if (c.is_not_modified and snapshot.description) else None)
        )
        discovered_sources.append(
            DiscoveredWebSourceDTO(
                url=c.url,
                normalized_url=c.normalized_url,
                host=c.host,
                source_type=c.source_type,
                trust_level=c.trust_level,
                match_confidence=c.match_confidence,
                title=c.title,
                snippet=snippet_text,
                http_status=c.http_status,
                content_hash=c.content_hash,
                selected_as_canonical=(best is not None and c.url == best.url),
                etag=c.etag,
                last_modified=c.last_modified,
            )
        )

    # Step 4: Construct result
    if best:
        if best.is_not_modified:
            # 304 Not Modified on verified canonical source
            freshness_res = calculate_freshness(
                effective_posted_at=snapshot.posted_at,
                valid_through=snapshot.valid_through,
                availability_status="active",
                now=current_time,
            )
            return JobEnrichmentResult(
                job_id=job_id,
                status="completed",
                enrichment_status=EnrichmentStatus.ENRICHED.value,
                freshness_status=freshness_res.freshness_status,
                availability_status="active",
                canonical_url=best.url,
                company_job_url=best.url if best.source_type == "official" else snapshot.company_job_url,
                application_url=best.url if best.source_type == "ats" else snapshot.application_url,
                linkedin_url=discovered_linkedin_url or existing_linkedin,
                posted_at=snapshot.posted_at,
                posted_at_source=snapshot.posted_at_source,
                posted_at_confidence=snapshot.posted_at_confidence,
                valid_through=snapshot.valid_through,
                location=snapshot.location,
                work_mode=snapshot.work_mode,
                employment_type=snapshot.employment_type,
                new_description=snapshot.description,
                new_content_hash=snapshot.content_hash,
                description_updated=False,
                discovered_sources=discovered_sources,
                last_verified_at=current_time,
                last_enriched_at=current_time,
            )

        if best.extracted_data:
            extracted = best.extracted_data
            date_eval = evaluate_posted_at(
                json_ld_date=extracted.date_posted,
                html_meta_date=extracted.date_posted if extracted.source_type == "semantic_html" else None,
                email_received_at=email_received_at,
                discovered_at=discovered_at,
                now=current_time,
            )
            freshness_res = calculate_freshness(
                effective_posted_at=date_eval.effective_posted_at,
                valid_through=extracted.valid_through,
                is_closed=extracted.is_closed,
                now=current_time,
            )

            canonical_url = best.url
            company_job_url = best.url if best.source_type == "official" else snapshot.company_job_url
            application_url = (
                extracted.application_url
                or (best.url if best.source_type == "ats" else snapshot.application_url)
            )

            desc_updated = False
            new_desc = None
            new_hash = None
            if extracted.description:
                candidate_hash = best.content_hash
                if candidate_hash and candidate_hash != snapshot.content_hash and len(extracted.description) > len(existing_desc):
                    desc_updated = True
                    new_desc = extracted.description
                    new_hash = candidate_hash
                elif len(extracted.description) > len(existing_desc):
                    desc_updated = True
                    new_desc = extracted.description
                    new_hash = candidate_hash

            return JobEnrichmentResult(
                job_id=job_id,
                status="completed",
                enrichment_status=EnrichmentStatus.ENRICHED.value,
                freshness_status=freshness_res.freshness_status,
                availability_status=freshness_res.availability_status,
                canonical_url=canonical_url,
                company_job_url=company_job_url,
                application_url=application_url,
                linkedin_url=discovered_linkedin_url or existing_linkedin,
                posted_at=date_eval.effective_posted_at,
                posted_at_source=date_eval.posted_at_source,
                posted_at_confidence=date_eval.posted_at_confidence,
                valid_through=extracted.valid_through,
                location=extracted.location or snapshot.location,
                work_mode=extracted.work_mode or snapshot.work_mode,
                employment_type=extracted.employment_type or snapshot.employment_type,
                new_description=new_desc,
                new_content_hash=new_hash,
                description_updated=desc_updated,
                discovered_sources=discovered_sources,
                last_verified_at=current_time,
                last_enriched_at=current_time,
            )

    # No valid candidate discovered: check 404 / 410 from verified or high-confidence sources ONLY
    verified_urls = {
        normalize_url(u)
        for u in (snapshot.canonical_url, snapshot.company_job_url)
        if u and normalize_url(u)
    }

    def _is_trusted_404_410_source(c: EnrichmentCandidate) -> bool:
        norm = normalize_url(c.url)
        is_previously_verified = bool(norm and norm in verified_urls)
        is_high_conf = (c.match_confidence == "high")
        return is_previously_verified or ((c.source_type in {"ats", "official"}) and is_high_conf)

    official_410 = any(
        c.http_status == 410 and _is_trusted_404_410_source(c) for c in candidates
    )
    official_404 = any(
        c.http_status == 404 and _is_trusted_404_410_source(c) for c in candidates
    )

    avail_status = snapshot.availability_status or "active"
    if official_410:
        avail_status = "removed"
    elif official_404:
        avail_status = "possibly_closed"

    date_eval = evaluate_posted_at(
        email_received_at=email_received_at,
        discovered_at=discovered_at,
        now=current_time,
    )
    freshness_res = calculate_freshness(
        effective_posted_at=snapshot.posted_at or date_eval.effective_posted_at,
        valid_through=snapshot.valid_through,
        availability_status=avail_status if avail_status != "active" else None,
        now=current_time,
    )

    # Determine status
    if search_unavailable_count > 0 and search_unavailable_count == len(queries):
        enrich_status = EnrichmentStatus.SEARCH_UNAVAILABLE.value
        err_class = "SearchUnavailableError"
        err_msg = "Web arama sağlayıcısı erişilemez durumda."
    elif candidate_urls and fetch_error_count >= len(candidate_urls):
        enrich_status = EnrichmentStatus.FETCH_FAILED.value
        err_class = "FetchUnavailableError"
        err_msg = "Aday kaynak sayfaları indirilemedi (ağ/zaman aşımı hatası)."
    else:
        enrich_status = EnrichmentStatus.NOT_FOUND.value
        err_class = None
        err_msg = None

    return JobEnrichmentResult(
        job_id=job_id,
        status="completed",
        enrichment_status=enrich_status,
        freshness_status=freshness_res.freshness_status,
        availability_status=freshness_res.availability_status,
        canonical_url=snapshot.canonical_url,
        company_job_url=snapshot.company_job_url,
        application_url=snapshot.application_url,
        linkedin_url=discovered_linkedin_url or existing_linkedin,
        posted_at=snapshot.posted_at or date_eval.effective_posted_at,
        posted_at_source=snapshot.posted_at_source or date_eval.posted_at_source,
        posted_at_confidence=snapshot.posted_at_confidence or date_eval.posted_at_confidence,
        valid_through=snapshot.valid_through,
        description_updated=False,
        discovered_sources=discovered_sources,
        error_class=err_class,
        error_message=err_msg,
        last_verified_at=current_time,
        last_enriched_at=current_time,
    )


def take_snapshot(session: Session, job_id: uuid.UUID) -> JobEnrichmentSnapshot | None:
    """Read a lightweight snapshot of Job attributes from DB."""
    job = session.get(Job, job_id)
    if job is None:
        return None

    web_sources = (
        session.execute(
            select(JobWebSource).where(JobWebSource.job_id == job.id)
        ).scalars().all()
    )
    existing_sources = [
        ExistingWebSourceCache(
            url=s.url,
            normalized_url=s.normalized_url,
            etag=s.etag,
            last_modified=s.last_modified,
            content_hash=s.content_hash,
            selected_as_canonical=s.selected_as_canonical,
            http_status=s.http_status,
        )
        for s in web_sources
    ]

    return JobEnrichmentSnapshot(
        job_id=job.id,
        user_id=job.user_id,
        title=job.title,
        company=job.company,
        description=job.description,
        description_status=job.description_status,
        posted_at=job.posted_at,
        posted_at_source=job.posted_at_source,
        posted_at_confidence=job.posted_at_confidence,
        valid_through=job.valid_through,
        email_received_at=job.email_received_at,
        discovered_at=job.discovered_at,
        freshness_status=job.freshness_status,
        availability_status=job.availability_status,
        enrichment_status=job.enrichment_status,
        content_hash=job.content_hash,
        canonical_url=job.canonical_url,
        company_job_url=job.company_job_url,
        application_url=job.application_url,
        linkedin_url=job.linkedin_url,
        url=job.url,
        last_enriched_at=job.last_enriched_at,
        last_verified_at=job.last_verified_at,
        work_mode=job.work_mode,
        location=job.location,
        employment_type=job.employment_type,
        existing_sources=existing_sources,
    )


def persist_result(
    session: Session,
    result: JobEnrichmentResult,
    original_snapshot: JobEnrichmentSnapshot,
) -> JobEnrichmentOutcome:
    """Persist the enrichment result into DB with optimistic concurrency and scoring re-evaluation."""
    job = session.get(Job, result.job_id)
    if job is None:
        return JobEnrichmentOutcome(
            job_id=result.job_id,
            status="failed",
            enrichment_status="failed",
            freshness_status="unknown",
            availability_status="unknown",
            error_class="not_found",
            error_message="İlan bulunamadı.",
        )

    # Optimistic update of description
    desc_updated = False
    if result.description_updated and result.new_description:
        if (
            result.new_content_hash
            and result.new_content_hash != job.content_hash
            and len(result.new_description) > len(job.description or "")
        ):
            job.description = result.new_description
            job.description_status = "ok"
            job.content_hash = result.new_content_hash
            desc_updated = True
            # Re-scoring trigger: mark match pending if content changed
            match = session.get(JobMatch, job.id) or job.match
            if match is not None:
                match.analysis_status = "pending"
                match.job_content_hash = None
        elif len(result.new_description) > len(job.description or ""):
            job.description = result.new_description
            job.description_status = "ok"
            job.content_hash = result.new_content_hash
            desc_updated = True
            match = session.get(JobMatch, job.id) or job.match
            if match is not None:
                match.analysis_status = "pending"
                match.job_content_hash = None

    if result.canonical_url:
        job.canonical_url = result.canonical_url
    if result.company_job_url:
        job.company_job_url = result.company_job_url
    if result.application_url:
        job.application_url = result.application_url
    if result.linkedin_url and not job.linkedin_url:
        job.linkedin_url = result.linkedin_url

    if result.location and not job.location:
        job.location = result.location
    if result.work_mode and job.work_mode in {"unknown", None}:
        job.work_mode = result.work_mode
    if result.employment_type and not job.employment_type:
        job.employment_type = result.employment_type

    job.posted_at = result.posted_at or job.posted_at
    job.posted_at_source = result.posted_at_source or job.posted_at_source
    job.posted_at_confidence = result.posted_at_confidence or job.posted_at_confidence
    job.valid_through = result.valid_through or job.valid_through
    job.freshness_status = result.freshness_status
    job.availability_status = result.availability_status
    job.enrichment_status = result.enrichment_status
    job.last_enriched_at = result.last_enriched_at or job.last_enriched_at
    job.last_verified_at = result.last_verified_at or job.last_verified_at

    # Upsert discovered web sources
    web_sources_repo = JobWebSourceRepository(session)
    for src in result.discovered_sources:
        web_sources_repo.upsert(
            user_id=job.user_id,
            job_id=job.id,
            url=src.url,
            normalized_url=src.normalized_url,
            host=src.host,
            source_type=src.source_type,
            trust_level=src.trust_level,
            match_confidence=src.match_confidence,
            title=src.title,
            snippet=src.snippet,
            http_status=src.http_status,
            content_hash=src.content_hash,
            selected_as_canonical=src.selected_as_canonical,
            etag=src.etag,
            last_modified=src.last_modified,
        )

    session.flush()

    return JobEnrichmentOutcome(
        job_id=job.id,
        status=result.status,
        enrichment_status=job.enrichment_status,
        freshness_status=job.freshness_status,
        availability_status=job.availability_status,
        canonical_url=job.canonical_url,
        description_updated=desc_updated,
        error_class=result.error_class,
        error_message=result.error_message,
    )


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

    def is_enrichment_needed(
        self,
        job: Job | JobEnrichmentSnapshot,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> bool:
        """Decide if a job needs web discovery & enrichment."""
        if isinstance(job, JobEnrichmentSnapshot):
            return is_enrichment_needed(job, force=force, now=now)

        snapshot = JobEnrichmentSnapshot(
            job_id=job.id,
            user_id=job.user_id,
            title=job.title,
            company=job.company,
            description=job.description,
            description_status=job.description_status,
            posted_at=job.posted_at,
            posted_at_source=job.posted_at_source,
            posted_at_confidence=job.posted_at_confidence,
            valid_through=job.valid_through,
            email_received_at=job.email_received_at,
            discovered_at=job.discovered_at,
            freshness_status=job.freshness_status,
            availability_status=job.availability_status,
            enrichment_status=job.enrichment_status,
            content_hash=job.content_hash,
            canonical_url=job.canonical_url,
            company_job_url=job.company_job_url,
            application_url=job.application_url,
            linkedin_url=job.linkedin_url,
            url=job.url,
            last_enriched_at=job.last_enriched_at,
            last_verified_at=job.last_verified_at,
            work_mode=job.work_mode,
            location=job.location,
            employment_type=job.employment_type,
        )
        return is_enrichment_needed(snapshot, force=force, now=now)

    async def enrich_job(
        self,
        job_id: uuid.UUID,
        *,
        force: bool = False,
    ) -> JobEnrichmentOutcome:
        """Run discovery, enrichment, and freshness calculation for a single job posting.
        Network operations execute detached without holding active DB transactions.
        """
        snapshot = take_snapshot(self.db, job_id)
        if snapshot is None:
            return JobEnrichmentOutcome(
                job_id=job_id,
                status="failed",
                enrichment_status="failed",
                freshness_status="unknown",
                availability_status="unknown",
                error_class="not_found",
                error_message="İlan bulunamadı.",
            )

        # Pure async network operations run outside DB transaction
        result = await execute_enrichment_flow(
            snapshot,
            self.search_provider,
            self.fetcher,
            force=force,
        )

        return persist_result(self.db, result, snapshot)
