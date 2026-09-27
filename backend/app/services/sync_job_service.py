"""Durable manual scan jobs: enqueue from the API, execute in the worker."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import (
    ConnectionStatus,
    SyncJobAccountStatus,
    SyncJobStatus,
    SyncTrigger,
)
from app.models.sync_job import SyncJob, SyncJobAccount
from app.models.user import User
from app.repositories.jobs import MailAccountRepository
from app.repositories.sync_jobs import SyncJobAccountRepository, SyncJobRepository
from app.services.mail_scan_service import AccountScanOutcome, MailScanService
from app.services.oauth_service import ClientFactory

logger = logging.getLogger("jobhunter.sync")


def default_worker_id() -> str:
    return settings.worker_id or f"{socket.gethostname()}:{__import__('os').getpid()}"


class SyncJobService:
    """API side of the queue."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = SyncJobRepository(db)
        self.accounts = MailAccountRepository(db)

    def runnable_accounts(self, user: User) -> list:
        return [
            account
            for account in self.accounts.list_for_user(user.id)
            if account.status != ConnectionStatus.DISCONNECTED.value
        ]

    def enqueue(
        self,
        user: User,
        *,
        account_ids: list[uuid.UUID] | None = None,
        trigger: SyncTrigger = SyncTrigger.MANUAL,
    ) -> SyncJob:
        active = self.jobs.active_for_user(user.id)
        if active is not None:
            raise errors.conflict(
                "Bu kullanıcı için zaten çalışan bir tarama var; bitmesini bekleyin "
                f"(iş: {active.id})."
            )

        runnable = self.runnable_accounts(user)
        if account_ids:
            wanted = set(account_ids)
            runnable = [account for account in runnable if account.id in wanted]
            if not runnable:
                raise errors.not_found("Seçilen hesaplar bulunamadı.")
        if not runnable:
            raise errors.validation_error(
                "Bağlı bir e-posta hesabı yok. Entegrasyonlar ekranından Gmail veya "
                "Hotmail/Outlook hesabınızı bağlayın."
            )

        job = SyncJob(
            user_id=user.id,
            status=SyncJobStatus.QUEUED.value,
            trigger=trigger.value,
            accounts_total=len(runnable),
            account_ids=[str(account.id) for account in runnable],
        )
        self.db.add(job)
        self.db.flush()
        SyncJobAccountRepository(self.db).ensure_accounts(
            job, [account.id for account in runnable]
        )
        return job

    def progress(self, user: User, job_id: uuid.UUID) -> dict:
        job = self.jobs.get_for_user(user.id, job_id)
        if job is None:
            raise errors.not_found("Tarama işi bulunamadı.")
        account_rows = SyncJobAccountRepository(self.db).list_for_job(job.id)
        accounts_by_id = {
            account.id: account for account in self.accounts.list_for_user(user.id)
        }
        return {
            "job": job,
            "accounts": [
                {
                    "id": row.id,
                    "mail_account_id": row.mail_account_id,
                    "email_address": (
                        accounts_by_id[row.mail_account_id].email_address
                        if row.mail_account_id in accounts_by_id
                        else None
                    ),
                    "provider": (
                        accounts_by_id[row.mail_account_id].provider
                        if row.mail_account_id in accounts_by_id
                        else None
                    ),
                    "status": row.status,
                    "messages_scanned": row.messages_scanned,
                    "jobs_found": row.jobs_found,
                    "jobs_new": row.jobs_new,
                    "jobs_duplicate": row.jobs_duplicate,
                    "messages_skipped": row.messages_skipped,
                    "error_class": row.error_class,
                    "error_message": row.error_message,
                    "started_at": row.started_at,
                    "finished_at": row.finished_at,
                }
                for row in account_rows
            ],
        }

    def cancel(self, user: User, job_id: uuid.UUID) -> SyncJob:
        job = self.jobs.get_for_user(user.id, job_id)
        if job is None:
            raise errors.not_found("Tarama işi bulunamadı.")
        if job.status in {
            SyncJobStatus.COMPLETED.value,
            SyncJobStatus.FAILED.value,
            SyncJobStatus.CANCELLED.value,
            SyncJobStatus.PARTIAL_FAILED.value,
        }:
            raise errors.conflict("Bu iş zaten bitmiş.")
        self.jobs.request_cancel(job)
        return job

    def list_jobs(self, user: User, *, page: int = 1, page_size: int = 20):
        return self.jobs.list_for_user(
            user.id, offset=(page - 1) * page_size, limit=page_size
        )

    def latest(self, user: User) -> SyncJob | None:
        return self.jobs.latest_for_user(user.id)


