from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.security import hash_password
from app.models.enums import ConnectionStatus, UserRole
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.integrations import SyncHistoryRepository, TelegramRepository
from app.repositories.jobs import JobRepository, MailAccountRepository
from app.repositories.sync_jobs import SyncJobRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.users import UserRepository
from app.schemas.user import IntegrationStatusSummary, OverviewResponse


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.preferences = PreferenceRepository(db)
        self.jobs = JobRepository(db)
        self.cvs = CVRepository(db)
        self.accounts = MailAccountRepository(db)
        self.telegram = TelegramRepository(db)
        self.sync_history = SyncHistoryRepository(db)
        self.sync_jobs = SyncJobRepository(db)

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        full_name: str | None = None,
        role: str = UserRole.MEMBER.value,
        make_owner: bool = False,
    ) -> User:
        username = username.strip()
        email = email.strip().lower()
        if self.users.username_exists(username):
            raise errors.conflict("Bu kullanıcı adı zaten alınmış.")
        if self.users.email_exists(email):
            raise errors.conflict("Bu e-posta ile kayıtlı bir kullanıcı zaten var.")

        if make_owner and self.users.count(User.role == UserRole.OWNER.value) > 0:
            raise errors.conflict("Zaten bir owner kullanıcı var.")

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            full_name=(full_name or "").strip() or None,
            role=UserRole.OWNER.value if make_owner else role,
        )
        self.db.add(user)
        self.db.flush()
        self.preferences.get_or_create(user)
        return user

    def update_profile(self, user: User, *, full_name: str | None, email: str | None) -> User:
        if full_name is not None:
            user.full_name = full_name.strip() or None
        if email is not None:
            email = email.strip().lower()
            if self.users.email_exists(email, exclude_id=user.id):
                raise errors.conflict("Bu e-posta başka bir kullanıcıya ait.")
            user.email = email
        self.db.flush()
        return user

    def overview(self, user: User) -> OverviewResponse:
        from app.integrations.deepseek import DeepSeekScoringClient
        from app.services.notification_service import NotificationService

        preferences = self.preferences.get_or_create(user)
        stats = self.jobs.stats(user.id, preferences.min_match_score)
        last_sync = self.sync_history.latest_for_user(user.id)
        accounts = self.accounts.list_for_user(user.id)
        active_job = self.sync_jobs.active_for_user(user.id)
        latest_job = self.sync_jobs.latest_for_user(user.id)
        connected_accounts = sum(
            1 for account in accounts if account.status == ConnectionStatus.CONNECTED.value
        )

        telegram = self.telegram.get_for_user(user.id)
        telegram_status = (
            telegram.status if telegram is not None else ConnectionStatus.DISCONNECTED.value
        )

        integrations = [
            IntegrationStatusSummary(
                provider="gmail",
                label="Gmail",
                status=_aggregate_status(accounts, "gmail"),
                available=True,
                account_count=sum(1 for a in accounts if a.provider == "gmail"),
                detail="Kendi Google OAuth uygulamanızla bağlanır.",
                last_synced_at=_max_dt([a.last_synced_at for a in accounts if a.provider == "gmail"]),
            ),
            IntegrationStatusSummary(
                provider="outlook",
                label="Hotmail / Outlook",
                status=_aggregate_status(accounts, "outlook"),
                available=True,
                account_count=sum(1 for a in accounts if a.provider == "outlook"),
                detail="Kendi Microsoft Entra uygulamanızla bağlanır.",
                last_synced_at=_max_dt([a.last_synced_at for a in accounts if a.provider == "outlook"]),
            ),
            IntegrationStatusSummary(
                provider="telegram",
                label="Telegram",
                status=telegram_status,
                available=True,
                account_count=1 if telegram_status == ConnectionStatus.CONNECTED.value else 0,
                detail=telegram.username or "Kullanıcı bazlı bot token ve Chat ID ile bildirim.",
                last_synced_at=telegram.linked_at if telegram else None,
            ),
        ]

        last_sync_at = None
        last_sync_status = None
        if latest_job is not None:
            last_sync_at = (
                latest_job.finished_at or latest_job.started_at or latest_job.requested_at
            )
            last_sync_status = latest_job.status
        elif last_sync is not None:
            last_sync_at = last_sync.started_at
            last_sync_status = last_sync.status

        manual_scan = self.sync_jobs.last_by_kind_and_trigger(
            user.id, kind="mail_scan", trigger="manual"
        )
        auto_scan = self.sync_jobs.last_by_kind_and_trigger(
            user.id, kind="mail_scan", trigger="scheduled"
        )
        auto_scan_at = _job_timestamp(auto_scan) or preferences.last_auto_scan_at

        next_scan_at = None
        if preferences.daily_scan_enabled and last_sync_at is not None:
            next_scan_at = preferences.next_scan_at

        return OverviewResponse(
            total_jobs=stats["total_jobs"],
            new_jobs=stats["new_jobs"],
            high_match_jobs=stats["high_match_jobs"],
            saved_jobs=stats["saved_jobs"],
            high_match_threshold=stats["high_match_threshold"],
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            next_scan_at=next_scan_at,
            integrations=integrations,
            has_mock_data=stats["mock_jobs"] > 0,
            has_active_cv=self.cvs.get_active_for_user(user.id) is not None,
            sync_available=True,
            connected_accounts=connected_accounts,
            active_job_id=active_job.id if active_job else None,
            active_job_kind=active_job.kind if active_job else None,
            worker_hint="python -m app.worker",
            real_jobs=stats["real_jobs"],
            discovered_today=stats["discovered_today"],
            analyzed_jobs=stats["analyzed_jobs"],
            pending_analysis=stats["pending_analysis"],
            failed_analysis=stats["failed_analysis"],
            notified_jobs=stats["notified_jobs"],
            average_score=stats["average_score"],
            last_manual_scan_at=_job_timestamp(manual_scan),
            last_auto_scan_at=auto_scan_at,
            next_auto_scan_at=preferences.next_scan_at,
            auto_scan_enabled=bool(preferences.daily_scan_enabled),
            scan_interval_hours=preferences.scan_interval_hours,
            llm=DeepSeekScoringClient().describe(),
            notifications=NotificationService(self.db).summary(user),
        )


def _job_timestamp(job) -> datetime | None:
    if job is None:
        return None
    return job.finished_at or job.started_at or job.requested_at


def _aggregate_status(accounts: list, provider: str) -> str:
    provider_accounts = [a for a in accounts if a.provider == provider]
    if not provider_accounts:
        return ConnectionStatus.DISCONNECTED.value
    statuses = {a.status for a in provider_accounts}
    for candidate in (
        ConnectionStatus.ERROR.value,
        ConnectionStatus.NEEDS_REAUTH.value,
        ConnectionStatus.CONNECTED.value,
        ConnectionStatus.PENDING.value,
    ):
        if candidate in statuses:
            return candidate
    return ConnectionStatus.DISCONNECTED.value


def _max_dt(values: list[datetime | None]) -> datetime | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return max(
        present,
        key=lambda value: value
        if value.tzinfo is not None
        else value.replace(tzinfo=timezone.utc),
    )
