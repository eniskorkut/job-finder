from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.security import hash_token
from app.models.user import UserSession
from app.repositories.base import Repository


class SessionRepository(Repository[UserSession]):
    model = UserSession

    def get_by_token(self, token: str) -> UserSession | None:
        stmt = select(UserSession).where(UserSession.token_hash == hash_token(token))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_active_by_token(self, token: str, now: datetime | None = None) -> UserSession | None:
        session = self.get_by_token(token)
        if session is None:
            return None
        moment = now or datetime.now(timezone.utc)
        if session.revoked_at is not None:
            return None
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= moment:
            return None
        return session

    def list_for_user(self, user_id: uuid.UUID) -> list[UserSession]:
        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def revoke(self, session: UserSession) -> None:
        session.revoked_at = datetime.now(timezone.utc)
        self.db.flush()

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        self.db.execute(stmt)
        self.db.flush()

    def touch(self, session: UserSession) -> None:
        session.last_seen_at = datetime.now(timezone.utc)
        self.db.flush()
