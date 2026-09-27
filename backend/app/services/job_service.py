from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core import errors
from app.models.enums import MatchStatus
from app.models.job import Job
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.integrations import SyncHistoryRepository
from app.repositories.jobs import JobRepository, MailAccountRepository
from app.repositories.preferences import PreferenceRepository
from app.schemas.job import JobDetail, JobFilterOptions, JobRead, JobStats
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
        return detail

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
        last_sync = self.sync_history.latest_for_user(user.id)
        active_cv = self.cvs.get_active_for_user(user.id)
        connected = self.accounts.connected_count(user.id)
        return SyncStatusResponse(
            available=False,
            phase="phase-2/3",
            running=False,
            message=(
                "Otomatik tarama 2. ve 3. aşamada açılacak. Şu an tarama tetiklenemiyor."
            ),
            last_sync_at=last_sync.started_at if last_sync else None,
            next_scan_at=None,
            active_cv=active_cv.filename if active_cv else None,
            connected_accounts=connected,
        )
