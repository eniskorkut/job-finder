"""Tests for Custom Sites and ATS Crawler service and endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.integrations.web_fetch.fetcher import (
    FetchResult,
    LinkedInFetchForbiddenError,
    SSRFProtectionError,
    WebFetchError,
)
from app.models.job import Job, JobMatch
from app.services.site_crawler_service import SiteCrawlerService

SAMPLE_JSON_LD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Senior Platform Engineer - Acme Corp</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Platform Engineer",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Acme Global Technologies"
        },
        "description": "<p>We are seeking an experienced Senior Platform Engineer to scale our distributed cloud systems. Experience with Kubernetes, Go, and Kafka required.</p>",
        "datePosted": "2026-09-15T10:00:00Z",
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "San Francisco",
                "addressRegion": "CA",
                "addressCountry": "US"
            }
        },
        "jobLocationType": "TELECOMMUTE",
        "directApply": "https://careers.acme.example/jobs/4521/apply"
    }
    </script>
</head>
<body>
    <h1>Senior Platform Engineer</h1>
</body>
</html>
"""

SAMPLE_SEMANTIC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Lead Site Reliability Architect at Nova Cloud</title>
    <meta property="og:title" content="Lead Site Reliability Architect">
    <meta property="og:site_name" content="Nova Cloud">
</head>
<body>
    <article class="job-description">
        <h1>Lead Site Reliability Architect</h1>
        <div class="location">New York, NY (Hybrid)</div>
        <div class="content">
            Responsible for core reliability and multi-region failover. Must have extensive cloud architecture background.
        </div>
    </article>