class SyncRunner:
    """Worker side: claim queued jobs and execute mailboxes concurrently."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        session_factory=SessionLocal,
        client_factory: ClientFactory | None = None,
        now: datetime | None = None,
    ) -> None:
        self.worker_id = worker_id or default_worker_id()
        self.session_factory = session_factory
        self.client_factory = client_factory or ClientFactory()
        self._now = now

    # --- queue handling -------------------------------------------------
    def recover(self) -> int:
        with self.session_factory() as session:
            recovered = SyncJobRepository(session).recover_expired_leases(
                max_attempts=settings.sync_max_attempts
            )
            session.commit()
            if recovered:
                logger.warning(
                    "%s süresi geçmiş tarama işi kurtarıldı.", len(recovered)
                )
            return len(recovered)

    def claim(self) -> uuid.UUID | None:
        with self.session_factory() as session:
            job = SyncJobRepository(session).claim_next(
                worker_id=self.worker_id, lease_seconds=settings.sync_lease_seconds
            )
            session.commit()
            return job.id if job else None

    # --- execution ------------------------------------------------------
    async def execute(self, job_id: uuid.UUID) -> SyncJobStatus:
        with self.session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return SyncJobStatus.FAILED
            user_id = job.user_id
            account_rows = SyncJobAccountRepository(session).list_for_job(job_id)
            pending = [row.mail_account_id for row in account_rows]
            still_queued = [
                row.mail_account_id
                for row in account_rows
                if row.status in {SyncJobAccountStatus.QUEUED.value, SyncJobAccountStatus.RUNNING.value}
            ]
            session.commit()

        if not still_queued:
            self._finish_job(job_id, SyncJobStatus.COMPLETED)
            return SyncJobStatus.COMPLETED

        heartbeat = asyncio.create_task(self._heartbeat_loop(job_id))
        semaphore = asyncio.Semaphore(max(1, settings.sync_max_active_mailboxes))
        registered = False

        async def run_account(account_id: uuid.UUID) -> AccountScanOutcome:
            async with semaphore:
                if self._is_cancelled(job_id):
                    self._finish_account(
                        job_id,
                        account_id,
                        AccountScanOutcome(
                            status=SyncJobAccountStatus.SKIPPED,
                            error_message="Kullanıcı taramayı iptal etti.",
                        ),
                    )
                    return AccountScanOutcome(status=SyncJobAccountStatus.SKIPPED)
                self._mark_account_running(job_id, account_id)
                try:
                    outcome = await MailScanService(
                        user_id=user_id,
                        account_id=account_id,
                        job_id=job_id,
                        client_factory=self.client_factory,
                        session_factory=self.session_factory,
                        cancel_check=lambda: self._is_cancelled(job_id),
                        now=self._now,
                    ).run()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Hesap taraması çöktü: %s", exc)
                    from app.models.enums import ErrorClass

                    outcome = AccountScanOutcome(
                        status=SyncJobAccountStatus.FAILED,
                        error_message=f"Beklenmeyen hata: {type(exc).__name__}",
                        error_class=ErrorClass.TRANSIENT,
                    )
                self._finish_account(job_id, account_id, outcome)
                return outcome

        try:
            results = await asyncio.gather(*(run_account(a) for a in still_queued))
            registered = True
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            if not registered:
                # Lease recovery will pick the job up again.
                self._release_job(job_id)

        status = self._final_status(results)
        self._finish_job(job_id, status)
        return status

    async def _heartbeat_loop(self, job_id: uuid.UUID) -> None:
        interval = max(2, settings.sync_heartbeat_seconds)
        while True:
            await asyncio.sleep(interval)
            with self.session_factory() as session:
                job = session.get(SyncJob, job_id)
                if job is None:
                    return
                SyncJobRepository(session).heartbeat(
                    job, lease_seconds=settings.sync_lease_seconds
                )
                session.commit()

    def _is_cancelled(self, job_id: uuid.UUID) -> bool:
        with self.session_factory() as session:
            job = session.get(SyncJob, job_id)
            return bool(job and job.cancel_requested)

    def _mark_account_running(self, job_id: uuid.UUID, account_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            rows = SyncJobAccountRepository(session).list_for_job(job_id)
            for row in rows:
                if row.mail_account_id != account_id:
                    continue
                if row.status not in {
                    SyncJobAccountStatus.QUEUED.value,
                    SyncJobAccountStatus.RUNNING.value,
                }:
                    return
                SyncJobAccountRepository(session).mark_running(row)
            session.commit()

    def _finish_account(
        self, job_id: uuid.UUID, account_id: uuid.UUID, outcome: AccountScanOutcome
    ) -> None:
        with self.session_factory() as session:
            rows = SyncJobAccountRepository(session).list_for_job(job_id)
            repo = SyncJobAccountRepository(session)
            for row in rows:
                if row.mail_account_id != account_id:
                    continue
                row.messages_scanned += outcome.messages_scanned
                row.jobs_found += outcome.jobs_found
                row.jobs_new += outcome.jobs_new
                row.jobs_duplicate += outcome.jobs_duplicate
                row.messages_skipped += outcome.messages_skipped
                repo.mark_finished(
                    row,
                    status=outcome.status,
                    error_message=outcome.error_message,
                    error_class=outcome.error_class,
                )
            job = session.get(SyncJob, job_id)
            if job is not None and job.accounts_processed < job.accounts_total:
                job.accounts_processed += 1
            if job is not None and outcome.error_message:
                job.errors_count += 1
            session.commit()

    @staticmethod
    def _final_status(results: list[AccountScanOutcome]) -> SyncJobStatus:
        if not results:
            return SyncJobStatus.COMPLETED
        succeeded = [
            outcome
            for outcome in results
            if outcome.status == SyncJobAccountStatus.SUCCEEDED
        ]
        skipped = [
            outcome
            for outcome in results
            if outcome.status == SyncJobAccountStatus.SKIPPED
        ]
        failed = [
            outcome
            for outcome in results
            if outcome.status == SyncJobAccountStatus.FAILED
        ]
        if not failed:
            return SyncJobStatus.COMPLETED
        if skipped and not succeeded:
            return SyncJobStatus.CANCELLED
        if succeeded:
            return SyncJobStatus.PARTIAL_FAILED
        return SyncJobStatus.FAILED

    def _finish_job(self, job_id: uuid.UUID, status: SyncJobStatus) -> None:
        with self.session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            repo = SyncJobRepository(session)
            if job.cancel_requested and status == SyncJobStatus.COMPLETED:
                status = SyncJobStatus.CANCELLED
            error = job.error_message
            if status in {SyncJobStatus.FAILED, SyncJobStatus.PARTIAL_FAILED} and not error:
                error = "Bir veya daha fazla posta kutusu taranamadı. Ayrıntı için hesaplara bakın."
            repo.finish(job, status, error=error)
            session.commit()

    def _release_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            job.status = SyncJobStatus.QUEUED.value
            job.worker_id = None
            job.lease_expires_at = None
            session.commit()

    # --- loop -----------------------------------------------------------
    async def run_forever(self, *, once: bool = False, poll_seconds: float | None = None) -> int:
        processed = 0
        self.recover()
        while True:
            job_id = await asyncio.to_thread(self.claim)
            if job_id is None:
                if once:
                    return processed
                await asyncio.sleep(poll_seconds or settings.worker_poll_seconds)
                continue
            logger.info("Tarama işi alındı: %s", job_id)
            status = await self.execute(job_id)
            logger.info("Tarama işi bitti: %s -> %s", job_id, status)
            processed += 1
            if once:
                return processed


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
