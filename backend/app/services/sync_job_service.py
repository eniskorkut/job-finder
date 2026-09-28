"""Durable manual scan jobs: enqueue from the API, execute in the worker."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
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
from app.models.user import User
from app.models.job import Job
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
        items: list[dict] = []
        if (job.kind or "mail_scan") == "scoring":
            from app.repositories.sync_jobs import ScoringItemRepository

            job_lookup = {
                candidate.id: candidate
                for candidate in self.db.execute(
                    select(Job).where(Job.user_id == user.id)
                ).scalars()
            }
            for item in ScoringItemRepository(self.db).list_for_job(job.id):
                candidate = job_lookup.get(item.job_id)
                items.append(
                    {
                        "id": item.id,
                        "job_id": item.job_id,
                        "job_title": candidate.title if candidate else None,
                        "company": candidate.company if candidate else None,
                        "status": item.status,
                        "attempt": item.attempt,
                        "error_class": item.error_class,
                        "error_message": item.error_message,
                        "match_id": item.match_id,
                        "started_at": item.started_at,
                        "finished_at": item.finished_at,
                    }
                )
        return {
            "job": job,
            "items": items,
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

    def list_jobs(
        self, user: User, *, page: int = 1, page_size: int = 20, kind: str | None = None
    ):
        if kind:
            items = self.jobs.list_for_user_by_kind(user.id, kind, limit=page_size)
            return items, len(items)
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
        llm_factory=None,
        telegram_factory=None,
        now: datetime | None = None,
    ) -> None:
        self.worker_id = worker_id or default_worker_id()
        self.session_factory = session_factory
        self.client_factory = client_factory or ClientFactory()
        self.llm_factory = llm_factory
        self.telegram_factory = telegram_factory
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
        """Dispatch one durable job to its stage: mail scan, scoring, notify."""
        heartbeat = asyncio.create_task(self._heartbeat_loop(job_id))
        registered = False
        try:
            with self.session_factory() as session:
                job = session.get(SyncJob, job_id)
                kind = (job.kind if job else None) or "mail_scan"
            if kind == "scoring":
                status = await self._execute_scoring(job_id)
            elif kind == "notify":
                status = await self._execute_notify(job_id)
            else:
                status = await self._execute_mail_scan(job_id)
            registered = True
            return status
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            if not registered:
                # If execution crashed or was cancelled before finishing, release job for lease recovery
                self._release_job(job_id)

    async def _execute_scoring(self, job_id: uuid.UUID) -> SyncJobStatus:
        from app.services.scoring_runner import ScoringRunner

        runner = ScoringRunner(
            llm_factory=self.llm_factory,
            session_factory=self.session_factory,
            now=self._now,
            cancel_check=lambda: self._is_cancelled(job_id),
        )
        outcome = await runner.run(job_id)
        self._finish_job(job_id, outcome.status, error=outcome.error_message)
        return outcome.status

    async def _execute_notify(self, job_id: uuid.UUID) -> SyncJobStatus:
        from app.services.notification_service import NotificationRunner

        runner = NotificationRunner(
            client_factory=self.telegram_factory,
            session_factory=self.session_factory,
            now=self._now,
            cancel_check=lambda: self._is_cancelled(job_id),
        )
        outcome = await runner.run(job_id)
        self._finish_job(job_id, outcome.status, error=outcome.error_message)
        return outcome.status

    async def _execute_mail_scan(self, job_id: uuid.UUID) -> SyncJobStatus:
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

        semaphore = asyncio.Semaphore(max(1, settings.sync_max_active_mailboxes))

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

        results = await asyncio.gather(*(run_account(a) for a in still_queued))

        status = self._final_status(results)
        self._finish_job(job_id, status)
        return status

    async def _heartbeat_loop(self, job_id: uuid.UUID) -> None:
        interval = max(2, settings.sync_heartbeat_seconds)
        while True:
            await asyncio.sleep(interval)
            try:
                with self.session_factory() as session:
                    job = session.get(SyncJob, job_id)
                    if job is None or job.status != SyncJobStatus.RUNNING.value:
                        return
                    SyncJobRepository(session).heartbeat(
                        job, lease_seconds=settings.sync_lease_seconds
                    )
                    session.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Heartbeat başarısız (job=%s): %s", job_id, exc)

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

    def _finish_job(
        self, job_id: uuid.UUID, status: SyncJobStatus, error: str | None = None
    ) -> None:
        kind = "mail_scan"
        trigger = None
        user_id = None
        finished_at = None
        with self.session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            kind = job.kind or "mail_scan"
            trigger = job.trigger
            user_id = job.user_id
            repo = SyncJobRepository(session)
            if job.cancel_requested and status == SyncJobStatus.COMPLETED:
                status = SyncJobStatus.CANCELLED
            error = error or job.error_message
            if status in {SyncJobStatus.FAILED, SyncJobStatus.PARTIAL_FAILED} and not error:
                error = "İş tamamlanamadı; ayrıntı için ilgili ekrana bakın."
            repo.finish(job, status, error=error)
            finished_at = job.finished_at
            session.commit()

        if user_id is not None:
            self._continue_pipeline(
                kind=kind,
                trigger=trigger,
                user_id=user_id,
                status=status,
                finished_at=finished_at,
            )

    def _continue_pipeline(
        self,
        *,
        kind: str,
        trigger: str | None,
        user_id: uuid.UUID,
        status: SyncJobStatus,
        finished_at: datetime | None,
    ) -> None:
        """Hand the pipeline to the next stage. Failures here never fail a job."""
        try:
            if kind == "mail_scan":
                if trigger == SyncTrigger.SCHEDULED.value:
                    from app.services.scheduler_service import SchedulerService

                    SchedulerService(session_factory=self.session_factory, now=self._now).refresh_after_scan(
                        user_id,
                        finished_at=finished_at or datetime.now(timezone.utc),
                        successful=status == SyncJobStatus.COMPLETED,
                    )
                if status in {SyncJobStatus.COMPLETED, SyncJobStatus.PARTIAL_FAILED}:
                    from app.services.scoring_service import ScoringService

                    with self.session_factory() as session:
                        job = ScoringService(session).enqueue_for_new_jobs(user_id)
                        session.commit()
                    if job is not None:
                        logger.info(
                            "Skorlama kuyruğa alındı (user=%s, job=%s)", user_id, job.id
                        )
            elif kind == "scoring":
                if status in {SyncJobStatus.COMPLETED, SyncJobStatus.PARTIAL_FAILED}:
                    from app.services.notification_service import NotificationService

                    with self.session_factory() as session:
                        user = session.get(User, user_id)
                        job = NotificationService(session).enqueue(user) if user else None
                        session.commit()
                    if job is not None:
                        logger.info(
                            "Bildirim kuyruğa alındı (user=%s, job=%s)", user_id, job.id
                        )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Pipeline devamı kurulamadı (kind=%s, user=%s): %s",
                kind,
                user_id,
                type(exc).__name__,
            )

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
    async def run_forever(
        self,
        *,
        once: bool = False,
        poll_seconds: float | None = None,
        shutdown_event: asyncio.Event | None = None,
    ) -> int:
        processed = 0
        self.recover()
        last_scheduler_tick: datetime | None = None
        poll_timeout = poll_seconds or settings.worker_poll_seconds

        while True:
            if shutdown_event is not None and shutdown_event.is_set():
                logger.info("İşçi kontrollü şekilde durduruldu (graceful shutdown).")
                return processed

            # Stale / crashed worker jobs whose lease expired get recovered
            self.recover()

            job_id = await asyncio.to_thread(self.claim)
            if job_id is None:
                if once:
                    return processed
                last_scheduler_tick = await self._scheduler_tick(last_scheduler_tick)
                if shutdown_event is not None:
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=poll_timeout)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(poll_timeout)
                continue

            logger.info("İş alındı: %s", job_id)
            status = await self.execute(job_id)
            logger.info("İş bitti: %s -> %s", job_id, status)
            processed += 1
            if once:
                return processed

    async def _scheduler_tick(self, last_tick: datetime | None) -> datetime | None:
        """Enqueue due scheduled scans at most once per scheduler interval."""
        if not settings.scheduler_enabled:
            return last_tick
        now = self._now or datetime.now(timezone.utc)
        if last_tick is not None and (now - last_tick).total_seconds() < settings.scheduler_poll_seconds:
            return last_tick
        from app.services.scheduler_service import SchedulerService

        try:
            created = await asyncio.to_thread(
                SchedulerService(session_factory=self.session_factory, now=self._origin_now()).sync_due
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Zamanlayıcı turu başarısız: %s", type(exc).__name__)
            return now
        if created:
            logger.info("Zamanlayıcı %s tarama işi oluşturdu.", len(created))
        return now

    def _origin_now(self) -> datetime | None:
        return self._now


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
