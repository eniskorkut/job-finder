"""Match notifications: queue (API side) and dispatch (worker side).

Delivery is idempotent per (user, match, channel): the dedupe key is written
only after Telegram accepted the message, so retries are safe and a delivered
notification can never be sent twice. Failures never block scoring.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.db.session import SessionLocal
from app.integrations.telegram import TelegramClient, TelegramError
from app.models.enums import (
    ConnectionStatus,
    ErrorClass,
    NotificationChannel,
    NotificationStatus,
    SyncJobStatus,
    SyncTrigger,
)
from app.models.job import Job, JobMatch
from app.models.notification import NotificationHistory
from app.models.sync_job import SyncJob
from app.models.user import User
from app.repositories.integrations import TelegramRepository
from app.repositories.jobs import JobRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.sync_jobs import SyncJobRepository
from app.services.telegram_message import build_match_message

logger = logging.getLogger("jobhunter.notifications")

NOTIFY_KIND = "notify"
MAX_ATTEMPTS = 5


def dedupe_key_for(match_id: uuid.UUID) -> str:
    return f"telegram:match:{match_id}"


def default_telegram_factory(bot_token: str) -> TelegramClient:
    return TelegramClient(bot_token=bot_token)


@dataclass(slots=True)
class NotificationOutcome:
    status: SyncJobStatus = SyncJobStatus.COMPLETED
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    error_message: str | None = None


class NotificationService:
    """Read/queue side used by the API."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = JobRepository(db)
        self.preferences = PreferenceRepository(db)
        self.telegram = TelegramRepository(db)
        self.queue = SyncJobRepository(db)

    def telegram_ready(self, user_id: uuid.UUID) -> bool:
        integration = self.telegram.get_for_user(user_id)
        return bool(
            integration
            and integration.status == ConnectionStatus.CONNECTED.value
            and integration.chat_id
            and integration.bot_token_encrypted
        )

    def eligible_matches(
        self, user: User, *, match_ids: list[uuid.UUID] | None = None, limit: int = 50
    ) -> list[JobMatch]:
        preference = self.preferences.get_or_create(user)
        if not preference.notify_telegram or not self.telegram_ready(user.id):
            return []

        stmt = (
            select(JobMatch)
            .join(Job, Job.id == JobMatch.job_id)
            .where(
                JobMatch.user_id == user.id,
                Job.is_mock.is_(False),
                JobMatch.score.is_not(None),
                JobMatch.score >= preference.min_match_score,
                JobMatch.analysis_status == "completed",
                Job.availability_status.not_in(["expired", "removed", "possibly_closed", "closed"]),
            )
            .order_by(JobMatch.score.desc())
            .limit(max(1, limit))
        )
        if match_ids:
            stmt = stmt.where(JobMatch.id.in_(match_ids))
        candidates = list(self.db.execute(stmt).scalars())

        delivered = self._delivered_keys(user.id, [match.id for match in candidates])
        return [match for match in candidates if dedupe_key_for(match.id) not in delivered]

    def _delivered_keys(self, user_id: uuid.UUID, match_ids: list[uuid.UUID]) -> set[str]:
        if not match_ids:
            return set()
        keys = [dedupe_key_for(match_id) for match_id in match_ids]
        rows = self.db.execute(
            select(NotificationHistory.dedupe_key).where(
                NotificationHistory.user_id == user_id,
                NotificationHistory.dedupe_key.in_(keys),
            )
        ).scalars()
        return {row for row in rows if row}

    def enqueue(
        self,
        user: User,
        *,
        match_ids: list[uuid.UUID] | None = None,
        trigger: SyncTrigger = SyncTrigger.MANUAL,
        require_eligible: bool = True,
    ) -> SyncJob | None:
        targets = self.eligible_matches(user, match_ids=match_ids)
        if require_eligible and not targets:
            return None

        active = self.queue.active_for_user(user.id, kinds=(NOTIFY_KIND,))
        if active is not None:
            # Same reasoning as the scan queue: never run two delivery jobs for
            # one user, just report the one that is already queued.
            return active

        job = self.queue.create(
            user_id=user.id,
            kind=NOTIFY_KIND,
            trigger=trigger.value,
            payload={"match_ids": [str(match.id) for match in targets]},
            progress={"sent": 0, "failed": 0, "skipped": 0, "total": len(targets)},
        )
        return job

    def enqueue_after_scoring(self, user_id: uuid.UUID) -> SyncJob | None:
        from app.repositories.users import UserRepository

        user = UserRepository(self.db).get_by_id(user_id)
        if user is None:
            return None
        try:
            return self.enqueue(user, trigger=SyncTrigger.MANUAL)
        except errors.AppError:
            return None

    def summary(self, user: User) -> dict:
        rows = self.db.execute(
            select(NotificationHistory.status, func.count(NotificationHistory.id))
            .where(
                NotificationHistory.user_id == user.id,
                NotificationHistory.channel == NotificationChannel.TELEGRAM.value,
            )
            .group_by(NotificationHistory.status)
        ).all()
        counts = {status: int(count) for status, count in rows}
        last_sent = self.db.execute(
            select(func.max(NotificationHistory.sent_at)).where(
                NotificationHistory.user_id == user.id,
                NotificationHistory.status == NotificationStatus.SENT.value,
            )
        ).scalar_one_or_none()
        preference = self.preferences.get_or_create(user)
        return {
            "sent": counts.get(NotificationStatus.SENT.value, 0),
            "failed": counts.get(NotificationStatus.FAILED.value, 0),
            "skipped": counts.get(NotificationStatus.SKIPPED.value, 0),
            "pending": len(self.eligible_matches(user, limit=200)),
            "last_sent_at": last_sent,
            "threshold": preference.min_match_score,
            "enabled": bool(preference.notify_telegram),
            "telegram_ready": self.telegram_ready(user.id),
        }


