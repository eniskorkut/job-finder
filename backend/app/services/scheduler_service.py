"""Per-user scheduled scans.

The scheduler lives inside the worker process (no fourth process to run) and
keeps all of its state in the database: ``user_preferences.next_scan_at`` is
the plan of record, so a restart never loses or duplicates a scan.

Claiming is done with a single atomic UPDATE per user, which is what prevents
two workers (or a worker racing a manual click) from scheduling twice.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import ConnectionStatus, SyncJobStatus, SyncTrigger
from app.models.mail_account import MailAccount
from app.models.preferences import UserPreference
from app.models.sync_job import SyncJob
from app.models.user import User
from app.repositories.sync_jobs import SyncJobAccountRepository, SyncJobRepository

logger = logging.getLogger("jobhunter.scheduler")

MAX_BACKOFF_MULTIPLIER = 6


def clamp_interval(hours: int | None) -> int:
    value = 24 if hours is None else int(hours)
    return max(settings.scheduler_min_interval_hours, min(settings.scheduler_max_interval_hours, value))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SchedulerService:
    def __init__(self, *, session_factory=SessionLocal, now: datetime | None = None) -> None:
        self.session_factory = session_factory
        self._origin = now

    def _now(self) -> datetime:
        return self._origin or utcnow()

    # --- planning -------------------------------------------------------
    def plan_next_scan(
        self,
        preference: UserPreference,
        *,
        from_time: datetime | None = None,
        failed: bool = False,
    ) -> datetime | None:
        """Compute and store the next run for one user's preferences row."""
        if not preference.daily_scan_enabled:
            preference.next_scan_at = None
            return None
        base = as_aware(from_time) or self._now()
        interval = clamp_interval(preference.scan_interval_hours)
        multiplier = 1
        if failed:
            multiplier = min(MAX_BACKOFF_MULTIPLIER, 2 ** min(4, preference.auto_scan_failures))
        preference.next_scan_at = base + timedelta(hours=interval * multiplier)
        return preference.next_scan_at

    def refresh_after_scan(
        self, user_id: uuid.UUID, *, finished_at: datetime, successful: bool
    ) -> None:
        with self.session_factory() as session:
            preference = session.execute(
                select(UserPreference).where(UserPreference.user_id == user_id)
            ).scalar_one_or_none()
            if preference is None:
                return
            if successful:
                preference.last_auto_scan_at = finished_at
                preference.auto_scan_failures = 0
            else:
                preference.auto_scan_failures = (preference.auto_scan_failures or 0) + 1
            self.plan_next_scan(preference, from_time=finished_at, failed=not successful)
            session.commit()

    # --- due work -------------------------------------------------------
    def due_user_ids(self, *, limit: int = 20) -> list[uuid.UUID]:
        now = self._now()
        with self.session_factory() as session:
            rows = session.execute(
                select(UserPreference.user_id)
                .join(User, User.id == UserPreference.user_id)
                .where(
                    UserPreference.daily_scan_enabled.is_(True),
                    UserPreference.next_scan_at.is_not(None),
                    UserPreference.next_scan_at <= now,
                    User.is_active.is_(True),
                )
                .order_by(UserPreference.next_scan_at)
                .limit(limit)
            ).scalars()
            return list(rows)

    def sync_due(self, *, limit: int = 20) -> list[uuid.UUID]:
        """Create one scheduled scan per due user; returns the created job ids."""
        created: list[uuid.UUID] = []
        for user_id in self.due_user_ids(limit=limit):
            job_id = self._schedule_user(user_id)
            if job_id is not None:
                created.append(job_id)
        if created:
            logger.info("%s kullanıcı için otomatik tarama kuyruğa alındı.", len(created))
        return created

    def _schedule_user(self, user_id: uuid.UUID) -> uuid.UUID | None:
        now = self._now()
        with self.session_factory() as session:
            preference = session.execute(
                select(UserPreference).where(UserPreference.user_id == user_id)
            ).scalar_one_or_none()
            if preference is None or not preference.daily_scan_enabled:
                return None
            if as_aware(preference.next_scan_at) is None or as_aware(preference.next_scan_at) > now:
                return None

            # Atomic claim: whoever flips next_scan_at owns this run.
            interval = clamp_interval(preference.scan_interval_hours)
            # synchronize_session=False: the claim is decided by the database,
            # not by comparing naive (SQLite) and aware datetimes in Python.
            claimed = session.execute(
                update(UserPreference)
                .where(
                    UserPreference.user_id == user_id,
                    UserPreference.daily_scan_enabled.is_(True),
                    UserPreference.next_scan_at.is_not(None),
                    UserPreference.next_scan_at <= now,
                )
                .values(next_scan_at=now + timedelta(hours=interval)),
                execution_options={"synchronize_session": False},
            )
            if not claimed.rowcount:
                session.rollback()
                return None

            accounts = list(
                session.execute(
                    select(MailAccount).where(
                        MailAccount.user_id == user_id,
                        MailAccount.status != ConnectionStatus.DISCONNECTED.value,
                    )
                ).scalars()
            )
            if not accounts:
                # Nothing to scan: keep the schedule moving instead of spinning.
                preference.auto_scan_failures = (preference.auto_scan_failures or 0) + 1
                session.commit()
                logger.info(
                    "Otomatik tarama atlandı: bağlı hesap yok (user=%s).", user_id
                )
                return None

            active = SyncJobRepository(session).active_for_user(user_id, kinds=("mail_scan",))
            if active is not None:
                # Push it out a little so the loop stays quiet until it finishes.
                preference.next_scan_at = now + timedelta(minutes=5)
                session.commit()
                return None

            job = SyncJob(
                user_id=user_id,
                kind="mail_scan",
                status=SyncJobStatus.QUEUED.value,
                trigger=SyncTrigger.SCHEDULED.value,
                accounts_total=len(accounts),
                account_ids=[str(account.id) for account in accounts],
            )
            session.add(job)
            session.flush()
            SyncJobAccountRepository(session).ensure_accounts(
                job, [account.id for account in accounts]
            )
            session.commit()
            logger.info(
                "Otomatik tarama kuyruğa alındı (user=%s, job=%s, hesaplar=%s)",
                user_id,
                job.id,
                len(accounts),
            )
            return job.id


__all__ = [
    "MAX_BACKOFF_MULTIPLIER",
    "SchedulerService",
    "SyncJob",
    "as_aware",
    "clamp_interval",
    "utcnow",
]
