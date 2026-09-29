from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update

from app.models.enums import (
    CursorKind,
    ErrorClass,
    ProcessedMessageStatus,
    SyncJobAccountStatus,
    SyncJobStatus,
    SyncTrigger,
)
from app.models.sync_job import (
    EnrichmentItem,
    JobSource,
    ProcessedMessage,
    ScoringItem,
    SyncCheckpoint,
    SyncJob,
    SyncJobAccount,
)
from app.repositories.base import Repository

ACTIVE_STATUSES = (SyncJobStatus.QUEUED.value, SyncJobStatus.RUNNING.value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SyncJobRepository(Repository[SyncJob]):
    model = SyncJob

    # --- creation / reads ---------------------------------------------
    def get_for_user(self, user_id: uuid.UUID, job_id: uuid.UUID) -> SyncJob | None:
        stmt = select(SyncJob).where(SyncJob.id == job_id, SyncJob.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def active_for_user(
        self, user_id: uuid.UUID, *, kinds: tuple[str, ...] | None = None
    ) -> SyncJob | None:
        stmt = select(SyncJob).where(
            SyncJob.user_id == user_id, SyncJob.status.in_(ACTIVE_STATUSES)
        )
        if kinds:
            stmt = stmt.where(SyncJob.kind.in_(kinds))
        stmt = stmt.order_by(SyncJob.requested_at.desc()).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: uuid.UUID,
        kind: str = "mail_scan",
        trigger: str = SyncTrigger.MANUAL.value,
        payload: dict | None = None,
        progress: dict | None = None,
        accounts_total: int = 0,
        account_ids: list[str] | None = None,
    ) -> SyncJob:
        job = SyncJob(
            user_id=user_id,
            kind=kind,
            status=SyncJobStatus.QUEUED.value,
            trigger=trigger,
            payload=payload or {},
            progress=progress or {},
            accounts_total=accounts_total,
            account_ids=account_ids or [],
        )
        self.db.add(job)
        self.db.flush()
        return job

    def list_for_user_by_kind(
        self, user_id: uuid.UUID, kind: str, *, limit: int = 20
    ) -> list[SyncJob]:
        stmt = (
            select(SyncJob)
            .where(SyncJob.user_id == user_id, SyncJob.kind == kind)
            .order_by(SyncJob.requested_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 20
    ) -> tuple[list[SyncJob], int]:
        stmt = (
            select(SyncJob)
            .where(SyncJob.user_id == user_id)
            .order_by(SyncJob.requested_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.execute(stmt).scalars())
        total = int(
            self.db.execute(
                select(func.count(SyncJob.id)).where(SyncJob.user_id == user_id)
            ).scalar_one()
        )
        return items, total

    def latest_for_user_kind(self, user_id: uuid.UUID, kind: str) -> SyncJob | None:
        stmt = (
            select(SyncJob)
            .where(SyncJob.user_id == user_id, SyncJob.kind == kind)
            .order_by(SyncJob.requested_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def last_by_kind_and_trigger(
        self, user_id: uuid.UUID, *, kind: str, trigger: str
    ) -> SyncJob | None:
        stmt = (
            select(SyncJob)
            .where(
                SyncJob.user_id == user_id,
                SyncJob.kind == kind,
                SyncJob.trigger == trigger,
            )
            .order_by(SyncJob.requested_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def latest_for_user(self, user_id: uuid.UUID) -> SyncJob | None:
        stmt = (
            select(SyncJob)
            .where(SyncJob.user_id == user_id)
            .order_by(SyncJob.requested_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    # --- worker side ---------------------------------------------------
    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int | None = None,
        now: datetime | None = None,
    ) -> SyncJob | None:
        """Optimistic claim: pick an eligible queued job, then flip it if still queued."""
        limit_attempts = (
            max_attempts if max_attempts is not None else 3
        )
        current_time = now or _now()
        candidates = self.db.execute(
            select(SyncJob.id)
            .where(
                SyncJob.status == SyncJobStatus.QUEUED.value,
                SyncJob.attempt < limit_attempts,
                or_(
                    SyncJob.next_attempt_at.is_(None),
                    SyncJob.next_attempt_at <= current_time,
                ),
            )
            .order_by(SyncJob.requested_at)
            .limit(5)
        ).scalars()
        for job_id in list(candidates):
            result = self.db.execute(
                update(SyncJob)
                .where(
                    SyncJob.id == job_id,
                    SyncJob.status == SyncJobStatus.QUEUED.value,
                    SyncJob.attempt < limit_attempts,
                    or_(
                        SyncJob.next_attempt_at.is_(None),
                        SyncJob.next_attempt_at <= current_time,
                    ),
                )
                .values(
                    status=SyncJobStatus.RUNNING.value,
                    worker_id=worker_id,
                    attempt=SyncJob.attempt + 1,
                    # coalesce keeps the first start time when a recovered job runs again
                    started_at=func.coalesce(SyncJob.started_at, current_time),
                    heartbeat_at=current_time,
                    lease_expires_at=current_time + timedelta(seconds=lease_seconds),
                    next_attempt_at=None,
                )
            )
            if result.rowcount:
                self.db.flush()
                return self.db.get(SyncJob, job_id)
            self.db.expire_all()
        return None

    def heartbeat(self, job: SyncJob, *, lease_seconds: int) -> None:
        now = _now()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.db.flush()

    def is_cancel_requested(self, job: SyncJob) -> bool:
        self.db.refresh(job, ["cancel_requested"])
        return bool(job.cancel_requested)

    def request_cancel(self, job: SyncJob) -> None:
        job.cancel_requested = True
        if job.status == SyncJobStatus.QUEUED.value:
            job.status = SyncJobStatus.CANCELLED.value
            job.finished_at = _now()
        self.db.flush()

    def finish(self, job: SyncJob, status: SyncJobStatus, error: str | None = None) -> None:
        job.status = status.value
        job.error_message = error
        job.finished_at = _now()
        job.lease_expires_at = None
        job.next_attempt_at = None
        self.db.flush()

    def recover_expired_leases(
        self, *, max_attempts: int, now: datetime | None = None
    ) -> list[SyncJob]:
        """Return stale jobs to the queue, or fail them once attempts run out."""
        current_time = now or _now()
        stale = list(
            self.db.execute(
                select(SyncJob).where(
                    SyncJob.status == SyncJobStatus.RUNNING.value,
                    SyncJob.lease_expires_at.is_not(None),
                    SyncJob.lease_expires_at < current_time,
                )
            ).scalars()
        )
        for job in stale:
            if job.attempt >= max_attempts:
                job.status = SyncJobStatus.FAILED.value
                job.finished_at = current_time
                job.worker_id = None
                job.lease_expires_at = None
                job.next_attempt_at = None
                job.error_message = (
                    job.error_message
                    or f"İşçi süreci yanıt vermedi ve {job.attempt} deneme hakkı doldu."
                )
            else:
                job.status = SyncJobStatus.QUEUED.value
                job.worker_id = None
                job.lease_expires_at = None
                job.next_attempt_at = None
            self.db.execute(
                update(SyncJobAccount)
                .where(
                    SyncJobAccount.sync_job_id == job.id,
                    SyncJobAccount.status == SyncJobAccountStatus.RUNNING.value,
                )
                .values(
                    status=(
                        SyncJobAccountStatus.FAILED.value
                        if job.attempt >= max_attempts
                        else SyncJobAccountStatus.QUEUED.value
                    )
                )
            )
            # A crashed scoring job must not leave items stuck in ``running``.
            self.db.execute(
                update(ScoringItem)
                .where(
                    ScoringItem.sync_job_id == job.id,
                    ScoringItem.status == "running",
                )
                .values(
                    status=(
                        "failed"
                        if job.attempt >= max_attempts
                        else "queued"
                    )
                )
            )
        if stale:
            self.db.flush()
        return stale

    def has_work(self) -> bool:
        return (
            self.db.execute(
                select(func.count(SyncJob.id)).where(
                    SyncJob.status == SyncJobStatus.QUEUED.value
                )
            ).scalar_one()
            > 0
        )

    def update_progress(self, job_id: uuid.UUID, deltas: dict[str, int]) -> None:
        """Atomic counters for the JSON progress document (short transaction)."""
        from sqlalchemy import update as sa_update

        if not deltas:
            return
        job = self.db.get(SyncJob, job_id)
        if job is None:
            return
        progress = dict(job.progress or {})
        for key, value in deltas.items():
            progress[key] = int(progress.get(key, 0)) + int(value)
        self.db.execute(
            sa_update(SyncJob).where(SyncJob.id == job_id).values(progress=progress)
        )
        self.db.flush()


class SyncJobAccountRepository(Repository[SyncJobAccount]):
    model = SyncJobAccount

    def ensure_accounts(
        self, job: SyncJob, account_ids: list[uuid.UUID]
    ) -> list[SyncJobAccount]:
        existing = {
            row.mail_account_id
            for row in self.db.execute(
                select(SyncJobAccount).where(SyncJobAccount.sync_job_id == job.id)
            ).scalars()
        }
        for account_id in account_ids:
            if account_id in existing:
                continue
            self.db.add(
                SyncJobAccount(
                    sync_job_id=job.id,
                    user_id=job.user_id,
                    mail_account_id=account_id,
                )
            )
        self.db.flush()
        return self.list_for_job(job.id)

    def list_for_job(self, job_id: uuid.UUID) -> list[SyncJobAccount]:
        stmt = (
            select(SyncJobAccount)
            .where(SyncJobAccount.sync_job_id == job_id)
            .order_by(SyncJobAccount.mail_account_id)
        )
        return list(self.db.execute(stmt).scalars())

    def pending_for_job(self, job_id: uuid.UUID) -> list[SyncJobAccount]:
        stmt = (
            select(SyncJobAccount)
            .where(
                SyncJobAccount.sync_job_id == job_id,
                SyncJobAccount.status == SyncJobAccountStatus.QUEUED.value,
            )
            .order_by(SyncJobAccount.mail_account_id)
        )
        return list(self.db.execute(stmt).scalars())

    def mark_running(self, item: SyncJobAccount) -> None:
        item.status = SyncJobAccountStatus.RUNNING.value
        item.started_at = _now()
        self.db.flush()

    def mark_finished(
        self,
        item: SyncJobAccount,
        *,
        status: SyncJobAccountStatus,
        error_message: str | None = None,
        error_class: ErrorClass = ErrorClass.NONE,
    ) -> None:
        item.status = status.value
        item.error_message = error_message
        item.error_class = error_class.value if isinstance(error_class, ErrorClass) else str(error_class)
        item.finished_at = _now()
        self.db.flush()


class ScoringItemRepository(Repository[ScoringItem]):
    model = ScoringItem

    def list_for_job(self, job_id: uuid.UUID) -> list[ScoringItem]:
        stmt = (
            select(ScoringItem)
            .where(ScoringItem.sync_job_id == job_id)
            .order_by(ScoringItem.id)
        )
        return list(self.db.execute(stmt).scalars())

    def create_items(
        self, job: SyncJob, entries: list[tuple[uuid.UUID, str | None]]
    ) -> list[ScoringItem]:
        existing = {item.job_id for item in self.list_for_job(job.id)}
        for job_id, cv_checksum in entries:
            if job_id in existing:
                continue
            self.db.add(
                ScoringItem(
                    sync_job_id=job.id,
                    user_id=job.user_id,
                    job_id=job_id,
                    cv_checksum=cv_checksum,
                    status="queued",
                )
            )
        self.db.flush()
        return self.list_for_job(job.id)

    def claim(self, item: ScoringItem) -> bool:
        """queued -> running, atomically; False when somebody else took it."""
        result = self.db.execute(
            update(ScoringItem)
            .where(
                ScoringItem.id == item.id,
                ScoringItem.status.in_(["queued", "retryable"]),
            )
            .values(
                status="running",
                attempt=ScoringItem.attempt + 1,
                started_at=func.now(),
            )
        )
        self.db.flush()
        if result.rowcount:
            self.db.refresh(item)
            return True
        return False

    def mark_finished(
        self,
        item: ScoringItem,
        *,
        status: str,
        match_id: uuid.UUID | None = None,
        error_class: ErrorClass | str | None = None,
        error_message: str | None = None,
    ) -> None:
        item.status = status
        item.match_id = match_id or item.match_id
        item.error_class = (
            error_class.value if isinstance(error_class, ErrorClass) else error_class
        )
        item.error_message = (error_message or None) and error_message[:400]
        item.finished_at = _now()
        self.db.flush()

    def pending_for_job(self, job_id: uuid.UUID) -> list[ScoringItem]:
        stmt = (
            select(ScoringItem)
            .where(
                ScoringItem.sync_job_id == job_id,
                ScoringItem.status.in_(["queued", "retryable"]),
            )
            .order_by(ScoringItem.id)
        )
        return list(self.db.execute(stmt).scalars())

    def requeue_running(self, job_id: uuid.UUID) -> int:
        result = self.db.execute(
            update(ScoringItem)
            .where(
                ScoringItem.sync_job_id == job_id,
                ScoringItem.status == "running",
            )
            .values(status="queued")
        )
        self.db.flush()
        return int(result.rowcount or 0)


class EnrichmentItemRepository(Repository[EnrichmentItem]):
    model = EnrichmentItem

    def list_for_job(self, job_id: uuid.UUID) -> list[EnrichmentItem]:
        stmt = (
            select(EnrichmentItem)
            .where(EnrichmentItem.sync_job_id == job_id)
            .order_by(EnrichmentItem.id)
        )
        return list(self.db.execute(stmt).scalars())

    def create_items(
        self, job: SyncJob, job_ids: list[uuid.UUID]
    ) -> list[EnrichmentItem]:
        existing = {item.job_id for item in self.list_for_job(job.id)}
        for job_id in job_ids:
            if job_id in existing:
                continue
            self.db.add(
                EnrichmentItem(
                    sync_job_id=job.id,
                    user_id=job.user_id,
                    job_id=job_id,
                    status="queued",
                )
            )
        self.db.flush()
        return self.list_for_job(job.id)

    def claim(self, item: EnrichmentItem) -> bool:
        """queued -> running, atomically; False when somebody else took it."""
        result = self.db.execute(
            update(EnrichmentItem)
            .where(
                EnrichmentItem.id == item.id,
                EnrichmentItem.status.in_(["queued", "retryable"]),
            )
            .values(
                status="running",
                attempt=EnrichmentItem.attempt + 1,
                started_at=func.now(),
            )
        )
        self.db.flush()
        if result.rowcount:
            self.db.refresh(item)
            return True
        return False

    def mark_finished(
        self,
        item: EnrichmentItem,
        *,
        status: str,
        source_type: str | None = None,
        source_url: str | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> None:
        item.status = status
        item.source_type = source_type or item.source_type
        item.source_url = source_url or item.source_url
        item.error_class = error_class
        item.error_message = (error_message or None) and error_message[:400]
        item.finished_at = _now()
        self.db.flush()

    def pending_for_job(self, job_id: uuid.UUID) -> list[EnrichmentItem]:
        stmt = (
            select(EnrichmentItem)
            .where(
                EnrichmentItem.sync_job_id == job_id,
                EnrichmentItem.status.in_(["queued", "retryable"]),
            )
            .order_by(EnrichmentItem.id)
        )
        return list(self.db.execute(stmt).scalars())

    def requeue_running(self, job_id: uuid.UUID) -> int:
        result = self.db.execute(
            update(EnrichmentItem)
            .where(
                EnrichmentItem.sync_job_id == job_id,
                EnrichmentItem.status == "running",
            )
            .values(status="queued")
        )
        self.db.flush()
        return int(result.rowcount or 0)


class CheckpointRepository(Repository[SyncCheckpoint]):
    model = SyncCheckpoint

    def get_for_account(self, mail_account_id: uuid.UUID) -> SyncCheckpoint | None:
        stmt = select(SyncCheckpoint).where(
            SyncCheckpoint.mail_account_id == mail_account_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(self, user_id: uuid.UUID, mail_account_id: uuid.UUID) -> SyncCheckpoint:
        checkpoint = self.get_for_account(mail_account_id)
        if checkpoint is None:
            checkpoint = SyncCheckpoint(
                user_id=user_id,
                mail_account_id=mail_account_id,
                cursor_kind=CursorKind.NONE.value,
            )
            self.db.add(checkpoint)
            self.db.flush()
        return checkpoint

    def advance(
        self,
        checkpoint: SyncCheckpoint,
        *,
        cursor_kind: CursorKind,
        cursor_value: str | None,
        last_message_at: datetime | None = None,
        initial_sync_completed: bool | None = None,
    ) -> None:
        """Move the cursor forward. Only call this after the covered work is
        committed, otherwise a crash could skip messages."""
        checkpoint.cursor_kind = cursor_kind.value
        if cursor_value is not None:
            checkpoint.cursor_value = cursor_value
        checkpoint.cursor_updated_at = _now()
        checkpoint.last_synced_at = _now()
        if last_message_at is not None:
            current = _aware(checkpoint.last_message_at)
            incoming = _aware(last_message_at)
            if current is None or (incoming is not None and incoming > current):
                checkpoint.last_message_at = last_message_at
        if initial_sync_completed is not None:
            checkpoint.initial_sync_completed = initial_sync_completed
        checkpoint.consecutive_failures = 0
        checkpoint.last_error = None
        checkpoint.last_error_class = ErrorClass.NONE.value
        self.db.flush()

    def mark_failure(
        self, checkpoint: SyncCheckpoint, *, message: str, error_class: ErrorClass
    ) -> None:
        checkpoint.consecutive_failures += 1
        checkpoint.last_error = message[:1000]
        checkpoint.last_error_class = error_class.value
        self.db.flush()

    def reset_cursor(self, checkpoint: SyncCheckpoint, *, reason: str) -> None:
        checkpoint.cursor_kind = CursorKind.NONE.value
        checkpoint.cursor_value = None
        checkpoint.cursor_updated_at = None
        checkpoint.initial_sync_completed = False
        checkpoint.last_error = reason[:1000]
        self.db.flush()


class ProcessedMessageRepository(Repository[ProcessedMessage]):
    model = ProcessedMessage

    def get(
        self, mail_account_id: uuid.UUID, provider_message_id: str
    ) -> ProcessedMessage | None:
        stmt = select(ProcessedMessage).where(
            ProcessedMessage.mail_account_id == mail_account_id,
            ProcessedMessage.provider_message_id == provider_message_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def already_processed(self, mail_account_id: uuid.UUID, provider_message_id: str) -> bool:
        return self.get(mail_account_id, provider_message_id) is not None

    def record(
        self,
        *,
        user_id: uuid.UUID,
        mail_account_id: uuid.UUID,
        provider_message_id: str,
        status: ProcessedMessageStatus,
        reason: str | None = None,
        subject: str | None = None,
        sender: str | None = None,
        received_at: datetime | None = None,
        jobs_found: int = 0,
    ) -> ProcessedMessage:
        entry = ProcessedMessage(
            user_id=user_id,
            mail_account_id=mail_account_id,
            provider_message_id=provider_message_id,
            status=status.value,
            reason=reason[:160] if reason else None,
            subject=subject[:500] if subject else None,
            sender=sender[:320] if sender else None,
            received_at=received_at,
            jobs_found=jobs_found,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def count_for_user(self, user_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(ProcessedMessage.id)).where(
                    ProcessedMessage.user_id == user_id
                )
            ).scalar_one()
        )


class JobSourceRepository(Repository[JobSource]):
    model = JobSource

    def list_for_job(self, job_id: uuid.UUID) -> list[JobSource]:
        stmt = (
            select(JobSource)
            .where(JobSource.job_id == job_id)
            .order_by(JobSource.discovered_at)
        )
        return list(self.db.execute(stmt).scalars())

    def exists(self, job_id: uuid.UUID, provider_message_id: str) -> bool:
        stmt = select(JobSource.id).where(
            JobSource.job_id == job_id,
            JobSource.provider_message_id == provider_message_id,
        )
        return self.db.execute(stmt).first() is not None

    def add(
        self,
        *,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        mail_account_id: uuid.UUID | None,
        provider: str,
        provider_message_id: str,
        subject: str | None,
        sender: str | None,
        received_at: datetime | None,
    ) -> JobSource:
        source = JobSource(
            user_id=user_id,
            job_id=job_id,
            mail_account_id=mail_account_id,
            provider=provider,
            provider_message_id=provider_message_id,
            subject=subject[:500] if subject else None,
            sender=sender[:320] if sender else None,
            received_at=received_at,
        )
        self.db.add(source)
        self.db.flush()
        return source
