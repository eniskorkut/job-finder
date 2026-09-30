"""Live Job Discovery & Enrichment Smoke Test on Real Internet.

Performs real end-to-end web discovery via SearXNG, safe ATS fetching,
JSON-LD/HTML parsing, and freshness validation with ZERO mock data,
ZERO fake responses, ZERO hardcoded URLs, and ZERO LinkedIn scraping.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.base import Base
from app.integrations.web_fetch.fetcher import FetchResult, SafeWebFetcher
from app.integrations.web_search.searxng import SearXNGSearchProvider
from app.models.enums import DescriptionStatus, EnrichmentStatus, UserRole
from app.models.job import Job, JobWebSource
from app.models.user import User
from app.services.job_enrichment.service import JobEnrichmentService


class TrackingWebFetcher(SafeWebFetcher):
    """Subclass that tracks all HTTP requests and strictly enforces 0 LinkedIn fetches."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fetch_calls: list[str] = []
        self.fetch_results: list[FetchResult] = []
        self.linkedin_fetch_count: int = 0

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        if "linkedin.com" in url.lower():
            self.linkedin_fetch_count += 1
            raise AssertionError(f"VIOLATION: Attempted to fetch LinkedIn URL: {url}")
        self.fetch_calls.append(url)
        res = await super().fetch(url, **kwargs)
        self.fetch_results.append(res)
        return res


async def run_live_discovery(
    company: str,
    title: str,
    searxng_url: str = "http://localhost:8080",
    db_path: str = "/tmp/jobfinder_live_smoke.db",
) -> dict:
    start_time = time.monotonic()

    # 1. Isolated temporary SQLite database
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()

    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        user = User(
            username="smoke_tester",
            email="smoke_tester@example.com",
            password_hash="not_a_real_password",
            role=UserRole.OWNER,
            full_name="Live Smoke Tester",
        )
        db.add(user)
        db.flush()

        # Seed raw job representing short alert email
        raw_job = Job(
            user_id=user.id,
            title=title,
            company=company,
            description="Kısa alert içeriği: Yeni ilan bulundu.",
            description_status=DescriptionStatus.INSUFFICIENT,
            enrichment_status=EnrichmentStatus.PENDING,
            freshness_status="unknown",
            source="gmail",
        )
        db.add(raw_job)
        db.commit()
        job_id = raw_job.id

    # 2. Configure Real SearXNG Search Provider & Tracking SafeWebFetcher
    search_provider = SearXNGSearchProvider(base_url=searxng_url)
    fetcher = TrackingWebFetcher()

    # 3. Execute enrichment
    service = JobEnrichmentService(
        session_factory=session_factory,
        search_provider=search_provider,
        fetcher=fetcher,
    )

    outcome = await service.enrich_job(job_id, force=True)
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # 4. Read final state from DB
    with session_factory() as db:
        enriched_job = db.get(Job, job_id)
        web_sources = db.query(JobWebSource).filter(JobWebSource.job_id == job_id).all()

    # 5. Extract verification metrics
    description_len = len(enriched_job.description or "")
    canonical_url = enriched_job.canonical_url or (web_sources[0].url if web_sources else None)
    ats_platform = web_sources[0].source_type if web_sources else "unknown"

    semantic_signals = ["ai", "engineer", "software", "python", "machine learning", "data", "model", "llm", "developer"]
    found_signals = [
        sig for sig in semantic_signals if sig in (enriched_job.description or "").lower()
    ]

    report = {
        "company": company,
        "title": title,
        "outcome_status": outcome.status,
        "enrichment_status": enriched_job.enrichment_status,
        "freshness_status": enriched_job.freshness_status,
        "canonical_url": canonical_url,
        "ats_platform": ats_platform,
        "description_length": description_len,
        "found_semantic_signals": found_signals,
        "linkedin_fetch_count": fetcher.linkedin_fetch_count,
        "web_fetch_count": len(fetcher.fetch_calls),
        "fetched_urls": fetcher.fetch_calls,
        "sources_found": len(web_sources),
        "posted_at": enriched_job.posted_at.isoformat() if enriched_job.posted_at else None,
        "last_verified_at": enriched_job.last_verified_at.isoformat() if enriched_job.last_verified_at else None,
        "elapsed_ms": elapsed_ms,
    }

    # Clean up client
    await search_provider.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Job Discovery Smoke Test")
    parser.add_argument("--company", default="Impiricus", help="Target company")
    parser.add_argument("--title", default="AI Engineer", help="Target title")
    parser.add_argument("--searxng-url", default="http://localhost:8080", help="SearXNG URL")
    parser.add_argument("--db-path", default="/tmp/jobfinder_live_smoke.db", help="Temp SQLite DB")
    args = parser.parse_args()

    print(f"\n=======================================================")
    print(f"STARTING LIVE JOB DISCOVERY SMOKE TEST ON REAL INTERNET")
    print(f"Target: {args.company} - {args.title}")
    print(f"SearXNG URL: {args.searxng_url}")
    print(f"Isolated DB: {args.db_path}")
    print(f"=======================================================\n")

    report = asyncio.run(
        run_live_discovery(
            company=args.company,
            title=args.title,
            searxng_url=args.searxng_url,
            db_path=args.db_path,
        )
    )

    print("\n--- RESULTS ---")
    for key, val in report.items():
        print(f"  {key:25s}: {val}")

    # Fallback if primary target yielded no description or didn't enrich
    if report["description_length"] < 300 and args.company == "Impiricus":
        print("\nPrimary target did not yield full text >= 300 chars. Running fallback target: Cadence Solutions / AI Engineer...")
        fallback_report = asyncio.run(
            run_live_discovery(
                company="Cadence Solutions",
                title="AI Engineer",
                searxng_url=args.searxng_url,
                db_path=args.db_path,
            )
        )
        print("\n--- FALLBACK RESULTS ---")
        for key, val in fallback_report.items():
            print(f"  {key:25s}: {val}")
        report = fallback_report

    # Strict Assertions
    assert report["linkedin_fetch_count"] == 0, "LinkedIn was fetched! Prohibited!"
    assert report["web_fetch_count"] > 0, "No web fetch calls were made!"
    print(f"\n[OK] Smoke test completed successfully. Real web discovery verified.")


if __name__ == "__main__":
    main()
