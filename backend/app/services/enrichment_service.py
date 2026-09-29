"""Job enrichment service (API and queue side)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.models.enums import SyncJobStatus, SyncTrigger
from app.models.job import Job
from app.models.sync_job import SyncJob
from app.models.user import User
from app.repositories.jobs import JobRepository
from app.repositories.sync_jobs import EnrichmentItemRepository, SyncJobRepository

logger = logging.getLogger("jobhunter.enrichment_service")

ENRICHMENT_KIND = "enrichment"


class EnrichmentService:
    """Manages creation and querying of enrichment SyncJobs."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = JobRepository(db)
        self.job_queue = SyncJobRepository(db)
        self.items = EnrichmentItemRepository(db)

    def eligible_jobs(
        self,
        user: User,
        *,
        job_id: uuid.UUID | None = None,
        force: bool = False,
        limit: int = 200,
    ) -> list[Job]:
        """Find jobs that require enrichment."""
        stmt = select(Job).where(Job.user_id == user.id)

        if job_id is not None:
            stmt = stmt.where(Job.id == job_id)
        else:
            stmt = stmt.where(Job.is_mock.is_(False))
            if not force:
                stmt = stmt.where(
                    (Job.enrichment_status == "pending")
                    | (Job.description_status == "insufficient_description")
                )

        stmt = stmt.order_by(Job.discovered_at.desc()).limit(max(1, limit))
        return list(self.db.execute(stmt).scalars())

    def enqueue(
        self,
        user: User,
        *,
        job_id: uuid.UUID | None = None,
        force: bool = False,
        trigger: SyncTrigger = SyncTrigger.MANUAL,
    ) -> tuple[SyncJob, int]:
        """Queue a durable enrichment job."""
        active = self.job_queue.active_for_user(user.id)
        if active is not None:
            raise errors.conflict(
                f"Bu kullanıcı için zaten çalışan bir iş var ({active.kind}: {active.id})."
            )

        candidates = self.eligible_jobs(user, job_id=job_id, force=force)
        if not candidates:
            raise errors.conflict("Zenginleştirme gerektiren uygun ilan bulunamadı.")

        job = SyncJob(
            user_id=user.id,
            kind=ENRICHMENT_KIND,
            status=SyncJobStatus.QUEUED.value,
            trigger=trigger.value,
            payload={
                "force": force,
                "job_id": str(job_id) if job_id else None,
            },
            progress={"total": len(candidates), "processed": 0, "enriched": 0, "failed": 0},
            accounts_total=len(candidates),
        )
        self.db.add(job)
        self.db.flush()

        self.items.create_items(job, [c.id for c in candidates])
        return job, len(candidates)

    def enqueue_for_new_jobs(self, user_id: uuid.UUID) -> SyncJob | None:
        """Called by pipeline after mail scan: queue enrichment if jobs need it."""
        user = self.db.get(User, user_id)
        if user is None:
            return None

        candidates = self.eligible_jobs(user, force=False)
        if not candidates:
            return None

        try:
            job, _ = self.enqueue(user, force=False, trigger=SyncTrigger.SCHEDULED)
            return job
        except errors.AppError as exc:
            logger.info("Otomatik zenginleştirme kuyruğa alınamadı: %s", exc)
            return None
