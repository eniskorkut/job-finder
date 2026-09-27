from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import errors
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.integrations import NotificationRepository, SyncHistoryRepository
from app.repositories.jobs import MailAccountRepository
from app.schemas.common import Page
from app.schemas.notification import NotificationRead
from app.schemas.sync import SyncHistoryRead


class SyncService:
    """Phase 1: read-only scan history + explicit "not implemented" trigger."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.history = SyncHistoryRepository(db)
        self.accounts = MailAccountRepository(db)
        self.cvs = CVRepository(db)

    def list_history(self, user: User, *, page: int = 1, page_size: int = 20) -> Page[SyncHistoryRead]:
        rows, total = self.history.list_for_user(
            user.id, offset=(page - 1) * page_size, limit=page_size
        )
        items = []
        for record, account_email in rows:
            item = SyncHistoryRead.model_validate(record)
            item.account_email = account_email
            items.append(item)
        return Page.build(items, total, page, page_size)

    def trigger(self, user: User) -> None:
        """Scanning depends on phase 2 (mail) and phase 3 (LLM + Telegram)."""
        accounts = self.accounts.list_for_user(user.id)
        raise errors.not_implemented(
            "phase-2",
            "Otomatik tarama henüz geliştirilmedi. "
            f"(Bu hesapta tanımlı e-posta hesabı sayısı: {len(accounts)}). "
            "2. aşamada Gmail/Hotmail okuma, 3. aşamada DeepSeek skorlaması eklenecek.",
        )


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.notifications = NotificationRepository(db)

    def list(self, user: User, *, page: int = 1, page_size: int = 20) -> Page[NotificationRead]:
        records, total = self.notifications.list_for_user(
            user.id, offset=(page - 1) * page_size, limit=page_size
        )
        items = []
        for record in records:
            item = NotificationRead.model_validate(record)
            item.job_title = record.job.title if record.job else None
            item.company = record.job.company if record.job else None
            items.append(item)
        return Page.build(items, total, page, page_size)

    def send_test(self, user: User) -> None:
        raise errors.not_implemented(
            "phase-3", "Telegram bildirim gönderimi 3. aşamada eklenecek."
        )