class NotificationRunner:
    """Worker side: send eligible matches, one short transaction per step."""

    def __init__(
        self,
        *,
        client_factory: Callable[[str], object] | None = None,
        session_factory=SessionLocal,
        now: datetime | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.client_factory = client_factory or default_telegram_factory
        self.session_factory = session_factory
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

    async def run(self, job_id: uuid.UUID) -> NotificationOutcome:
        with self._db() as db:
            job = db.get(SyncJob, job_id)
            if job is None:
                return NotificationOutcome(
                    status=SyncJobStatus.FAILED, error_message="İş bulunamadı."
                )
            user_id = job.user_id
            match_ids = [uuid.UUID(value) for value in (job.payload or {}).get("match_ids", [])]

        outcome = NotificationOutcome()
        with self._db() as db:
            user = db.get(User, user_id)
            if user is None:
                return NotificationOutcome(
                    status=SyncJobStatus.FAILED, error_message="Kullanıcı bulunamadı."
                )
            service = NotificationService(db)
            if not service.telegram_ready(user_id):
                self._bump(job_id, {"skipped": len(match_ids) or 1})
                outcome.skipped = len(match_ids) or 1
                outcome.status = SyncJobStatus.COMPLETED
                outcome.error_message = "Telegram bağlı değil; bildirim gönderilmedi."
                return outcome
            targets = service.eligible_matches(user, match_ids=match_ids or None, limit=50)

        if not targets:
            outcome.status = SyncJobStatus.COMPLETED
            return outcome

        for match in targets:
            if self._cancel_check is not None and self._cancel_check():
                outcome.status = SyncJobStatus.CANCELLED
                break
            result = await self._send_one(match.id)
            if result == NotificationStatus.SENT.value:
                outcome.sent += 1
                self._bump(job_id, {"sent": 1})
            elif result == NotificationStatus.SKIPPED.value:
                outcome.skipped += 1
                self._bump(job_id, {"skipped": 1})
            else:
                outcome.failed += 1
                self._bump(job_id, {"failed": 1})

        if outcome.status is not SyncJobStatus.CANCELLED:
            if outcome.failed and outcome.sent:
                outcome.status = SyncJobStatus.PARTIAL_FAILED
            elif outcome.failed:
                outcome.status = SyncJobStatus.FAILED
            else:
                outcome.status = SyncJobStatus.COMPLETED
        if outcome.failed:
            outcome.error_message = (
                f"{outcome.failed} bildirim gönderilemedi; Telegram ayarlarını kontrol edin."
            )
        return outcome

    def _bump(self, job_id: uuid.UUID, deltas: dict[str, int]) -> None:
        with self._db() as db:
            SyncJobRepository(db).update_progress(job_id, deltas)

    # --- one notification -------------------------------------------------
    async def _send_one(self, match_id: uuid.UUID) -> str:
        with self._db() as db:
            match = db.get(JobMatch, match_id)
            if match is None:
                return NotificationStatus.SKIPPED.value
            user = db.get(User, match.user_id)
            job = db.get(Job, match.job_id)
            if user is None or job is None:
                return NotificationStatus.SKIPPED.value
            preference = PreferenceRepository(db).get_or_create(user)
            if not preference.notify_telegram:
                return NotificationStatus.SKIPPED.value
            if match.score is None or match.score < preference.min_match_score:
                return NotificationStatus.SKIPPED.value

            integration = TelegramRepository(db).get_for_user(user.id)
            if (
                integration is None
                or integration.status != ConnectionStatus.CONNECTED.value
                or not integration.chat_id
                or not integration.bot_token_encrypted
            ):
                return NotificationStatus.SKIPPED.value

            token = decrypt_secret(integration.bot_token_encrypted)
            chat_id = integration.chat_id
            user_id = user.id
            key = dedupe_key_for(match.id)
            already = db.execute(
                select(NotificationHistory.id).where(
                    NotificationHistory.user_id == user_id,
                    NotificationHistory.dedupe_key == key,
                )
            ).first()
            if already is not None:
                return NotificationStatus.SKIPPED.value
            message = build_match_message(
                job=job, match=match, score_threshold=preference.min_match_score
            )
            attempt = self._next_attempt(db, user_id, match.id)

        client = self.client_factory(token)
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            response = await client.send_message(  # type: ignore[attr-defined]
                chat_id=chat_id, text=message
            )
        except TelegramError as exc:
            self._record_failure(
                user_id=user_id,
                match_id=match.id,
                job_id=job.id,
                message=message,
                attempt=attempt,
                error=exc,
            )
            return NotificationStatus.FAILED.value
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

        self._record_success(
            user_id=user_id,
            match_id=match.id,
            job_id=job.id,
            message=message,
            attempt=attempt,
            dedupe_key=key,
            provider_message_id=str((response or {}).get("message_id") or "") or None,
        )
        return NotificationStatus.SENT.value

    # --- persistence ------------------------------------------------------
    def _next_attempt(self, db: Session, user_id: uuid.UUID, match_id: uuid.UUID) -> int:
        row = db.execute(
            select(NotificationHistory)
            .where(
                NotificationHistory.user_id == user_id,
                NotificationHistory.job_match_id == match_id,
                NotificationHistory.channel == NotificationChannel.TELEGRAM.value,
            )
            .order_by(NotificationHistory.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return int(row.attempts or 0) + 1 if row else 1

    def _record_success(
        self,
        *,
        user_id: uuid.UUID,
        match_id: uuid.UUID,
        job_id: uuid.UUID,
        message: str,
        attempt: int,
        dedupe_key: str,
        provider_message_id: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._db() as db:
            entry = self._existing_entry(db, user_id, match_id)
            if entry is None:
                entry = NotificationHistory(
                    user_id=user_id,
                    job_id=job_id,
                    job_match_id=match_id,
                    channel=NotificationChannel.TELEGRAM.value,
                )
                db.add(entry)
            entry.status = NotificationStatus.SENT.value
            entry.message = message
            entry.error_message = None
            entry.error_class = None
            entry.attempts = attempt
            entry.dedupe_key = dedupe_key
            entry.provider_message_id = provider_message_id
            entry.sent_at = now
            try:
                db.flush()
            except IntegrityError:
                # Unique (user_id, dedupe_key): another worker already delivered it.
                db.rollback()
                logger.info("Bildirim zaten gönderilmiş (match=%s); tekrar atlandı.", match_id)
                return

            match = db.get(JobMatch, match_id)
            if match is not None:
                match.notified_at = now
                if match.status in {"new", "viewed"}:
                    match.status = "notified"
            integration = TelegramRepository(db).get_for_user(user_id)
            if integration is not None:
                integration.last_notification_at = now
                integration.last_error = None
                integration.last_error_class = None

    def _record_failure(
        self,
        *,
        user_id: uuid.UUID,
        match_id: uuid.UUID,
        job_id: uuid.UUID,
        message: str,
        attempt: int,
        error: TelegramError,
    ) -> None:
        error_class = (
            error.error_class.value
            if isinstance(error.error_class, ErrorClass)
            else str(error.error_class)
        )
        with self._db() as db:
            entry = self._existing_entry(db, user_id, match_id)
            if entry is None:
                entry = NotificationHistory(
                    user_id=user_id,
                    job_id=job_id,
                    job_match_id=match_id,
                    channel=NotificationChannel.TELEGRAM.value,
                )
                db.add(entry)
            entry.status = NotificationStatus.FAILED.value
            entry.message = message
            entry.error_message = str(error)[:500]
            entry.error_class = error_class
            entry.attempts = attempt
            db.flush()

            integration = TelegramRepository(db).get_for_user(user_id)
            if integration is not None:
                integration.last_error = str(error)[:500]
                integration.last_error_class = error_class
                integration.last_checked_at = datetime.now(timezone.utc)
                if error_class == ErrorClass.AUTH.value:
                    integration.status = ConnectionStatus.NEEDS_REAUTH.value
        logger.warning(
            "Bildirim başarısız (user=%s, match=%s, class=%s, attempt=%s)",
            user_id,
            match_id,
            error_class,
            attempt,
        )

    @staticmethod
    def _existing_entry(
        db: Session, user_id: uuid.UUID, match_id: uuid.UUID
    ) -> NotificationHistory | None:
        return db.execute(
            select(NotificationHistory)
            .where(
                NotificationHistory.user_id == user_id,
                NotificationHistory.job_match_id == match_id,
                NotificationHistory.channel == NotificationChannel.TELEGRAM.value,
                NotificationHistory.dedupe_key.is_(None),
            )
            .order_by(NotificationHistory.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()


__all__ = [
    "NOTIFY_KIND",
    "NotificationOutcome",
    "NotificationRunner",
    "NotificationService",
    "dedupe_key_for",
    "settings",
]
