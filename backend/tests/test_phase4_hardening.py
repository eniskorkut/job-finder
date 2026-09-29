"""Comprehensive unit & integration tests for Phase 4 Hardening:
- SSRF & DNS rebinding IP pinning
- SafeWebFetcher retries, 304 handling, and LinkedIn guard
- Detached Job Enrichment DTO pipeline
- TTL policies, 404/410 availability handling, date clamping
- Re-scoring trigger on rich description enrichment
- Telegram message formatting with freshness and provenance
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    FetchTimeoutError,
    FetchUnavailableError,
    LinkedInFetchForbiddenError,
    SSRFGuardedBackend,
    SSRFGuardedTransport,
    SSRFProtectionError,
    SafeWebFetcher,
    backoff_delay,
    parse_retry_after,
    validate_url_for_ssrf,
)
from app.integrations.web_search.base import SearchResult, SearchUnavailableError
from app.integrations.web_search.mock import MockSearchProvider
from app.models.enums import DescriptionStatus, MatchStatus, SyncJobStatus
from app.models.job import Job, JobMatch
from app.repositories.jobs import JobRepository, JobWebSourceRepository
from app.services.enrichment_runner import EnrichmentRunner
from app.services.job_enrichment.dtos import (
    JobEnrichmentResult,
    JobEnrichmentSnapshot,
)
from app.services.job_enrichment.freshness import (
    calculate_freshness,
    evaluate_posted_at,
)
from app.services.job_enrichment.html_parser import (
    extract_from_json_ld,
    extract_job_posting,
)
from app.services.job_enrichment.service import (
    JobEnrichmentService,
    execute_enrichment_flow,
    is_enrichment_needed,
    persist_result,
    take_snapshot,
)
from app.services.notification_service import NotificationService
from app.services.scoring_service import MODE_NEW, MODE_REANALYZE, ScoringService
from app.services.telegram_message import build_match_message, format_relative_date


class TestSSRFAndDnsRebinding:
    @pytest.mark.asyncio
    async def test_port_validation(self):
        backend = SSRFGuardedBackend(allowed_ports={80, 443})
        # Port 8080 should be blocked
        with pytest.raises(SSRFProtectionError, match="Erişime kapalı bağlantı noktası: 8080"):
            await backend.connect_tcp("93.184.216.34", 8080)

    @pytest.mark.asyncio
    async def test_ip_pinning_and_private_ip_interception(self):
        backend = SSRFGuardedBackend(allowed_ports={80, 443})

        # Intercept direct private IP
        with pytest.raises(SSRFProtectionError):
            await backend.connect_tcp("127.0.0.1", 80)

        with pytest.raises(SSRFProtectionError):
            await backend.connect_tcp("169.254.169.254", 80)

        with pytest.raises(SSRFProtectionError):
            await backend.connect_tcp("10.0.0.5", 80)

    @pytest.mark.asyncio
    async def test_dns_rebinding_intercepts_prohibited_dns_records(self):
        backend = SSRFGuardedBackend(allowed_ports={80, 443})
        # Mock getaddrinfo returning loopback address for malicious domain
        mock_addr = [(None, None, None, None, ("127.0.0.1", 80))]

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=mock_addr)
            with pytest.raises(SSRFProtectionError, match="erişimi engellenen özel/dahili IP"):
                await backend.connect_tcp("malicious-rebind.example.com", 80)


class TestSafeWebFetcherHardening:
    @pytest.mark.asyncio
    async def test_retry_after_parsing(self):
        assert parse_retry_after("12") == 12.0
        assert parse_retry_after("0") == 0.0
        assert parse_retry_after("invalid") is None
        assert parse_retry_after(None) is None
        # Max cap
        assert parse_retry_after("300", max_delay=60.0) == 60.0

    @pytest.mark.asyncio
    async def test_never_scrape_linkedin(self):
        fetcher = SafeWebFetcher()
        with pytest.raises(LinkedInFetchForbiddenError):
            await fetcher.fetch("https://www.linkedin.com/jobs/view/4012345678/")

    @pytest.mark.asyncio
    async def test_retries_on_transient_http_errors(self):
        sleep_calls: list[float] = []

        async def fake_sleep(d: float):
            sleep_calls.append(d)

        # Mock client that fails twice with 429, then succeeds with 200
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"retry-after": "1.5"}
        mock_response_429.is_redirect = False

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.headers = {"content-type": "text/html"}
        mock_response_200.is_redirect = False
        mock_response_200.encoding = "utf-8"

        async def fake_aiter_bytes():
            yield b"<html><body><h1>Job</h1></body></html>"

        mock_response_200.aiter_bytes = fake_aiter_bytes

        mock_stream_ctx_429 = MagicMock()
        mock_stream_ctx_429.__aenter__ = AsyncMock(return_value=mock_response_429)
        mock_stream_ctx_429.__aexit__ = AsyncMock(return_value=None)

        mock_stream_ctx_200 = MagicMock()
        mock_stream_ctx_200.__aenter__ = AsyncMock(return_value=mock_response_200)
        mock_stream_ctx_200.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(side_effect=[mock_stream_ctx_429, mock_stream_ctx_200])
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()

        fetcher = SafeWebFetcher(
            client=mock_client,
            sleeper=fake_sleep,
            retry_max_attempts=3,
        )

        with patch("app.integrations.web_fetch.fetcher.validate_url_for_ssrf", new=AsyncMock()):
            res = await fetcher.fetch("https://example.com/careers/1")
            assert res.status_code == 200
            assert "Job" in res.content
            assert len(sleep_calls) == 1
            assert sleep_calls[0] == 1.5

    @pytest.mark.asyncio
    async def test_handles_304_not_modified(self):
        mock_response_304 = MagicMock()
        mock_response_304.status_code = 304
        mock_response_304.headers = {"etag": '"abc123etag"', "last-modified": "Wed, 21 Oct 2026 07:28:00 GMT"}
        mock_response_304.is_redirect = False

        mock_stream_ctx_304 = MagicMock()
        mock_stream_ctx_304.__aenter__ = AsyncMock(return_value=mock_response_304)
        mock_stream_ctx_304.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx_304)
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()

        fetcher = SafeWebFetcher(client=mock_client)
        with patch("app.integrations.web_fetch.fetcher.validate_url_for_ssrf", new=AsyncMock()):
            res = await fetcher.fetch("https://example.com/jobs/1", etag='"abc123etag"')
            assert res.status_code == 304
            assert res.is_not_modified is True
            assert res.etag == '"abc123etag"'


class TestEnrichmentPoliciesAndDecoupledPipeline:
    def test_ttl_policy_enforcement(self):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        snapshot = JobEnrichmentSnapshot(
            job_id=datetime.now().microsecond,
            user_id=datetime.now().microsecond,
            title="AI Engineer",
            company="NovaTech",
            description="Detailed job description with more than forty words to ensure it qualifies as adequate text.",
            description_status="ok",
            posted_at=now - timedelta(days=2),
            posted_at_source="json_ld",
            posted_at_confidence="high",
            valid_through=now + timedelta(days=10),
            email_received_at=now - timedelta(days=2),
            discovered_at=now - timedelta(days=2),
            freshness_status="fresh",
            availability_status="active",
            enrichment_status="enriched",
            content_hash="abc",
            canonical_url="https://novatech.com/careers/1",
            company_job_url="https://novatech.com/careers/1",
            application_url="https://novatech.com/careers/1",
            linkedin_url="https://www.linkedin.com/jobs/view/123/",
            url="https://novatech.com/careers/1",
            last_enriched_at=now - timedelta(hours=6),
            last_verified_at=now - timedelta(hours=6),
        )

        # Enriched 6 hours ago -> TTL is 24h -> Should NOT be needed
        assert is_enrichment_needed(snapshot, force=False, now=now) is False

        # If forced -> ALWAYS True
        assert is_enrichment_needed(snapshot, force=True, now=now) is True

        # Enriched 30 hours ago -> TTL expired -> Needs enrichment
        snapshot.last_enriched_at = now - timedelta(hours=30)
        assert is_enrichment_needed(snapshot, force=False, now=now) is True

    def test_future_date_clamp_and_broken_valid_through(self):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

        # Buggy future date (> 24 hours into future) must be rejected
        future_date = now + timedelta(days=30)
        email_date = now - timedelta(days=1)
        res = evaluate_posted_at(
            json_ld_date=future_date,
            email_received_at=email_date,
            discovered_at=now,
            now=now,
        )
        assert res.effective_posted_at == email_date
        assert res.posted_at_source == "email_date"

        # Broken valid_through before posted date should be ignored
        broken_valid_through = now - timedelta(days=5)
        freshness = calculate_freshness(
            effective_posted_at=now - timedelta(days=1),
            valid_through=broken_valid_through,
            now=now,
        )
        assert freshness.freshness_status == "fresh"
        assert freshness.availability_status == "active"
        assert freshness.should_auto_score is True

    @pytest.mark.asyncio
    async def test_404_and_410_availability_handling(self):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        snapshot = JobEnrichmentSnapshot(
            job_id=datetime.now().microsecond,
            user_id=datetime.now().microsecond,
            title="Backend Engineer",
            company="Acme",
            description="Short desc",
            description_status="insufficient_description",
            posted_at=None,
            posted_at_source=None,
            posted_at_confidence=None,
            valid_through=None,
            email_received_at=now - timedelta(days=2),
            discovered_at=now - timedelta(days=2),
            freshness_status="unknown",
            availability_status="unknown",
            enrichment_status="pending",
            content_hash=None,
            canonical_url=None,
            company_job_url=None,
            application_url=None,
            linkedin_url="https://www.linkedin.com/jobs/view/999/",
            url=None,
            last_enriched_at=None,
            last_verified_at=None,
        )

        search_mock = MockSearchProvider()
        search_mock.set_results(
            "acme",
            [SearchResult(url="https://jobs.lever.co/acme/1", title="Acme Backend", snippet="Lever ATS")],
        )
        fetch_mock = AsyncMock(spec=SafeWebFetcher)

        # Case 1: Official site returns 404 -> possibly_closed
        fetch_mock.fetch.return_value = FetchResult(
            url="https://jobs.lever.co/acme/1",
            final_url="https://jobs.lever.co/acme/1",
            status_code=404,
            content="",
        )

        res_404 = await execute_enrichment_flow(
            snapshot,
            search_mock,
            fetch_mock,
            force=True,
            now=now,
        )
        assert res_404.availability_status == "possibly_closed"
        assert res_404.freshness_status == "expired"

        # Case 2: Official site returns 410 -> removed
        fetch_mock.fetch.return_value = FetchResult(
            url="https://jobs.lever.co/acme/1",
            final_url="https://jobs.lever.co/acme/1",
            status_code=410,
            content="",
        )

        res_410 = await execute_enrichment_flow(
            snapshot,
            search_mock,
            fetch_mock,
            force=True,
            now=now,
        )
        assert res_410.availability_status == "removed"
        assert res_410.freshness_status == "expired"


class TestReScoringAndNotifications:
    @pytest.mark.asyncio
    async def test_enrichment_description_update_triggers_rescore(self, db, user1):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Senior Staff Engineer",
            company="NovaTech",
            description="Kısa açıklama.",
            description_status="insufficient_description",
            freshness_status="fresh",
            availability_status="active",
            enrichment_status="pending",
            discovered_at=now,
            posted_at=now - timedelta(days=1),
            content_hash="old_hash_123",
        )
        db.add(job)
        db.flush()

        match = JobMatch(
            user_id=user1.id,
            job_id=job.id,
            score=75,
            confidence=80,
            analysis_status="completed",
            job_content_hash="old_hash_123",
        )
        db.add(match)
        db.commit()

        # Simulate enrichment discovering rich description
        rich_desc = "NovaTech is seeking a Senior Staff Engineer to lead high performance distributed machine learning inference platforms across our enterprise clusters with deep PyTorch experience."
        enrich_result = JobEnrichmentResult(
            job_id=job.id,
            status="completed",
            enrichment_status="enriched",
            freshness_status="fresh",
            availability_status="active",
            canonical_url="https://novatech.example.com/jobs/1",
            new_description=rich_desc,
            new_content_hash="new_rich_hash_456",
            description_updated=True,
            last_enriched_at=now,
            last_verified_at=now,
        )

        snapshot = take_snapshot(db, job.id)
        assert snapshot is not None

        persist_result(db, enrich_result, snapshot)
        db.commit()

        # Verify job description and match status updated
        refreshed_job = db.get(Job, job.id)
        assert refreshed_job.description == rich_desc
        assert refreshed_job.content_hash == "new_rich_hash_456"

        refreshed_match = db.get(JobMatch, match.id)
        # Because content changed, analysis_status was reset to pending!
        assert refreshed_match.analysis_status == "pending"

    def test_telegram_message_contains_freshness_and_provenance(self, user1):
        now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        job = Job(
            user_id=user1.id,
            title="Lead AI Engineer",
            company="NovaTech",
            location="Istanbul",
            work_mode="remote",
            freshness_status="fresh",
            posted_at=now - timedelta(days=2),
            canonical_url="https://jobs.lever.co/novatech/1",
            application_url="https://jobs.lever.co/novatech/1",
            linkedin_url="https://www.linkedin.com/jobs/view/4012345678/",
        )
        match = JobMatch(
            user_id=user1.id,
            job_id=job.id,
            score=88,
            confidence=92,
            rationale="Harika profil uyumu.",
            matched_skills=["Python", "PyTorch", "Kubernetes"],
            missing_skills=["Rust"],
        )

        msg = build_match_message(job=job, match=match, score_threshold=70, now=now)
        assert "Lead AI Engineer" in msg
        assert "88" in msg
        assert "2 gün önce" in msg
        assert "Taze (Son 3 gün)" in msg
        assert "Resmi Başvuru Sayfası" in msg
        assert "LinkedIn İlanı" in msg
        assert "https://jobs.lever.co/novatech/1" in msg
        assert "https://www.linkedin.com/jobs/view/4012345678/" in msg
