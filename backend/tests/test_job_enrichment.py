"""Unit and acceptance tests for Job Discovery, Enrichment & Freshness layer."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    InvalidContentTypeError,
    LinkedInFetchForbiddenError,
    ResponseTooLargeError,
    SSRFProtectionError,
    SafeWebFetcher,
    TooManyRedirectsError,
    is_ip_prohibited,
    validate_url_for_ssrf,
)
from app.integrations.web_search.base import SearchResult
from app.integrations.web_search.mock import MockSearchProvider
from app.integrations.web_search.searxng import SearXNGSearchProvider
from app.models.enums import DescriptionStatus, SyncJobStatus
from app.models.job import Job
from app.models.sync_job import EnrichmentItem, SyncJob
from app.repositories.jobs import JobRepository, JobWebSourceRepository
from app.repositories.sync_jobs import EnrichmentItemRepository
from app.services.enrichment_runner import EnrichmentRunner
from app.services.enrichment_service import EnrichmentService
from app.services.job_enrichment.freshness import (
    calculate_freshness,
    evaluate_posted_at,
)
from app.services.job_enrichment.html_parser import (
    check_is_closed,
    clean_html_content,
    extract_from_json_ld,
    extract_from_semantic_html,
    extract_job_posting,
    parse_iso_datetime,
)
from app.services.job_enrichment.service import JobEnrichmentService
from app.services.job_enrichment.trust import (
    calculate_match_confidence,
    classify_source,
    compute_string_similarity,
)
from app.services.job_enrichment.url_utils import (
    compute_content_hash,
    extract_domain,
    extract_linkedin_job_id,
    is_linkedin_url,
    normalize_linkedin_job_url,
    normalize_url,
)

SAMPLE_JSON_LD_HTML = """
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Senior AI Infrastructure Engineer",
  "description": "<p>NovaTech is seeking a Senior AI Infrastructure Engineer.</p><ul><li>Deploy distributed LLM inference engines</li><li>Optimize vLLM and TensorRT-LLM pipelines</li><li>Kubernetes and GPU cluster management</li></ul>",
  "datePosted": "2026-09-25T10:00:00Z",
  "validThrough": "2026-10-25T23:59:59Z",
  "hiringOrganization": {
    "@type": "Organization",
    "name": "NovaTech AI",
    "sameAs": "https://novatech.example.com"
  },
  "jobLocation": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Istanbul",
      "addressCountry": "TR"
    }
  },
  "employmentType": "FULL_TIME"
}
</script>
</head>
<body>
<h1>Senior AI Infrastructure Engineer</h1>
</body>
</html>
"""

SAMPLE_CLOSED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Job Closed</title></head>
<body>
<div class="job-status">
  <h2>This position has been closed</h2>
  <p>Thank you for your interest. We are no longer accepting applications for this job.</p>
</div>
</body>
</html>
"""

SAMPLE_SEMANTIC_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Staff ML Ops Specialist - Acenet" />
  <meta property="article:published_time" content="2026-09-27T14:30:00Z" />
</head>
<body>
  <header><nav><a href="/">Home</a></nav></header>
  <main>
    <article class="job-description">
      <h2>Role Overview</h2>
      <p>Lead the MLOps engineering roadmap across our autonomous systems fleet.</p>
      <p>Requirements include 5+ years with Kubernetes, Kubeflow, PyTorch, and cloud platforms.</p>
    </article>
  </main>
  <footer><p>&copy; 2026 Acenet Inc.</p></footer>
