from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.mail_account import MailAccount
from app.models.notification import NotificationHistory
from app.models.sync import SyncHistory
from app.models.telegram import TelegramIntegration
from app.repositories.base import Repository


class SyncHistoryRepository(Repository[SyncHistory]):
    model = SyncHistory

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 20
    ) -> tuple[list[tuple[SyncHistory, str | None]], int]:
        stmt = (
            select(SyncHistory, MailAccount.email_address)
            .outerjoin(MailAccount, MailAccount.id == SyncHistory.mail_account_id)
            .where(SyncHistory.user_id == user_id)
            .order_by(SyncHistory.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = [tuple(row) for row in self.db.execute(stmt).all()]
        total = self.count(SyncHistory.user_id == user_id)
        return rows, total  # type: ignore[return-value]

    def latest_for_user(self, user_id: uuid.UUID) -> SyncHistory | None:
        stmt = (
            select(SyncHistory)
            .where(SyncHistory.user_id == user_id)
            .order_by(SyncHistory.started_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def has_mock_for_user(self, user_id: uuid.UUID) -> bool:
        return (
            self.db.execute(
                select(func.count(SyncHistory.id)).where(
                    SyncHistory.user_id == user_id, SyncHistory.is_mock.is_(True)
                )
            ).scalar_one()
            > 0
        )


class NotificationRepository(Repository[NotificationHistory]):
    model = NotificationHistory

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 20
    ) -> tuple[list[NotificationHistory], int]:
        stmt = (
            select(NotificationHistory)
            .where(NotificationHistory.user_id == user_id)
            .order_by(NotificationHistory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.execute(stmt).scalars())
        total = self.count(NotificationHistory.user_id == user_id)
        return items, total


class TelegramRepository(Repository[TelegramIntegration]):
    model = TelegramIntegration

    def get_for_user(self, user_id: uuid.UUID) -> TelegramIntegration | None:
        stmt = select(TelegramIntegration).where(TelegramIntegration.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(self, user_id: uuid.UUID) -> TelegramIntegration:
        existing = self.get_for_user(user_id)
        if existing is not None:
            return existing
        integration = TelegramIntegration(user_id=user_id)
        self.db.add(integration)
        self.db.flush()
        return integration
