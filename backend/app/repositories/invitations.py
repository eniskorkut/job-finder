from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.security import hash_token
from app.models.user import UserInvitation
from app.repositories.base import Repository


class InvitationRepository(Repository[UserInvitation]):
    model = UserInvitation

    def get_by_token(self, token: str) -> UserInvitation | None:
        stmt = select(UserInvitation).where(
            UserInvitation.token_hash == hash_token(token)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_for_user(self, invitation_id: uuid.UUID) -> UserInvitation | None:
        return self.db.get(UserInvitation, invitation_id)

    def list_all(self) -> list[UserInvitation]:
        stmt = select(UserInvitation).order_by(UserInvitation.created_at.desc())
        return list(self.db.execute(stmt).scalars())

    def list_pending(self, now: datetime | None = None) -> list[UserInvitation]:
        moment = now or datetime.now(timezone.utc)
        stmt = (
            select(UserInvitation)
            .where(
                UserInvitation.used_at.is_(None),
                UserInvitation.expires_at > moment,
            )
            .order_by(UserInvitation.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def delete_expired(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(timezone.utc)
        stmt = delete(UserInvitation).where(
            UserInvitation.used_at.is_(None),
            UserInvitation.expires_at <= moment,
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return int(result.rowcount or 0)