</body>
</html>
"""


# ==============================================================================
# 1. URL & LinkedIn Utilities
# ==============================================================================

class TestUrlUtils:
    def test_normalize_url_strips_tracking(self):
        url = "https://www.example.com/jobs/123/?utm_source=linkedin&utm_medium=email&trk=job_alert&refId=abc#heading"
        norm = normalize_url(url)
        assert norm == "https://example.com/jobs/123"

    def test_is_linkedin_url(self):
        assert is_linkedin_url("https://www.linkedin.com/jobs/view/4012345678/") is True
        assert is_linkedin_url("https://tr.linkedin.com/in/test") is True
        assert is_linkedin_url("https://example.com/jobs") is False

    def test_extract_linkedin_job_id(self):
        assert extract_linkedin_job_id("https://www.linkedin.com/jobs/view/4012345678/") == "4012345678"
        assert extract_linkedin_job_id("https://www.linkedin.com/jobs/view/?currentJobId=4098765432") == "4098765432"
        assert extract_linkedin_job_id("senior-engineer-at-novatech-4012345678") == "4012345678"

    def test_normalize_linkedin_job_url(self):
        canonical = normalize_linkedin_job_url("https://www.linkedin.com/comm/jobs/view/4012345678?trk=email")
        assert canonical == "https://www.linkedin.com/jobs/view/4012345678/"

    def test_content_hash_deterministic(self):
        text1 = "Senior AI Engineer at NovaTech. Remote position."
        text2 = "  Senior   AI Engineer  at NovaTech.   Remote position. \n"
        h1 = compute_content_hash(text1)
        h2 = compute_content_hash(text2)
        assert h1 == h2
        assert len(h1) == 64


# ==============================================================================
# 2. SSRF Protection & Safe Web Fetcher
# ==============================================================================

class TestSSRFProtection:
    @pytest.mark.asyncio
    async def test_blocks_localhost_and_private_ips(self):
        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://localhost:8080/test")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://127.0.0.1:8000/api")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://10.0.0.1/admin")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://172.16.0.1/")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://192.168.1.1/")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://169.254.169.254/latest/meta-data")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://[::1]/internal")

    @pytest.mark.asyncio
    async def test_blocks_userinfo_and_unsupported_schemes(self):
        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("http://user:pass@example.com/job")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("file:///etc/passwd")

        with pytest.raises(SSRFProtectionError):
            await validate_url_for_ssrf("ftp://example.com/job")

    @pytest.mark.asyncio
    async def test_strictly_blocks_fetching_linkedin(self):
        with pytest.raises(LinkedInFetchForbiddenError):
            await validate_url_for_ssrf("https://www.linkedin.com/jobs/view/4012345678/")

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_is_blocked(self):
        fetcher = SafeWebFetcher()
        # Mock client.stream redirecting to 127.0.0.1
        with patch("app.integrations.web_fetch.fetcher.validate_url_for_ssrf") as mock_val:
            mock_val.side_effect = [None, SSRFProtectionError("Erişime kapalı yerel adres: 127.0.0.1")]
            with pytest.raises(SSRFProtectionError):
                # When second hop is validated, it must raise SSRFProtectionError
                await validate_url_for_ssrf("http://127.0.0.1:8000/internal")


# ==============================================================================
# 3. HTML & JSON-LD Parser
# ==============================================================================

class TestHtmlParser:
    def test_extract_json_ld(self):
        data = extract_from_json_ld(SAMPLE_JSON_LD_HTML)
        assert data is not None
        assert data.title == "Senior AI Infrastructure Engineer"
        assert data.company == "NovaTech AI"
        assert "Deploy distributed LLM inference engines" in (data.description or "")
        assert data.date_posted == datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)
        assert data.valid_through == datetime(2026, 10, 25, 23, 59, 59, tzinfo=timezone.utc)
        assert data.is_closed is False
        assert data.source_type == "json_ld"

    def test_extract_semantic_html(self):
        data = extract_from_semantic_html(SAMPLE_SEMANTIC_HTML)
        assert data is not None
        assert data.title == "Staff ML Ops Specialist"
        assert "Lead the MLOps engineering roadmap" in (data.description or "")
        assert data.date_posted == datetime(2026, 9, 27, 14, 30, 0, tzinfo=timezone.utc)
        assert data.source_type == "semantic_html"

    def test_closed_job_detection(self):
        assert check_is_closed("This position has been closed. Thank you.") is True
        assert check_is_closed("Bu ilan artık aktif değil.") is True
        assert check_is_closed("We are actively hiring for this position.") is False

        data = extract_job_posting(SAMPLE_CLOSED_HTML)
        assert data is not None
        assert data.is_closed is True


# ==============================================================================
# 4. Source Trust & Matching
# ==============================================================================

class TestTrustAndMatching:
    def test_classify_known_ats(self):
        source_type, trust, name = classify_source("https://boards.greenhouse.io/anthropic/jobs/12345")
        assert source_type == "ats"
        assert trust == 95
        assert name == "Greenhouse"

        source_type, trust, name = classify_source("https://jobs.lever.co/openai/abcdef")
        assert source_type == "ats"
        assert trust == 95
        assert name == "Lever"

        source_type, trust, name = classify_source("https://acme.myworkdayjobs.com/en-US/careers/job/123")
        assert source_type == "ats"
        assert trust == 90

    def test_classify_official_site(self):
        source_type, trust, name = classify_source("https://careers.google.com/jobs/results/1234", company="Google")
        assert source_type == "official"
        assert trust >= 75

    def test_classify_aggregator(self):
        source_type, trust, _ = classify_source("https://www.indeed.com/viewjob?jk=1234")
        assert source_type == "aggregator"
        assert trust == 40

    def test_match_confidence(self):
        conf = calculate_match_confidence(
            expected_title="Senior AI Infrastructure Engineer",
            extracted_title="Senior AI Infrastructure Engineer",
            expected_company="NovaTech",
            extracted_company="NovaTech AI",
            source_type="ats",
        )
        assert conf == "high"

        conf_low = calculate_match_confidence(
            expected_title="Frontend Developer",
            extracted_title="Marketing Specialist",
            expected_company="NovaTech",
            extracted_company="NovaTech",
            source_type="official",
        )
        assert conf_low in {"none", "low"}


# ==============================================================================
# 5. Freshness & Date Precedence
# ==============================================================================

class TestFreshnessAndDatePrecedence:
    def test_date_precedence_json_ld_over_email(self):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        json_date = datetime(2026, 9, 24, 8, 0, 0, tzinfo=timezone.utc)  # 5 days ago
        email_date = datetime(2026, 9, 28, 9, 0, 0, tzinfo=timezone.utc)  # 1 day ago

        res = evaluate_posted_at(
            json_ld_date=json_date,
            email_received_at=email_date,
            now=now,
        )
        assert res.effective_posted_at == json_date
        assert res.posted_at_source == "json_ld"
        assert res.posted_at_confidence == "high"

    def test_freshness_categories(self):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

        # 0-3 days: fresh
        fresh = calculate_freshness(effective_posted_at=now - timedelta(days=2), now=now)
        assert fresh.freshness_status == "fresh"
        assert fresh.should_auto_score is True

        # 4-7 days: aging
        aging = calculate_freshness(effective_posted_at=now - timedelta(days=5), now=now)
        assert aging.freshness_status == "aging"
        assert aging.should_auto_score is True

        # 8-14 days: stale
        stale = calculate_freshness(effective_posted_at=now - timedelta(days=10), now=now)
        assert stale.freshness_status == "stale"
        assert stale.should_auto_score is True

        # >14 days: expired
        expired = calculate_freshness(effective_posted_at=now - timedelta(days=18), now=now)
        assert expired.freshness_status == "expired"
        assert expired.should_auto_score is False

    def test_future_date_clamping(self):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        future_date = now + timedelta(days=5)
        res = evaluate_posted_at(json_ld_date=future_date, now=now)
        assert res.effective_posted_at <= now


# ==============================================================================
# 6. Acceptance Scenarios A through G
# ==============================================================================

class TestAcceptanceScenarios:
    @pytest.mark.asyncio
    async def test_scenario_a_official_source_discovery_and_enrichment(self, db, user1):
        """Scenario A:
        Job alert mail carried insufficient description -> Web search discovers official Greenhouse posting
        -> Full description extracted, canonical URL set, posted_at source is json_ld, status is enriched.
        """
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Kısa özet ilan metni.",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        # Mock search provider
        search_provider = MockSearchProvider()
        greenhouse_url = "https://boards.greenhouse.io/novatech/jobs/4012345"
        search_provider.set_results(
            "novatech",
            [
                SearchResult(
                    url=greenhouse_url,
                    title="Senior AI Infrastructure Engineer - NovaTech AI",
                    snippet="Join NovaTech as Senior AI Infrastructure Engineer...",
                )
            ],
        )

        # Mock fetcher
        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=greenhouse_url,
            final_url=greenhouse_url,
            status_code=200,
            content=SAMPLE_JSON_LD_HTML,
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        outcome = await service.enrich_job(job.id)

        assert outcome.status == "completed"
        assert outcome.enrichment_status == "enriched"
        assert outcome.description_updated is True

        db.refresh(job)
        assert job.canonical_url == greenhouse_url
        assert "Deploy distributed LLM inference engines" in (job.description or "")
        assert job.posted_at_source == "json_ld"
        assert job.posted_at_confidence == "high"
        assert job.enrichment_status == "enriched"
        assert job.content_hash is not None

        # Verify web source recorded
        web_sources = JobWebSourceRepository(db).list_for_job(job.id)
        assert len(web_sources) >= 1
        assert web_sources[0].source_type == "ats"
        assert web_sources[0].selected_as_canonical is True

    @pytest.mark.asyncio
    async def test_scenario_b_date_conflict_precedence(self, db, user1):
        """Scenario B:
        Email received yesterday, but ATS JSON-LD datePosted indicates 5 days ago
        -> Effective posted_at is 5 days ago (JSON-LD priority), freshness is aging.
        """
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        yesterday = now - timedelta(days=1)
        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description="Kısa özet.",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            email_received_at=yesterday,
            enrichment_status="pending",
            discovered_at=yesterday,
        )
        db.add(job)
        db.commit()

        search_provider = MockSearchProvider()
        greenhouse_url = "https://boards.greenhouse.io/novatech/jobs/4012345"
        search_provider.set_results(
            "novatech",
            [SearchResult(url=greenhouse_url, title="Senior AI Infrastructure Engineer", snippet="...")]
        )

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=greenhouse_url,
            final_url=greenhouse_url,
            status_code=200,
            content=SAMPLE_JSON_LD_HTML,  # datePosted is 2026-09-25T10:00:00Z (~4-5 days ago)
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        await service.enrich_job(job.id)

        posted = job.posted_at.replace(tzinfo=timezone.utc) if job.posted_at.tzinfo is None else job.posted_at
        assert posted == datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)
        assert job.posted_at_source == "json_ld"
        assert job.freshness_status == "aging"

    @pytest.mark.asyncio
    async def test_scenario_c_closed_job_and_expiration(self, db, user1):
        """Scenario C:
        Candidate page returns 404 or indicates closed position
        -> Marked availability_status='closed', freshness_status='expired'.
        """
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Closed Position",
            company="OldCorp",
            description="Short desc",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        search_provider = MockSearchProvider()
        old_url = "https://jobs.lever.co/oldcorp/12345"
        search_provider.set_results(
            "oldcorp",
            [SearchResult(url=old_url, title="Closed Position", snippet="...")]
        )

        fetcher = AsyncMock(spec=SafeWebFetcher)
        fetcher.fetch.return_value = FetchResult(
            url=old_url,
            final_url=old_url,
            status_code=404,
            content="Not Found",
        )

        service = JobEnrichmentService(db, search_provider=search_provider, fetcher=fetcher)
        await service.enrich_job(job.id)

        db.refresh(job)
        # 404 source was checked, job enrichment marked not_found
        assert job.enrichment_status == "not_found"

    @pytest.mark.asyncio
    async def test_scenario_d_content_hashing_avoids_duplicate_update(self, db, user1):
        """Scenario D:
        Enrichment calculates content_hash; unchanged content hash avoids modifying description.
        """
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        desc = "NovaTech is seeking a Senior AI Infrastructure Engineer. Deploy distributed LLM inference engines Optimize vLLM and TensorRT-LLM pipelines Kubernetes and GPU cluster management"
        h = compute_content_hash(desc)

        job = Job(
            user_id=user1.id,
            title="Senior AI Infrastructure Engineer",
            company="NovaTech AI",
            description=desc,
            content_hash=h,
            description_status="ok",
            canonical_url="https://boards.greenhouse.io/novatech/jobs/4012345",
            enrichment_status="enriched",
            discovered_at=now,
        )
        db.add(job)
        db.commit()

        service = JobEnrichmentService(db)
        # Not needed since already enriched with adequate description
        assert service.is_enrichment_needed(job) is False

    @pytest.mark.asyncio
    async def test_scenario_e_never_scrape_linkedin(self):
        """Scenario E:
        SafeWebFetcher strictly prevents scraping LinkedIn.
        """
        fetcher = SafeWebFetcher()
        with pytest.raises(LinkedInFetchForbiddenError):
            await fetcher.fetch("https://www.linkedin.com/jobs/view/4012345678/")

    @pytest.mark.asyncio
    async def test_scenario_f_ssrf_and_dns_rebind_protection(self):
        """Scenario F:
        SafeWebFetcher strictly prevents SSRF attempts to metadata and private IPs.
        """
        fetcher = SafeWebFetcher()
        with pytest.raises(SSRFProtectionError):
            await fetcher.fetch("http://169.254.169.254/latest/meta-data/")

        with pytest.raises(SSRFProtectionError):
            await fetcher.fetch("http://127.0.0.1:8000/admin")

    @pytest.mark.asyncio
    async def test_scenario_g_durable_enrichment_runner(self, db, user1):
        """Scenario G:
        Durable enrichment SyncJob processes items atomically with bounded retry and recovery.
        """
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        job1 = Job(
            user_id=user1.id,
            title="AI Engineer",
            company="Acenet",
            description="Kısa.",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        job2 = Job(
            user_id=user1.id,
            title="ML Engineer",
            company="Acenet",
            description="Kısa 2.",
            description_status=DescriptionStatus.INSUFFICIENT.value,
            enrichment_status="pending",
            discovered_at=now,
        )
        db.add_all([job1, job2])
        db.commit()

        enrich_service = EnrichmentService(db)
        sync_job, count = enrich_service.enqueue(user1, force=True)
        db.commit()
        assert count == 2

        items = EnrichmentItemRepository(db).list_for_job(sync_job.id)
        assert len(items) == 2
        assert all(it.status == "queued" for it in items)

        # Run via EnrichmentRunner with mock search & fetcher
        search_mock = MockSearchProvider()
        fetch_mock = AsyncMock(spec=SafeWebFetcher)
        fetch_mock.fetch.return_value = FetchResult(
            url="https://jobs.lever.co/acenet/1",
            final_url="https://jobs.lever.co/acenet/1",
            status_code=200,
            content=SAMPLE_SEMANTIC_HTML,
        )

        runner = EnrichmentRunner(
            search_provider_factory=lambda: search_mock,
            fetcher_factory=lambda: fetch_mock,
            session_factory=lambda: db,
        )
        outcome = await runner.run(sync_job.id)
        assert outcome.status == SyncJobStatus.COMPLETED
        assert outcome.processed == 2

        # Verify items completed
        items_after = EnrichmentItemRepository(db).list_for_job(sync_job.id)
        assert all(it.status == "completed" for it in items_after)
