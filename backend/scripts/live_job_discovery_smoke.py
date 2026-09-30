"""Live Job Discovery & Real-World Acceptance Test on Real Internet.

Performs strict, end-to-end web discovery via SearXNG, safe ATS fetching,
JSON-LD/HTML parsing, title/company matching, and freshness validation with:
- ZERO mock data
- ZERO fake responses
- ZERO hardcoded URLs
- ZERO LinkedIn scraping
- Strict PASS / FAIL / PARTIAL / BLOCKED evaluation
- Isolated temporary SQLite databases per target with complete engine disposal
- Resource lifecycle cleanup (HTTP clients, DB sessions, DB engines, temp files)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.base import Base
from app.integrations.web_fetch.fetcher import (
    FetchResult,
    LinkedInFetchForbiddenError,
    SafeWebFetcher,
    WebFetchError,
)
from app.integrations.web_search.base import SearchResult, SearchUnavailableError
from app.integrations.web_search.searxng import SearXNGSearchProvider
from app.models.enums import DescriptionStatus, EnrichmentStatus, UserRole
from app.models.job import Job, JobWebSource
from app.models.user import User
from app.services.job_enrichment.service import JobEnrichmentService
from app.services.job_enrichment.trust import (
    classify_source,
    compute_string_similarity,
    extract_ats_tenant,
)
from app.services.job_enrichment.url_utils import is_linkedin_url


@dataclass(slots=True)
class TargetMetrics:
    company: str
    title: str
    verdict: str = "BLOCKED"  # PASS, FAIL, PARTIAL, BLOCKED
    failure_reasons: list[str] = field(default_factory=list)
    search_query_count: int = 0
    search_result_count: int = 0
    unique_result_count: int = 0
    web_fetch_count: int = 0
    successful_fetch_count: int = 0
    failed_fetch_count: int = 0
    retry_count: int = 0
    linkedin_fetch_count: int = 0
    elapsed_ms: int = 0
    selected_source_url: str | None = None
    selected_source_type: str = "unknown"
    source_confidence: str = "none"
    description_length: int = 0
    parser_source: str = "none"
    http_status: int | None = None
    enrichment_status: str = "pending"
    freshness_status: str = "unknown"
    posted_at: str | None = None
    found_semantic_signals: list[str] = field(default_factory=list)
    fetched_urls: list[str] = field(default_factory=list)


class InstrumentedTestFetcher(SafeWebFetcher):
    """Subclass tracking exact fetch counts, status codes, and strictly prohibiting LinkedIn fetches."""

    def __init__(self, metrics: TargetMetrics, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.metrics = metrics

    async def fetch(self, url: str, **kwargs: Any) -> FetchResult:
        if is_linkedin_url(url):
            self.metrics.linkedin_fetch_count += 1
            raise AssertionError(f"VIOLATION: Attempted to fetch LinkedIn URL: {url}")

        self.metrics.web_fetch_count += 1
        self.metrics.fetched_urls.append(url)
        try:
            res = await super().fetch(url, **kwargs)
            if res.status_code in {200, 304}:
                self.metrics.successful_fetch_count += 1
            else:
                self.metrics.failed_fetch_count += 1
            return res
        except WebFetchError:
            self.metrics.failed_fetch_count += 1
            raise


class InstrumentedTestSearchProvider:
    """Delegating wrapper around SearXNGSearchProvider tracking queries and result counts."""

    def __init__(self, provider: SearXNGSearchProvider, metrics: TargetMetrics) -> None:
        self._provider = provider
        self.metrics = metrics
        self._seen_urls: set[str] = set()

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.metrics.search_query_count += 1
        results = await self._provider.search(query, limit=limit)
        self.metrics.search_result_count += len(results)
        for r in results:
            if r.url not in self._seen_urls:
                self._seen_urls.add(r.url)
                self.metrics.unique_result_count += 1
        return results

    async def close(self) -> None:
        await self._provider.close()


async def evaluate_single_target(
    company: str,
    title: str,
    searxng_url: str = "http://localhost:8080",
) -> TargetMetrics:
    """Run real-world discovery and enrichment for a single company/title target on an isolated temporary DB."""
    metrics = TargetMetrics(company=company, title=title)
    start_time = time.monotonic()

    # 1. Create unique isolated temporary directory and SQLite database
    temp_dir = tempfile.mkdtemp(prefix=f"jobhunter_live_{company.lower().replace(' ', '_')}_")
    db_file = Path(temp_dir) / "test.db"

    engine = None
    raw_searxng = None

    try:
        engine = create_engine(
            f"sqlite:///{db_file}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        # Seed isolated test user and initial raw job (simulating short email alert)
        with session_factory() as db:
            user = User(
                username=f"tester_{uuid.uuid4().hex[:8]}",
                email=f"tester_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="test_secret_hash",
                role=UserRole.OWNER,
                full_name="Acceptance Tester",
            )
            db.add(user)
            db.flush()

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

        # 2. Configure Real SearXNG Search Provider & Instrumented Fetcher
        raw_searxng = SearXNGSearchProvider(base_url=searxng_url)
        search_provider = InstrumentedTestSearchProvider(raw_searxng, metrics)
        fetcher = InstrumentedTestFetcher(metrics)

        # 3. Execute enrichment
        try:
            service = JobEnrichmentService(
                session_factory=session_factory,
                search_provider=search_provider,
                fetcher=fetcher,
            )
            outcome = await service.enrich_job(job_id, force=True)
            metrics.enrichment_status = outcome.enrichment_status
        except SearchUnavailableError as exc:
            metrics.verdict = "BLOCKED"
            metrics.failure_reasons.append(f"SearXNG unavailable: {exc}")
            return metrics
        except Exception as exc:
            metrics.verdict = "FAIL"
            metrics.failure_reasons.append(f"Enrichment service error: {exc}")
            return metrics

        # 4. Read persisted state from DB
        with session_factory() as db:
            enriched_job = db.get(Job, job_id)
            web_sources = db.query(JobWebSource).filter(JobWebSource.job_id == job_id).all()

        metrics.elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # 5. Extract verification fields
        if enriched_job:
            metrics.description_length = len(enriched_job.description or "")
            metrics.selected_source_url = enriched_job.canonical_url or (web_sources[0].url if web_sources else None)
            metrics.freshness_status = enriched_job.freshness_status or "unknown"
            metrics.posted_at = enriched_job.posted_at.isoformat() if enriched_job.posted_at else None

        if web_sources:
            selected = next((s for s in web_sources if s.selected_as_canonical), web_sources[0])
            metrics.selected_source_type = selected.source_type
            metrics.source_confidence = selected.match_confidence
            metrics.http_status = selected.http_status
            if selected.source_type == "json_ld":
                metrics.parser_source = "json_ld"
            elif selected.source_type in {"ats", "official"}:
                metrics.parser_source = "semantic_html"
            else:
                metrics.parser_source = selected.source_type

        # Semantic signal checking
        semantic_keywords = ["ai", "engineer", "software", "python", "machine learning", "data", "model", "llm", "developer", "cloud", "aws"]
        desc_lower = (enriched_job.description or "").lower() if enriched_job else ""
        metrics.found_semantic_signals = [k for k in semantic_keywords if k in desc_lower]

        # 6. Apply Strict PASS / FAIL Criteria
        reasons: list[str] = []

        if metrics.search_result_count == 0:
            reasons.append("No search results found by SearXNG.")

        if metrics.web_fetch_count == 0:
            reasons.append("No candidate URLs were fetched.")

        if metrics.linkedin_fetch_count > 0:
            reasons.append(f"Prohibited LinkedIn fetch attempted ({metrics.linkedin_fetch_count} times)!")

        if not metrics.selected_source_url:
            reasons.append("No canonical URL was selected.")

        if metrics.source_confidence not in {"high", "medium"}:
            reasons.append(f"Source confidence is insufficient ({metrics.source_confidence}). Expected high or medium.")

        if metrics.description_length < 300:
            reasons.append(f"Extracted description is too short ({metrics.description_length} chars < 300).")

        if metrics.enrichment_status != "enriched":
            reasons.append(f"Enrichment status is '{metrics.enrichment_status}'. Expected 'enriched'.")

        if len(metrics.found_semantic_signals) < 2:
            reasons.append(f"Insufficient semantic signals in description: {metrics.found_semantic_signals}")

        # Check tenant / company match
        if metrics.selected_source_url:
            tenant = extract_ats_tenant(metrics.selected_source_url)
            tenant_sim = compute_string_similarity(company, tenant) if tenant else 0.0
            source_type, trust, _ = classify_source(metrics.selected_source_url, company)
            if trust < 85 and tenant_sim < 0.5:
                reasons.append(f"Source URL '{metrics.selected_source_url}' is not a trusted ATS or company official domain.")

        metrics.failure_reasons = reasons

        if not reasons:
            metrics.verdict = "PASS"
        elif metrics.enrichment_status == "enriched" or metrics.description_length >= 300:
            metrics.verdict = "PARTIAL"
        else:
            metrics.verdict = "FAIL"

    finally:
        # Proper resource lifecycle cleanup
        if raw_searxng:
            try:
                await raw_searxng.close()
            except Exception:
                pass

        if engine:
            try:
                engine.dispose()
            except Exception:
                pass

        # Clean temporary DB directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    return metrics


async def run_acceptance_suite(searxng_url: str = "http://localhost:8080") -> list[TargetMetrics]:
    """Execute live acceptance tests on 3 distinct real companies."""
    targets = [
        ("Impiricus", "AI Engineer"),
        ("Cadence Solutions", "AI Engineer"),
        ("Synthesia", "Backend Engineer"),
    ]

    results: list[TargetMetrics] = []
    print("\n" + "=" * 70)
    print("STARTING REAL-WORLD ACCEPTANCE TESTS ON REAL INTERNET")
    print(f"SearXNG URL: {searxng_url}")
    print(f"Targets ({len(targets)}): {', '.join(f'{c} ({t})' for c, t in targets)}")
    print("=" * 70 + "\n")

    for idx, (company, title) in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] Evaluating: {company} - {title}...")
        metric = await evaluate_single_target(company, title, searxng_url=searxng_url)
        results.append(metric)
        status_color = "\033[92m" if metric.verdict == "PASS" else "\033[91m"
        reset_color = "\033[0m"
        print(f"   -> Result: {status_color}{metric.verdict}{reset_color} ({metric.elapsed_ms}ms)")
        if metric.selected_source_url:
            print(f"      Canonical URL: {metric.selected_source_url}")
        print(f"      Description:   {metric.description_length} chars, Signals: {metric.found_semantic_signals}")
        if metric.failure_reasons:
            print(f"      Reasons:       {'; '.join(metric.failure_reasons)}")
        print()
        if idx < len(targets):
            await asyncio.sleep(2)

    return results


def print_summary_table(results: list[TargetMetrics]) -> None:
    print("\n" + "=" * 90)
    print("REAL WORLD ACCEPTANCE TEST SUMMARY REPORT")
    print("=" * 90)
    header = f"{'Company':<20} | {'Title':<20} | {'Verdict':<8} | {'Conf':<6} | {'Desc Len':<9} | {'Latency':<8} | {'Canonical URL':<30}"
    print(header)
    print("-" * 90)
    for r in results:
        url_snippet = (r.selected_source_url or "None")[:28]
        if r.selected_source_url and len(r.selected_source_url) > 28:
            url_snippet += ".."
        line = f"{r.company:<20} | {r.title:<20} | {r.verdict:<8} | {r.source_confidence:<6} | {r.description_length:<9} | {r.elapsed_ms:<6}ms | {url_snippet:<30}"
        print(line)
    print("=" * 90)

    pass_count = sum(1 for r in results if r.verdict == "PASS")
    print(f"\nFinal Result: {pass_count}/{len(results)} targets PASSED.")
    if pass_count >= 2:
        print("\033[92m[ACCEPTANCE TARGET MET: At least 2 real companies successfully discovered and enriched]\033[0m\n")
    else:
        print("\033[91m[ACCEPTANCE TARGET FAILED: Fewer than 2 targets passed]\033[0m\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-World Live Job Discovery Acceptance Test")
    parser.add_argument("--company", help="Single target company")
    parser.add_argument("--title", help="Single target title")
    parser.add_argument("--all-targets", action="store_true", help="Run acceptance test across 3 real companies")
    parser.add_argument("--searxng-url", default="http://localhost:8080", help="SearXNG URL")
    args = parser.parse_args()

    if args.all_targets or (not args.company and not args.title):
        results = asyncio.run(run_acceptance_suite(searxng_url=args.searxng_url))
        print_summary_table(results)
        pass_count = sum(1 for r in results if r.verdict == "PASS")
        if pass_count < 2:
            sys.exit(1)
    else:
        company = args.company or "Impiricus"
        title = args.title or "AI Engineer"
        print(f"\nRunning single live target: {company} - {title}...")
        metric = asyncio.run(evaluate_single_target(company, title, searxng_url=args.searxng_url))
        print("\n--- TARGET METRICS ---")
        for f_name in TargetMetrics.__slots__:
            print(f"  {f_name:25s}: {getattr(metric, f_name)}")
        if metric.verdict != "PASS":
            print(f"\n[FAIL] Target did not pass: {metric.failure_reasons}")
            sys.exit(1)
        else:
            print("\n[OK] Target PASSED all strict criteria.")


if __name__ == "__main__":
    main()