</body>
</html>
"""

SAMPLE_ATS_BOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Careers at Quantum Labs</title>
</head>
<body>
    <div class="job-board">
        <div class="opening">
            <h3><a href="/jobs/101">Staff Infrastructure Engineer</a></h3>
            <span class="location">London, UK - Remote</span>
        </div>
        <div class="opening">
            <h3><a href="/jobs/102">Senior Data Platform Lead</a></h3>
            <span class="location">Berlin, Germany</span>
        </div>
    </div>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_crawl_site_json_ld_ingestion(db, user1):
    service = SiteCrawlerService(db)

    mock_fetch = AsyncMock(
        return_value=FetchResult(
            url="https://careers.acme.example/jobs/4521",
            final_url="https://careers.acme.example/jobs/4521",
            status_code=200,
            content=SAMPLE_JSON_LD_HTML,
        )
    )

    with patch.object(service.fetcher, "fetch", mock_fetch):
        res = await service.crawl_site(user1, "careers.acme.example/jobs/4521")

    assert res.success is True
    assert res.jobs_found == 1
    assert res.jobs_created == 1
    assert len(res.jobs) == 1
    job_item = res.jobs[0]
    assert job_item.title == "Senior Platform Engineer"
    assert job_item.company == "Acme Global Technologies"
    assert job_item.location == "San Francisco, CA, US"
    assert job_item.is_new is True

    # Verify database persistence
    job_db = db.scalars(select(Job).where(Job.id == job_item.id)).first()
    assert job_db is not None
    assert job_db.user_id == user1.id
    assert job_db.work_mode == "remote"
    assert "Kubernetes" in job_db.description

    match_db = db.scalars(select(JobMatch).where(JobMatch.job_id == job_item.id)).first()
    assert match_db is not None
    assert match_db.status == "new"

    # Second crawl of same URL -> deduplication
    with patch.object(service.fetcher, "fetch", mock_fetch):
        res2 = await service.crawl_site(user1, "https://careers.acme.example/jobs/4521")

    assert res2.success is True
    assert res2.jobs_found == 1
    assert res2.jobs_created == 0
    assert res2.jobs[0].is_new is False


@pytest.mark.asyncio
async def test_crawl_site_semantic_html(db, user1):
    service = SiteCrawlerService(db)

    mock_fetch = AsyncMock(
        return_value=FetchResult(
            url="https://novacloud.example/jobs/sre",
            final_url="https://novacloud.example/jobs/sre",
            status_code=200,
            content=SAMPLE_SEMANTIC_HTML,
        )
    )

    with patch.object(service.fetcher, "fetch", mock_fetch):
        res = await service.crawl_site(user1, "https://novacloud.example/jobs/sre")

    assert res.success is True
    assert res.jobs_found == 1
    assert res.jobs_created == 1
    assert "Lead Site Reliability Architect" in res.jobs[0].title


@pytest.mark.asyncio
async def test_crawl_site_ats_board_multiple_jobs(db, user1):
    service = SiteCrawlerService(db)

    mock_fetch = AsyncMock(
        return_value=FetchResult(
            url="https://quantumlabs.example/careers",
            final_url="https://quantumlabs.example/careers",
            status_code=200,
            content=SAMPLE_ATS_BOARD_HTML,
        )
    )

    with patch.object(service.fetcher, "fetch", mock_fetch):
        res = await service.crawl_site(user1, "https://quantumlabs.example/careers")

    assert res.success is True
    assert res.jobs_found == 2
    assert res.jobs_created == 2
    titles = [j.title for j in res.jobs]
    assert "Staff Infrastructure Engineer" in titles
    assert "Senior Data Platform Lead" in titles


@pytest.mark.asyncio
async def test_crawl_site_ssrf_blocked(db, user1):
    service = SiteCrawlerService(db)

    mock_fetch = AsyncMock(side_effect=SSRFProtectionError("Private IP prohibited"))

    with patch.object(service.fetcher, "fetch", mock_fetch):
        res = await service.crawl_site(user1, "http://127.0.0.1:8000/internal-jobs")

    assert res.success is False
    assert res.jobs_created == 0
    assert "Güvenlik nedeniyle" in res.message


@pytest.mark.asyncio
async def test_verify_sites_batch(db):
    service = SiteCrawlerService(db)

    async def fake_fetch(url):
        if "failing" in url:
            raise WebFetchError("DNS resolution failed")
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content=SAMPLE_JSON_LD_HTML,
        )

    with patch.object(service.fetcher, "fetch", side_effect=fake_fetch):
        res = await service.verify_sites(["goodsite.example/jobs", "failing.example/jobs"])

    assert res.success is True
    assert res.total_checked == 2
    assert res.active_sites == 1
    assert res.results[0].status == "ok"
    assert res.results[1].status == "error"


def test_custom_sites_api_endpoints(api_user1):
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            url="https://acme.example/jobs",
            final_url="https://acme.example/jobs",
            status_code=200,
            content=SAMPLE_JSON_LD_HTML,
        )
    )

    with patch("app.services.site_crawler_service.SafeWebFetcher.fetch", mock_fetch):
        # 1. Crawl single custom site endpoint (202 durable job)
        crawl_resp = api_user1.post(
            "/api/v1/integrations/custom-sites/crawl",
            json={"url": "https://acme.example/jobs"},
        )
        assert crawl_resp.status_code == 202
        data = crawl_resp.json()
        assert data["status"] == "queued"
        assert "job_id" in data
        assert data["url"] == "https://acme.example/jobs"

        # 2. Verify sites endpoint
        verify_resp = api_user1.post(
            "/api/v1/integrations/custom-sites/verify",
            json={"sites": ["https://acme.example/jobs"]},
        )
        assert verify_resp.status_code == 200
        vdata = verify_resp.json()
        assert vdata["success"] is True
        assert vdata["active_sites"] == 1


@pytest.mark.asyncio
async def test_site_crawl_worker_execution(db, user1):
    from app.services.sync_job_service import SyncJobService, SyncRunner
    from app.models.sync_job import SyncJob
    from app.models.enums import SyncJobStatus

    mock_fetch = AsyncMock(
        return_value=FetchResult(
            url="https://acme.example/careers",
            final_url="https://acme.example/careers",
            status_code=200,
            content=SAMPLE_JSON_LD_HTML,
        )
    )

    job_service = SyncJobService(db)
    job = job_service.enqueue_site_crawl(user1, "https://acme.example/careers")
    db.commit()
    job_id = job.id

    with patch("app.services.site_crawler_service.SafeWebFetcher.fetch", mock_fetch):
        runner = SyncRunner(worker_id="crawler-test")
        status = await runner.execute(job_id)

    assert status == SyncJobStatus.COMPLETED

    db.expire_all()
    refreshed_job = db.get(SyncJob, job_id)
    assert refreshed_job.status == SyncJobStatus.COMPLETED.value
    assert refreshed_job.jobs_found == 1
    assert refreshed_job.jobs_new == 1
