"""Worker runner for durable enrichment jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.web_fetch.fetcher import SafeWebFetcher
from app.integrations.web_search import get_search_provider
from app.integrations.web_search.base import SearchProvider
from app.models.enums import SyncJobStatus
from app.models.sync_job import EnrichmentItem, SyncJob
from app.repositories.sync_jobs import EnrichmentItemRepository
from app.services.job_enrichment.service import JobEnrichmentService

logger = logging.getLogger("jobhunter.enrichment_runner")


@dataclass(slots=True)
class EnrichmentRunnerOutcome:
    status: SyncJobStatus = SyncJobStatus.COMPLETED
    processed: int = 0
    enriched: int = 0
    failed: int = 0
    skipped: int = 0
    error_message: str | None = None


class EnrichmentRunner:
    """Executes an enrichment SyncJob by processing each EnrichmentItem with bounded concurrency."""

    def __init__(
        self,
        *,
        search_provider_factory: Callable[[], SearchProvider] | None = None,
        fetcher_factory: Callable[[], SafeWebFetcher] | None = None,
        session_factory=SessionLocal,
        max_concurrency: int | None = None,
        now: datetime | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.search_provider_factory = search_provider_factory or get_search_provider
        self.fetcher_factory = fetcher_factory or (lambda: SafeWebFetcher())
        self.session_factory = session_factory
        self.max_concurrency = max(1, max_concurrency or settings.web_fetch_max_concurrency)
        self._origin = now
        self._cancel_check = cancel_check

    @contextmanager
    def _db(self):
        session: Session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _is_cancelled(self) -> bool:
        return bool(self._cancel_check and self._cancel_check())

    async def run(self, job_id: uuid.UUID) -> EnrichmentRunnerOutcome:
        """Run the enrichment stage for the given SyncJob id."""
        force = False
        with self._db() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return EnrichmentRunnerOutcome(
                    status=SyncJobStatus.FAILED,
                    error_message=f"SyncJob bulunamadı: {job_id}",
                )
            if job.cancel_requested:
                return EnrichmentRunnerOutcome(status=SyncJobStatus.CANCELLED)
            force = bool(job.payload.get("force")) if job.payload else False
            # Requeue running items from prior crash
            EnrichmentItemRepository(session).requeue_running(job_id)

        with self._db() as session:
            items = EnrichmentItemRepository(session).list_for_job(job_id)
            item_ids = [item.id for item in items]

        if not item_ids:
            return EnrichmentRunnerOutcome(status=SyncJobStatus.COMPLETED)

        semaphore = asyncio.Semaphore(self.max_concurrency)
        search_provider = self.search_provider_factory()
        fetcher = self.fetcher_factory()

        processed = 0
        enriched = 0
        failed = 0
        skipped = 0

        async def _process_item(item_id: uuid.UUID) -> None:
            nonlocal processed, enriched, failed, skipped
            async with semaphore:
                if self._is_cancelled():
                    with self._db() as session:
                        repo = EnrichmentItemRepository(session)
                        item = repo.get(item_id)
                        if item and item.status in {"queued", "running"}:
                            repo.mark_finished(
                                item,
                                status="skipped",
                                error_message="Kullanıcı işi iptal etti.",
                            )
                    skipped += 1
                    return

                # Step 1: Claim atomically
                target_job_id = None
                with self._db() as session:
                    repo = EnrichmentItemRepository(session)
                    item = repo.get(item_id)
                    if item is None or not repo.claim(item):
                        return
                    target_job_id = item.job_id

                if not target_job_id:
                    return

                # Step 2: Run enrichment outside long DB lock
                outcome_status = "completed"
                enrich_status = "failed"
                err_class = None
                err_msg = None
                canonical = None

                with self._db() as session:
                    service = JobEnrichmentService(
                        session,
                        search_provider=search_provider,
                        fetcher=fetcher,
                    )
                    try:
                        res = await service.enrich_job(target_job_id, force=force)
                        enrich_status = res.enrichment_status
                        canonical = res.canonical_url
                    except Exception as exc:
                        logger.exception("İlan zenginleştirme hatası (job=%s): %s", target_job_id, exc)
                        outcome_status = "failed"
                        err_class = type(exc).__name__
                        err_msg = str(exc)[:300]

                # Step 3: Record item outcome
                with self._db() as session:
                    repo = EnrichmentItemRepository(session)
                    item = repo.get(item_id)
                    if item is not None:
                        repo.mark_finished(
                            item,
                            status=outcome_status,
                            source_url=canonical,
                            error_class=err_class,
                            error_message=err_msg,
                        )
                    # Update sync job progress
                    job = session.get(SyncJob, job_id)
                    if job is not None:
                        current_prog = dict(job.progress or {})
                        current_prog["processed"] = current_prog.get("processed", 0) + 1
                        if enrich_status == "enriched":
                            current_prog["enriched"] = current_prog.get("enriched", 0) + 1
                        elif outcome_status == "failed":
                            current_prog["failed"] = current_prog.get("failed", 0) + 1
                        job.progress = current_prog
                        if outcome_status == "failed":
                            job.errors_count += 1

                processed += 1
                if enrich_status == "enriched":
                    enriched += 1
                elif outcome_status == "failed":
                    failed += 1

        await asyncio.gather(*(_process_item(i_id) for i_id in item_ids))

        final_status = SyncJobStatus.COMPLETED
        if self._is_cancelled():
            final_status = SyncJobStatus.CANCELLED
        elif failed > 0 and enriched == 0 and processed == failed:
            final_status = SyncJobStatus.FAILED
        elif failed > 0:
            final_status = SyncJobStatus.PARTIAL_FAILED

        return EnrichmentRunnerOutcome(
            status=final_status,
            processed=processed,
            enriched=enriched,
            failed=failed,
            skipped=skipped,
        )
