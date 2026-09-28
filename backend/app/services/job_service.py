from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.models.enums import MatchStatus
from app.models.job import Job
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.integrations import SyncHistoryRepository
from app.repositories.jobs import JobRepository, MailAccountRepository
from app.repositories.preferences import PreferenceRepository
from app.schemas.job import (
    JobDetail,
    JobFilterOptions,
    JobRead,
    JobSourceRead,
    JobStats,
)
from app.schemas.sync import SyncStatusResponse


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = JobRepository(db)
        self.accounts = MailAccountRepository(db)
        self.preferences = PreferenceRepository(db)
        self.cvs = CVRepository(db)
        self.sync_history = SyncHistoryRepository(db)

    def list(
        self,
        user: User,
        *,
        search: str | None = None,
        company: str | None = None,
        location: str | None = None,
        work_mode: str | None = None,
        source: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        analysis_status: str | None = None,
        notification: str | None = None,
        sort: str = "recent",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[JobRead], int]:
        jobs, total = self.jobs.list_for_user(
            user.id,
            search=search,
            company=company,
            location=location,
            work_mode=work_mode,
            source=source,
            status=status,
            min_score=min_score,
            max_score=max_score,
            analysis_status=analysis_status,
            notification=notification,
            sort=sort,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [JobRead.model_validate(job) for job in jobs], total

    def get(self, user: User, job_id: uuid.UUID) -> Job:
        job = self.jobs.get_for_user(user.id, job_id)
        if job is None:
            raise errors.not_found("İlan bulunamadı.")
        return job

    def get_detail(self, user: User, job_id: uuid.UUID) -> JobDetail:
        job = self.get(user, job_id)
        account_email = None
        if job.mail_account_id is not None:
            account = self.accounts.get_for_user(user.id, job.mail_account_id)
            account_email = account.email_address if account else None
        detail = JobDetail.model_validate(job)
        detail.mail_account_email = account_email

        # Every mailbox/message that delivered this posting (one job can arrive
        # through several alerts), scoped to the owner.
        from app.repositories.sync_jobs import JobSourceRepository

        accounts = {
            account.id: account.email_address
            for account in self.accounts.list_for_user(user.id)
        }
        sources = []
        for source in JobSourceRepository(self.db).list_for_job(job.id):
            item = JobSourceRead.model_validate(source)
            item.account_email = accounts.get(source.mail_account_id)
            sources.append(item)
        detail.sources = sources

        if detail.match is not None and detail.match.analyzed_at:
            cv = (
                self.cvs.get_for_user(user.id, job_match_cv_id)
                if (job_match_cv_id := self._match_cv_id(user, job.id))
                else None
            )
            detail.analysis_cv = {
                "checksum": detail.match.cv_checksum,
                "filename": cv.filename if cv else None,
                "model": detail.match.model,
                "prompt_version": detail.match.prompt_version,
                "analyzed_at": detail.match.analyzed_at,
            }
        return detail

    def _match_cv_id(self, user: User, job_id: uuid.UUID) -> uuid.UUID | None:
        from app.models.job import JobMatch

        match = self.db.execute(
            select(JobMatch.cv_id).where(
                JobMatch.user_id == user.id, JobMatch.job_id == job_id
            )
        ).scalar_one_or_none()
        return match

    def mark_viewed(self, user: User, job_id: uuid.UUID) -> None:
        job = self.get(user, job_id)
        match = self.jobs.get_match_for_user(user.id, job.id)
        if match is not None:
            self.jobs.touch_match_view(match)

    def update_match_status(
        self, user: User, job_id: uuid.UUID, status: MatchStatus
    ) -> Job:
        job = self.get(user, job_id)
        match = self.jobs.get_match_for_user(user.id, job.id)
        if match is None:
            raise errors.not_found("Bu ilan için eşleşme kaydı bulunamadı.")
        match.status = status.value
        self.db.flush()
        self.db.refresh(job)
        return job

    def stats(self, user: User) -> JobStats:
        preference = self.preferences.get_or_create(user)
        data = self.jobs.stats(user.id, preference.min_match_score)
        return JobStats.model_validate(data)

    def filter_options(self, user: User) -> JobFilterOptions:
        return JobFilterOptions.model_validate(self.jobs.filter_options(user.id))

    def sync_status(self, user: User) -> SyncStatusResponse:
        """Base scan status; the sync API enriches it with queue state."""
        from app.core.config import settings

        last_sync = self.sync_history.latest_for_user(user.id)
        active_cv = self.cvs.get_active_for_user(user.id)
        connected = self.accounts.connected_count(user.id)
        preference = self.preferences.get_or_create(user)
        return SyncStatusResponse(
            available=True,
            phase="phase-3",
            running=False,
            message="Manuel tarama hazır.",
            last_sync_at=last_sync.started_at if last_sync else None,
            next_scan_at=None,
            last_auto_scan_at=preference.last_auto_scan_at,
            next_auto_scan_at=preference.next_scan_at,
            active_cv=active_cv.filename if active_cv else None,
            connected_accounts=connected,
            worker_hint="python -m app.worker",
            scheduler_enabled=settings.scheduler_enabled,
            llm_configured=settings.llm_configured,
        )
