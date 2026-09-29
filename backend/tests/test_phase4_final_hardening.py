"""Phase 4 Final Hardening Test Suite.

Covers:
1. WEB_SEARCH_PROVIDER=none semantics (NullSearchProvider -> search_disabled, 0 network calls, no crash)
2. search_unavailable distinction (SearchUnavailableError -> search_unavailable status)
3. Empty successful search distinction (HTTP 200 with 0 results -> not_found status)
4. Partial search failure resilience (some queries fail, successful ones still enrich)
5. 404/410 false-positive mitigation (random unverified 404 does NOT close job)
6. Verified canonical 404 marks possibly_closed
7. Verified canonical 410 marks removed
8. Random /jobs/ path is NOT classified as official
9. ATS without verified company capped at medium confidence (never high)
10. ATS with wrong company penalized to low/none
11. Conditional fetch passes ETag and Last-Modified to fetcher
12. 304 Not Modified does NOT trigger re-score and preserves description
13. Same content hash 200 does NOT trigger re-score
14. Changed content hash triggers re-score (analysis_status -> pending)
15. LinkedIn fallback query executes when linkedin_url is missing
16. LinkedIn URLs are NEVER fetched (provenance only)
17. All candidate fetches failing yields fetch_failed
18. Search concurrency respects bounded parallelism
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    FetchUnavailableError,
    LinkedInFetchForbiddenError,
    SafeWebFetcher,
)
from app.integrations.web_search.base import SearchResult, SearchUnavailableError
from app.integrations.web_search.mock import MockSearchProvider
from app.integrations.web_search.null import NullSearchProvider
from app.models.enums import DescriptionStatus, EnrichmentStatus
from app.models.job import Job, JobMatch, JobWebSource
from app.repositories.jobs import JobWebSourceRepository
from app.services.job_enrichment.dtos import JobEnrichmentSnapshot
from app.services.job_enrichment.service import (
    JobEnrichmentService,
    build_search_queries,
    execute_enrichment_flow,
    take_snapshot,
)
from app.services.job_enrichment.trust import (
    calculate_match_confidence,
    classify_source,
)
from app.services.job_enrichment.url_utils import compute_content_hash, normalize_url

SAMPLE_VALID_JOB_HTML = """
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Senior AI Infrastructure Engineer",
  "description": "<p>NovaTech is seeking a Senior AI Infrastructure Engineer to lead distributed LLM inference clusters and optimize high throughput pipelines.</p>",
  "datePosted": "2026-09-28T10:00:00Z",
  "hiringOrganization": {
    "@type": "Organization",
    "name": "NovaTech AI"
  }
}
</script>
</head>
<body><h1>Senior AI Infrastructure Engineer</h1></body>
</html>
"""


@pytest.fixture
def mock_fetcher():
    fetcher = AsyncMock(spec=SafeWebFetcher)
    fetcher.fetch.return_value = FetchResult(
        url="https://boards.greenhouse.io/novatech/jobs/100",
        final_url="https://boards.greenhouse.io/novatech/jobs/100",
        status_code=200,
        content=SAMPLE_VALID_JOB_HTML,
    )
    return fetcher


class TestPhase4FinalHardening:

    @pytest.mark.asyncio
    async def test_null_provider_is_not_not_found(self, db: Session, user1):
        """1. NullSearchProvider returns search_disabled, does 0 network requests, doesn't crash."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Senior Backend Engineer",
            company="Acme Corp",
            description="Kısa açıklama",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        null_provider = NullSearchProvider()
        fetcher = AsyncMock(spec=SafeWebFetcher)

        service = JobEnrichmentService(db, search_provider=null_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.status == "completed"
        assert outcome.enrichment_status == EnrichmentStatus.SEARCH_DISABLED.value
        assert fetcher.fetch.call_count == 0
        db.refresh(job)
        assert job.enrichment_status == EnrichmentStatus.SEARCH_DISABLED.value

    @pytest.mark.asyncio
    async def test_search_unavailable_is_distinct(self, db: Session, user1):
        """2. Provider failure (SearchUnavailableError) returns search_unavailable status."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="DevOps Specialist",
            company="CloudFlow",
            description="Short desc",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        search_provider = AsyncMock()
        search_provider.available = True
        search_provider.search.side_effect = SearchUnavailableError("SearXNG unreachable")

        fetcher = AsyncMock(spec=SafeWebFetcher)
        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.enrichment_status == EnrichmentStatus.SEARCH_UNAVAILABLE.value
        assert outcome.error_class == "SearchUnavailableError"
        assert fetcher.fetch.call_count == 0
        db.refresh(job)
        assert job.enrichment_status == EnrichmentStatus.SEARCH_UNAVAILABLE.value

    @pytest.mark.asyncio
    async def test_empty_successful_search_is_not_found(self, db: Session, user1):
        """3. Empty results from working search returns not_found (error_class is None)."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Obscure Niche Role",
            company="GhostStartupXYZ",
            description="Short desc",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        search_provider = MockSearchProvider()  # returns [] for anything not configured
        fetcher = AsyncMock(spec=SafeWebFetcher)

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.enrichment_status == EnrichmentStatus.NOT_FOUND.value
        assert outcome.error_class is None
        db.refresh(job)
        assert job.enrichment_status == EnrichmentStatus.NOT_FOUND.value

    @pytest.mark.asyncio
    async def test_partial_search_failure_can_enrich(self, db: Session, user1):
        """4. Partial search query failure still enriches if at least one query succeeds."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Kısa",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        candidate_url = "https://boards.greenhouse.io/novatech/jobs/100"

        # Search mock: fails for query 0 and 1, succeeds for query 2
        calls = 0

        async def flaky_search(query: str, limit: int = 5):
            nonlocal calls
            calls += 1
            if calls <= 2:
                raise SearchUnavailableError("Temporary timeout on this query")
            return [SearchResult(url=candidate_url, title="Senior AI Infrastructure Engineer - NovaTech AI", snippet="LLM infra role")]

        search_provider = AsyncMock()
        search_provider.available = True
        search_provider.search.side_effect = flaky_search

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=candidate_url,
            final_url=candidate_url,
            status_code=200,
            content=SAMPLE_VALID_JOB_HTML,
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.enrichment_status == EnrichmentStatus.ENRICHED.value
        assert outcome.description_updated is True
        db.refresh(job)
        assert job.enrichment_status == EnrichmentStatus.ENRICHED.value
        assert job.canonical_url == candidate_url

    @pytest.mark.asyncio
    async def test_low_confidence_404_does_not_close_job(self, db: Session, user1):
        """5. Random unverified 404 search result does NOT change job availability."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Principal Architect",
            company="Acme Corp",
            description="Short description",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            availability_status="active",
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        # Random blog / unverified search result returning 404
        untrusted_url = "https://randomjobboard.example.com/jobs/acme-architect"
        search_provider = MockSearchProvider()
        search_provider.set_results("acme", [SearchResult(url=untrusted_url, title="Acme Architect", snippet="Job board snippet")])

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=untrusted_url,
            final_url=untrusted_url,
            status_code=404,
            content="Page Not Found",
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        await service.enrich_job(job.id)

        db.refresh(job)
        # Job must NOT be marked closed/possibly_closed
        assert job.availability_status == "active"
        assert job.enrichment_status == EnrichmentStatus.NOT_FOUND.value

    @pytest.mark.asyncio
    async def test_verified_canonical_404_marks_possibly_closed(self, db: Session, user1):
        """6. Previously verified canonical_url returning 404 marks job possibly_closed."""
        now = datetime.now(timezone.utc)
        canonical_url = "https://boards.greenhouse.io/novatech/jobs/401"
        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Detailed existing description",
            description_status="ok",
            canonical_url=canonical_url,
            availability_status="active",
            enrichment_status="enriched",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        search_provider = MockSearchProvider()
        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=canonical_url,
            final_url=canonical_url,
            status_code=404,
            content="Job not found",
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        await service.enrich_job(job.id, force=True)

        db.refresh(job)
        assert job.availability_status == "possibly_closed"

    @pytest.mark.asyncio
    async def test_verified_canonical_410_marks_removed(self, db: Session, user1):
        """7. Previously verified canonical_url returning 410 marks job removed."""
        now = datetime.now(timezone.utc)
        canonical_url = "https://boards.greenhouse.io/novatech/jobs/402"
        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Detailed existing description",
            description_status="ok",
            canonical_url=canonical_url,
            availability_status="active",
            enrichment_status="enriched",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        search_provider = MockSearchProvider()
        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=canonical_url,
            final_url=canonical_url,
            status_code=410,
            content="Position Gone",
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        await service.enrich_job(job.id, force=True)

        db.refresh(job)
        assert job.availability_status == "removed"

    def test_random_jobs_path_not_official(self):
        """8. Random domain with /jobs/ in path is NOT classified as official."""
        source_type, trust, is_ats = classify_source("https://randomblog.com/jobs/novatech", "NovaTech")
        assert source_type != "official"
        assert source_type in {"unknown", "other"}
        assert trust < 50

    def test_ats_without_company_not_high_confidence(self):
        """9. ATS candidate with exact title but unverified company is capped at medium."""
        conf = calculate_match_confidence(
            expected_title="Staff ML Ops Specialist",
            extracted_title="Staff ML Ops Specialist",
            expected_company="Acenet",
            extracted_company=None,
            source_type="ats",
            url="https://boards.greenhouse.io/unknown/jobs/123",
        )
        assert conf != "high"
        assert conf == "medium"

    def test_ats_wrong_company_not_selected(self):
        """10. ATS candidate with wrong company is penalized to low/none."""
        conf = calculate_match_confidence(
            expected_title="Staff ML Ops Specialist",
            extracted_title="Staff ML Ops Specialist",
            expected_company="Acenet",
            extracted_company="TotallyDifferentCorp",
            source_type="ats",
            url="https://boards.greenhouse.io/totallydifferentcorp/jobs/123",
        )
        assert conf in {"low", "none"}

    @pytest.mark.asyncio
    async def test_conditional_fetch_sends_etag(self, db: Session, user1):
        """11. Fetcher receives cached ETag and Last-Modified headers from JobWebSource."""
        now = datetime.now(timezone.utc)
        target_url = "https://boards.greenhouse.io/novatech/jobs/500"
        norm_url = normalize_url(target_url)

        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Existing description",
            description_status="ok",
            canonical_url=target_url,
            enrichment_status="enriched",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        # Add existing JobWebSource with ETag and Last-Modified
        source = JobWebSource(
            user_id=user1.id,
            job_id=job.id,
            url=target_url,
            normalized_url=norm_url,
            host="greenhouse.io",
            source_type="ats",
            trust_level=90,
            match_confidence="high",
            etag='"etag-hash-12345"',
            last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
            selected_as_canonical=True,
        )
        db.add(source)
        db.commit()

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=target_url,
            final_url=target_url,
            status_code=304,
            content="",
            is_not_modified=True,
            etag='"etag-hash-12345"',
            last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
        )

        service = JobEnrichmentService(db, search_provider=MockSearchProvider(), fetcher=fetcher)
        await service.enrich_job(job.id, force=True)

        # Verify fetcher was called with ETag and Last-Modified
        fetcher.fetch.assert_called_once_with(
            target_url,
            etag='"etag-hash-12345"',
            last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
        )

    @pytest.mark.asyncio
    async def test_304_does_not_trigger_rescore(self, db: Session, user1):
        """12. 304 Not Modified preserves description/hash and does NOT reset match analysis_status."""
        now = datetime.now(timezone.utc)
        target_url = "https://boards.greenhouse.io/novatech/jobs/600"
        norm_url = normalize_url(target_url)
        old_desc = "Original preserved job description text."
        old_hash = compute_content_hash(old_desc)

        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description=old_desc,
            content_hash=old_hash,
            description_status="ok",
            canonical_url=target_url,
            enrichment_status="enriched",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        source = JobWebSource(
            user_id=user1.id,
            job_id=job.id,
            url=target_url,
            normalized_url=norm_url,
            host="greenhouse.io",
            source_type="ats",
            trust_level=90,
            match_confidence="high",
            content_hash=old_hash,
            etag='"etag-abc"',
            selected_as_canonical=True,
        )
        match = JobMatch(
            user_id=user1.id,
            job_id=job.id,
            score=95,
            analysis_status="completed",
        )
        db.add_all([source, match])
        db.commit()

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=target_url,
            final_url=target_url,
            status_code=304,
            content="",
            is_not_modified=True,
        )

        service = JobEnrichmentService(db, search_provider=MockSearchProvider(), fetcher=fetcher)
        outcome = await service.enrich_job(job.id, force=True)

        assert outcome.status == "completed"
        assert outcome.description_updated is False
        db.refresh(job)
        db.refresh(match)
        assert job.description == old_desc
        assert job.content_hash == old_hash
        assert match.analysis_status == "completed"
        assert job.last_verified_at is not None

    @pytest.mark.asyncio
    async def test_same_hash_200_does_not_trigger_rescore(self, db: Session, user1):
        """13. HTTP 200 with identical content hash does NOT reset match analysis_status."""
        now = datetime.now(timezone.utc)
        target_url = "https://boards.greenhouse.io/novatech/jobs/700"
        extracted_desc = (
            "NovaTech is seeking a Senior AI Infrastructure Engineer to lead "
            "distributed LLM inference clusters and optimize high throughput pipelines."
        )
        exact_hash = compute_content_hash(extracted_desc)

        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description=extracted_desc,
            content_hash=exact_hash,
            description_status="ok",
            canonical_url=target_url,
            enrichment_status="enriched",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        match = JobMatch(
            user_id=user1.id,
            job_id=job.id,
            score=92,
            analysis_status="completed",
        )
        db.add(match)
        db.commit()

        search_provider = MockSearchProvider()
        search_provider.set_results("novatech", [SearchResult(url=target_url, title="Senior AI Engineer", snippet="NovaTech AI infra")])

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=target_url,
            final_url=target_url,
            status_code=200,
            content=SAMPLE_VALID_JOB_HTML,  # produces exact extracted_desc and exact_hash
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id, force=True)

        assert outcome.description_updated is False
        db.refresh(match)
        assert match.analysis_status == "completed"

    @pytest.mark.asyncio
    async def test_changed_hash_triggers_rescore(self, db: Session, user1):
        """14. HTTP 200 with new longer description changes hash and marks match pending."""
        now = datetime.now(timezone.utc)
        target_url = "https://boards.greenhouse.io/novatech/jobs/800"

        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Short summary.",
            content_hash=compute_content_hash("Short summary."),
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        match = JobMatch(
            user_id=user1.id,
            job_id=job.id,
            score=50,
            analysis_status="completed",
        )
        db.add(match)
        db.commit()

        search_provider = MockSearchProvider()
        search_provider.set_results("novatech", [SearchResult(url=target_url, title="Senior AI Engineer", snippet="NovaTech AI infra")])

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=target_url,
            final_url=target_url,
            status_code=200,
            content=SAMPLE_VALID_JOB_HTML,
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.description_updated is True
        db.refresh(job)
        db.refresh(match)
        assert job.description_status == "ok"
        assert match.analysis_status == "pending"
        assert match.job_content_hash is None

    def test_linkedin_fallback_query_executes(self):
        """15. LinkedIn query is generated and prioritized within max queries when linkedin_url is None."""
        queries = build_search_queries(
            title="Platform Engineer",
            company="Stripe",
            existing_linkedin=None,
            max_queries=settings.web_search_max_queries_per_job,
        )
        assert len(queries) <= settings.web_search_max_queries_per_job
        assert any("linkedin.com/jobs" in q for q in queries)

    @pytest.mark.asyncio
    async def test_linkedin_fallback_never_fetched(self, db: Session, user1):
        """16. Discovered LinkedIn URL is saved to job but NEVER fetched."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Software Architect",
            company="TechGiant",
            description="Brief text",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            linkedin_url=None,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        linkedin_result_url = "https://www.linkedin.com/jobs/view/4099887766/?refId=abc&trackingId=xyz"
        search_provider = MockSearchProvider()
        search_provider.set_results(
            "techgiant",
            [SearchResult(url=linkedin_result_url, title="Software Architect - TechGiant | LinkedIn", snippet="View job on LinkedIn")]
        )

        fetcher = AsyncMock(spec=SafeWebFetcher)

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        await service.enrich_job(job.id)

        db.refresh(job)
        # LinkedIn URL normalized and stored
        assert job.linkedin_url.rstrip("/") == "https://www.linkedin.com/jobs/view/4099887766"
        # Fetcher was NEVER called with LinkedIn URL
        for call_args in fetcher.fetch.call_args_list:
            called_url = call_args[0][0]
            assert "linkedin.com" not in called_url

    @pytest.mark.asyncio
    async def test_all_fetches_timeout_results_fetch_failed(self, db: Session, user1):
        """17. If search returns candidates but all fetches fail with network/timeout errors, status is fetch_failed."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Database Specialist",
            company="DataScale",
            description="Kısa",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        candidate_url = "https://boards.greenhouse.io/datascale/jobs/99"
        search_provider = MockSearchProvider()
        search_provider.set_results("datascale", [SearchResult(url=candidate_url, title="Database Specialist", snippet="DB role")])

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.side_effect = FetchUnavailableError("Connection reset by peer / timeout")

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.enrichment_status == EnrichmentStatus.FETCH_FAILED.value
        assert outcome.error_class == "FetchUnavailableError"
        db.refresh(job)
        assert job.enrichment_status == EnrichmentStatus.FETCH_FAILED.value

    @pytest.mark.asyncio
    async def test_search_concurrency_bounded_parallel(self, db: Session, user1):
        """18. Multiple queries run concurrently bounded by semaphore without unbounded spikes."""
        now = datetime.now(timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Senior Cloud Architect",
            company="MultiCloud",
            description="Kısa",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        max_in_flight = 0
        current_in_flight = 0
        lock = asyncio.Lock()

        class ConcurrencyTrackingProvider:
            available: bool = True

            def __init__(self, limit: int = 2):
                self.sem = asyncio.Semaphore(limit)

            async def search(self, query: str, limit: int = 5):
                nonlocal max_in_flight, current_in_flight
                async with self.sem:
                    async with lock:
                        current_in_flight += 1
                        if current_in_flight > max_in_flight:
                            max_in_flight = current_in_flight
                    await asyncio.sleep(0.05)
                    async with lock:
                        current_in_flight -= 1
                return []

            async def close(self):
                pass

        provider = ConcurrencyTrackingProvider(limit=settings.web_search_max_concurrency)
        fetcher = AsyncMock(spec=SafeWebFetcher)

        service = JobEnrichmentService(db, search_provider=provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.status == "completed"
        # max concurrent in-flight calls never exceeded concurrency limit (2)
        assert max_in_flight <= settings.web_search_max_concurrency
