"""Scoring queue (API side).

Long analysis never happens inside a request: the API enqueues a durable
``scoring`` job into the same queue the mail scans use, and the worker runs it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.models.enums import MatchStatus, SyncJobStatus, SyncTrigger
from app.models.job import Job, JobMatch
from app.models.sync_job import SyncJob
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.jobs import JobRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.sync_jobs import ScoringItemRepository, SyncJobRepository

SCORING_KIND = "scoring"
ANALYSIS_PENDING = "pending"
ANALYSIS_RUNNING = "running"
ANALYSIS_COMPLETED = "completed"
ANALYSIS_FAILED = "failed"
ANALYSIS_SKIPPED = "skipped"

MODE_NEW = "new"
MODE_REANALYZE = "reanalyze"


class ScoringService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = JobRepository(db)
        self.job_queue = SyncJobRepository(db)
        self.cvs = CVRepository(db)
        self.preferences = PreferenceRepository(db)

    # --- eligibility ----------------------------------------------------
    def active_cv_checksum(self, user: User) -> str | None:
        cv = self.cvs.get_active_for_user(user.id)
        return cv.checksum if cv else None

    def eligible_jobs(
        self,
        user: User,
        *,
        mode: str = MODE_NEW,
        days: int | None = None,
        job_id: uuid.UUID | None = None,
        force: bool = False,
        limit: int = 500,
    ) -> list[Job]:
        """Real (non mock) jobs that still need a CV analysis.

        A job is skipped when a completed analysis already used the current CV
        checksum, so pressing "reanalyze" with an unchanged CV does no work.
        """
        checksum = self.active_cv_checksum(user)
        stmt = (
            select(Job)
            .outerjoin(JobMatch, JobMatch.job_id == Job.id)
            .where(Job.user_id == user.id, Job.is_mock.is_(False))
        )
        if job_id is not None:
            stmt = stmt.where(Job.id == job_id)
        if days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
            stmt = stmt.where(Job.discovered_at >= cutoff)

        if mode == MODE_NEW:
            if job_id is None and not force:
                max_age_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.job_max_age_days)
                stmt = stmt.where(
                    (Job.freshness_status != "expired"),
                    (Job.availability_status != "closed"),
                    or_(
                        Job.posted_at.is_(None),
                        Job.posted_at >= max_age_cutoff,
                    ),
                )
            stmt = stmt.where(
                or_(
                    JobMatch.id.is_(None),
                    JobMatch.analysis_status.is_(None),
                    JobMatch.analysis_status == ANALYSIS_PENDING,
                    (
                        (JobMatch.analysis_status == ANALYSIS_FAILED)
                        & (JobMatch.analysis_attempts < settings.llm_max_analysis_attempts)
                    ),
                )
            )
        elif not force:
            stmt = stmt.where(
                or_(
                    JobMatch.id.is_(None),
                    JobMatch.analysis_status.is_(None),
                    JobMatch.analysis_status.in_([ANALYSIS_PENDING, ANALYSIS_FAILED]),
                    JobMatch.cv_checksum.is_(None),
                    JobMatch.cv_checksum != (checksum or ""),
                )
            )

        stmt = stmt.order_by(Job.discovered_at.desc()).limit(max(1, limit))
        return list(self.db.execute(stmt).scalars())

    def get_job_or_404(self, user: User, job_id: uuid.UUID):
        job = self.jobs.get_for_user(user.id, job_id)
        if job is None:
            raise errors.not_found("İlan bulunamadı.")
        return job

    # --- enqueue --------------------------------------------------------
    def enqueue(
        self,
        user: User,
        *,
        mode: str = MODE_NEW,
        days: int | None = None,
        job_id: uuid.UUID | None = None,
        force: bool = False,
        trigger: SyncTrigger = SyncTrigger.MANUAL,
    ) -> tuple[SyncJob, int]:
        active = self.job_queue.active_for_user(user.id, kinds=(SCORING_KIND,))
        if active is not None:
            raise errors.conflict(
                "Bu kullanıcı için zaten çalışan bir analiz var; bitmesini bekleyin "
                f"(iş: {active.id})."
            )

        cv = self.cvs.get_active_for_user(user.id)
        if cv is None or not cv.extracted_text:
            raise errors.validation_error(
                "Analiz için metni çıkarılmış bir aktif CV gerekiyor. "
                "CV ve Tercihler ekranından PDF/DOCX yükleyin."
            )

        targets = self.eligible_jobs(
            user, mode=mode, days=days, job_id=job_id, force=force
        )
        if not targets:
            raise errors.conflict(
                "Bu CV ile değerlendirilmemiş ilan yok. Yeni ilanlar geldiğinde "
                "otomatik olarak analiz edilir."
            )

        job = self.job_queue.create(
            user_id=user.id,
            kind=SCORING_KIND,
            trigger=trigger.value,
            payload={
                "mode": mode,
                "days": days,
                "job_ids": [str(target.id) for target in targets],
                "cv_checksum": cv.checksum,
                "cv_id": str(cv.id),
            },
            progress={"analyzed": 0, "failed": 0, "skipped": 0, "total": len(targets)},
        )
        # One claimable row per posting: the worker's idempotency boundary.
        ScoringItemRepository(self.db).create_items(
            job, [(target.id, cv.checksum) for target in targets]
        )
        self.db.flush()
        return job, len(targets)

    def enqueue_for_new_jobs(self, user_id: uuid.UUID) -> SyncJob | None:
        """Called by the pipeline after an ingest; quiet when nothing is new."""
        from app.repositories.users import UserRepository

        user = UserRepository(self.db).get_by_id(user_id)
        if user is None:
            return None
        if self.job_queue.active_for_user(user_id, kinds=(SCORING_KIND,)) is not None:
            return None
        try:
            job, _count = self.enqueue(user, mode=MODE_NEW, trigger=SyncTrigger.MANUAL)
        except errors.AppError:
            return None
        return job

    # --- reporting ------------------------------------------------------
    def queue_depth(self, user: User) -> dict:
        rows = self.db.execute(
            select(JobMatch.analysis_status, func.count(JobMatch.id))
            .join(Job, Job.id == JobMatch.job_id)
            .where(Job.user_id == user.id, Job.is_mock.is_(False))
            .group_by(JobMatch.analysis_status)
        ).all()
        counts = {status or ANALYSIS_PENDING: int(count) for status, count in rows}
        real_jobs = int(
            self.db.execute(
                select(func.count(Job.id)).where(
                    Job.user_id == user.id, Job.is_mock.is_(False)
                )
            ).scalar_one()
        )
        analyzed = counts.get(ANALYSIS_COMPLETED, 0)
        return {
            "real_jobs": real_jobs,
            "analyzed": analyzed,
            "pending": counts.get(ANALYSIS_PENDING, 0) + max(0, real_jobs - sum(counts.values())),
            "running": counts.get(ANALYSIS_RUNNING, 0),
            "failed": counts.get(ANALYSIS_FAILED, 0),
            "skipped": counts.get(ANALYSIS_SKIPPED, 0),
            "active_job_id": (
                job.id if (job := self.job_queue.active_for_user(user.id, kinds=(SCORING_KIND,))) else None
            ),
        }

    def pending_analysis_count(self, user: User) -> int:
        return self.queue_depth(user)["pending"]

    def latest_job(self, user: User) -> SyncJob | None:
        jobs = self.job_queue.list_for_user_by_kind(user.id, SCORING_KIND, limit=1)
        return jobs[0] if jobs else None

    def mark_status(
        self, match: JobMatch, *, status: str, error: str | None = None
    ) -> None:
        match.analysis_status = status
        match.analysis_error = (error or None) and error[:500]
        match.analysis_attempts = (match.analysis_attempts or 0) + 1
        if status == ANALYSIS_COMPLETED:
            match.analyzed_at = datetime.now(timezone.utc)
        self.db.flush()


def match_is_high(match: JobMatch, threshold: int) -> bool:
    return match.score is not None and match.score >= threshold


__all__ = [
    "ANALYSIS_COMPLETED",
    "ANALYSIS_FAILED",
    "ANALYSIS_PENDING",
    "ANALYSIS_RUNNING",
    "ANALYSIS_SKIPPED",
    "MODE_NEW",
    "MODE_REANALYZE",
    "MatchStatus",
    "SCORING_KIND",
    "ScoringService",
    "SyncJobStatus",
]
