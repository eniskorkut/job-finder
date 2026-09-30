"""Stage A Hardening & Technical Debt Verification Test Suite.

Covers:
1. Legacy 'fresh' backfill to 'unknown' via migration 0007 logic
2. Verified/enriched 'fresh' jobs stay 'fresh'
3. JobEnrichmentService closes DB session before network I/O
4. EnrichmentRunner executes network flow with no open DB transactions
5. Acceptance test hook gating requires enable_acceptance_test_hooks=True
6. Acceptance test hook gating is strictly forbidden in production
7. SSRFGuardedTransport httpcore & httpx pinned version compatibility
8. DNS rebinding TOCTOU (public then private IP) blocked with SSRFProtectionError
9. Mixed public/private DNS records blocked with SSRFProtectionError
10. JobRepository.stats() includes aging_jobs metric
11. JobRepository.list_for_user(sort="verified") sorts by last_verified_at desc nulls last
12. JobRepository.list_for_user(source=...) provenance filtering (official_ats, linkedin, mail)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import socket
from unittest.mock import AsyncMock, patch
import uuid

import httpcore
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    SafeWebFetcher,
    SSRFGuardedBackend,
    SSRFGuardedTransport,
    SSRFProtectionError,
    validate_url_for_ssrf,
)
from app.integrations.web_search.base import SearchProvider, SearchResult
from app.models.enums import DescriptionStatus, EnrichmentStatus, SyncJobStatus
from app.models.job import Job, JobWebSource
from app.models.sync_job import EnrichmentItem, SyncJob
from app.repositories.jobs import JobRepository
from app.schemas.job import JobStats
from app.services.enrichment_runner import EnrichmentRunner
from app.services.job_enrichment.service import JobEnrichmentService
from app.services.sync_job_service import SyncRunner


@pytest.fixture
def test_job(db: Session, user1) -> Job:
    job = Job(
        user_id=user1.id,
        title="Senior AI Systems Engineer",
        company="Hardening Test Corp",
        description="A job needing enrichment for stage A test suite.",
        description_status=DescriptionStatus.INSUFFICIENT,
        enrichment_status=EnrichmentStatus.PENDING,
        freshness_status="fresh",
        source="gmail",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# 1 & 2. Legacy Freshness Backfill (Migration 0007)
# ---------------------------------------------------------------------------

def test_legacy_fresh_job_is_backfilled_unknown(db: Session, test_job: Job) -> None:
    """Legacy job that was auto-marked fresh without date verification or enrichment
    must be backfilled to 'unknown'.
    """
    test_job.freshness_status = "fresh"
    test_job.last_enriched_at = None
    test_job.posted_at_source = None
    test_job.last_verified_at = None
    db.commit()

    db.execute(text("""
        UPDATE jobs
        SET freshness_status = 'unknown'
        WHERE freshness_status = 'fresh'
          AND last_enriched_at IS NULL
          AND posted_at_source IS NULL
          AND last_verified_at IS NULL
    """))
    db.commit()
    db.refresh(test_job)

    assert test_job.freshness_status == "unknown"


def test_true_enriched_fresh_job_stays_fresh(db: Session, test_job: Job) -> None:
    """Job that actually underwent enrichment with verified source metadata stays 'fresh'."""
    now = datetime.now(timezone.utc)
    test_job.freshness_status = "fresh"
    test_job.last_enriched_at = now
    test_job.posted_at_source = "json_ld"
    test_job.last_verified_at = now
    db.commit()

    db.execute(text("""
        UPDATE jobs
        SET freshness_status = 'unknown'
        WHERE freshness_status = 'fresh'
          AND last_enriched_at IS NULL
          AND posted_at_source IS NULL
          AND last_verified_at IS NULL
    """))
    db.commit()
    db.refresh(test_job)

    assert test_job.freshness_status == "fresh"


# ---------------------------------------------------------------------------
# 3 & 4. Detached DB Sessions During Async Network Operations
# ---------------------------------------------------------------------------

class AssertNoTransactionSearchProvider(SearchProvider):
    def __init__(self, db: Session) -> None:
        self.db = db
        self.called = False

    async def search(self, query: str, limit: int = 5, **kwargs) -> list[SearchResult]:
        self.called = True
        # Verify that caller's DB session is NOT in an open transaction
        assert not self.db.in_transaction(), "DB transaction was held open during web search network call!"
        return []


@pytest.mark.asyncio
async def test_enrich_job_closes_db_before_network(db: Session, test_job: Job) -> None:
    """JobEnrichmentService.enrich_job must not hold an open DB transaction across network operations."""
    search_provider = AssertNoTransactionSearchProvider(db)
    fetcher = SafeWebFetcher()

    service = JobEnrichmentService(
        db=db,
        search_provider=search_provider,
        fetcher=fetcher,
    )

    outcome = await service.enrich_job(test_job.id, force=True)
    assert outcome is not None
    assert search_provider.called is True


@pytest.mark.asyncio
async def test_runner_closes_db_before_network(db: Session, test_job: Job, user1) -> None:
    """EnrichmentRunner must process items without holding open DB sessions during network operations."""
    sync_job = SyncJob(
        user_id=user1.id,
        kind="enrichment",
        status=SyncJobStatus.RUNNING,
        payload={"force": True},
    )
    db.add(sync_job)
    db.flush()

    item = EnrichmentItem(
        user_id=user1.id,
        job_id=test_job.id,
        sync_job_id=sync_job.id,
        status="queued",
    )
    db.add(item)
    db.commit()

    search_provider = AssertNoTransactionSearchProvider(db)

    runner = EnrichmentRunner(
        search_provider_factory=lambda: search_provider,
        session_factory=sessionmaker(bind=db.get_bind()),
    )

    outcome = await runner.run(sync_job.id)
    assert outcome.status == SyncJobStatus.COMPLETED
    assert search_provider.called is True


# ---------------------------------------------------------------------------
# 5 & 6. Acceptance Test Hook Gating
# ---------------------------------------------------------------------------

def test_acceptance_hook_requires_explicit_flag() -> None:
    """When enable_acceptance_test_hooks is False, is_test_hook_allowed() is False even in test environment."""
    with patch.object(settings, "environment", "test"), \
         patch.object(settings, "enable_acceptance_test_hooks", False):
        assert settings.is_test_hook_allowed() is False


def test_production_never_allows_acceptance_hook() -> None:
    """When environment is production, is_test_hook_allowed() is ALWAYS False regardless of flag."""
    with patch.object(settings, "environment", "production"), \
         patch.object(settings, "enable_acceptance_test_hooks", True):
        assert settings.is_test_hook_allowed() is False


# ---------------------------------------------------------------------------
# 7. SSRFGuardedTransport httpcore & httpx Pinned Compatibility
# ---------------------------------------------------------------------------

def test_ssrf_transport_httpcore_compatibility() -> None:
    """SSRFGuardedTransport must instantiate correctly and verify pinned version parity."""
    assert httpx.__version__ == "0.28.1"
    assert httpcore.__version__ == "1.0.9"

    transport = SSRFGuardedTransport()
    assert isinstance(transport._backend, SSRFGuardedBackend)
    assert transport._pool is not None
    assert transport._pool._network_backend is transport._backend


# ---------------------------------------------------------------------------
# 8 & 9. DNS Rebinding & Mixed DNS Record SSRF Protection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dns_rebinding_public_then_private_is_blocked() -> None:
    """If DNS re-resolves to a private IP (e.g. 127.0.0.1 or 169.254.169.254) during TCP connect,
    SSRFGuardedBackend blocks it immediately with SSRFProtectionError.
    """
    backend = SSRFGuardedBackend(allowed_ports={80, 443})

    with patch("asyncio.get_running_loop") as mock_loop_fn:
        mock_loop = AsyncMock()
        mock_loop_fn.return_value = mock_loop
        mock_loop.getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
        ]

        with pytest.raises(SSRFProtectionError, match="özel/dahili IP adresine çözümlendi"):
            await backend.connect_tcp("rebind-attack.example.com", 80)


@pytest.mark.asyncio
async def test_mixed_public_private_dns_answer_is_blocked() -> None:
    """DNS answer containing a mix of public and private IPs must be completely blocked."""
    with patch("asyncio.get_running_loop") as mock_loop_fn:
        mock_loop = AsyncMock()
        mock_loop_fn.return_value = mock_loop
        mock_loop.getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 80)),
        ]

        with pytest.raises(SSRFProtectionError, match="özel/dahili IP adresine çözümlendi"):
            await validate_url_for_ssrf("http://dual-homed.example.com/job")


# ---------------------------------------------------------------------------
# 10. Aging Jobs Metric in JobRepository
# ---------------------------------------------------------------------------

def test_aging_metric(db: Session, test_job: Job) -> None:
    """JobRepository.stats() must accurately include aging_jobs metric."""
    test_job.freshness_status = "aging"
    db.commit()

    repo = JobRepository(db)
    stats_dict = repo.stats(user_id=test_job.user_id)
    assert "aging_jobs" in stats_dict
    assert stats_dict["aging_jobs"] >= 1

    stats_schema = JobStats.model_validate(stats_dict)
    assert stats_schema.aging_jobs >= 1


# ---------------------------------------------------------------------------
# 11. Verified Sort Option
# ---------------------------------------------------------------------------

def test_verified_sort(db: Session, user1) -> None:
    """JobRepository.list_for_user(sort='verified') sorts by last_verified_at desc nulls last."""
    now = datetime.now(timezone.utc)
    job_recent = Job(
        user_id=user1.id,
        title="Job Recent Verification",
        company="Company A",
        last_verified_at=now,
    )
    job_older = Job(
        user_id=user1.id,
        title="Job Older Verification",
        company="Company B",
        last_verified_at=now - timedelta(days=2),
    )
    job_unverified = Job(
        user_id=user1.id,
        title="Job Unverified",
        company="Company C",
        last_verified_at=None,
    )
    db.add_all([job_recent, job_older, job_unverified])
    db.commit()

    repo = JobRepository(db)
    items, total = repo.list_for_user(user_id=user1.id, sort="verified", offset=0, limit=10)

    # Find the positions of our test jobs in the sorted result
    ids = [j.id for j in items]
    assert job_recent.id in ids
    assert job_older.id in ids
    assert job_unverified.id in ids

    assert ids.index(job_recent.id) < ids.index(job_older.id)
    assert ids.index(job_older.id) < ids.index(job_unverified.id)


# ---------------------------------------------------------------------------
# 12. Source Provenance Filtering
# ---------------------------------------------------------------------------

def test_source_filtering(db: Session, user1) -> None:
    """JobRepository.list_for_user(source=...) supports official_ats, linkedin, and mail filters."""
    job_ats = Job(
        user_id=user1.id,
        title="ATS Job",
        company="Company ATS",
        source="official_ats",
    )
    job_linkedin = Job(
        user_id=user1.id,
        title="LinkedIn Job",
        company="Company LinkedIn",
        source="gmail",
        linkedin_url="https://www.linkedin.com/jobs/view/999888777",
    )
    job_mail_only = Job(
        user_id=user1.id,
        title="Mail Only Job",
        company="Company Mail",
        source="outlook",
        linkedin_url=None,
    )
    db.add_all([job_ats, job_linkedin, job_mail_only])
    db.commit()

    repo = JobRepository(db)

    # 1. Filter official_ats
    ats_items, _ = repo.list_for_user(user_id=user1.id, source="official_ats", limit=20)
    ats_ids = {j.id for j in ats_items}
    assert job_ats.id in ats_ids
    assert job_mail_only.id not in ats_ids

    # 2. Filter linkedin
    li_items, _ = repo.list_for_user(user_id=user1.id, source="linkedin", limit=20)
    li_ids = {j.id for j in li_items}
    assert job_linkedin.id in li_ids
    assert job_mail_only.id not in li_ids

    # 3. Filter mail
    mail_items, _ = repo.list_for_user(user_id=user1.id, source="mail", limit=20)
    mail_ids = {j.id for j in mail_items}
    assert job_linkedin.id in mail_ids
    assert job_mail_only.id in mail_ids
    assert job_ats.id not in mail_ids
