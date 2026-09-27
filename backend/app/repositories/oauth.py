from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import hash_token
from app.models.oauth import OAuthState
from app.repositories.base import Repository


class OAuthStateRepository(Repository[OAuthState]):
    model = OAuthState

    def get_by_state(self, state: str) -> OAuthState | None:
        stmt = select(OAuthState).where(OAuthState.state_hash == hash_token(state))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_valid(self, state: str, now: datetime | None = None) -> OAuthState | None:
        record = self.get_by_state(state)
        if record is None or record.consumed_at is not None:
            return None
        moment = now or datetime.now(timezone.utc)
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= moment:
            return None
        return record

    def consume(self, record: OAuthState) -> None:
        record.consumed_at = datetime.now(timezone.utc)
        self.db.flush()

    def get_for_user(self, user_id: uuid.UUID, state_id: uuid.UUID) -> OAuthState | None:
        stmt = select(OAuthState).where(
            OAuthState.id == state_id, OAuthState.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_pending_for_session(
        self, session_id: uuid.UUID, provider: str
    ) -> list[OAuthState]:
        stmt = select(OAuthState).where(
            OAuthState.session_id == session_id,
            OAuthState.provider == provider,
            OAuthState.consumed_at.is_(None),
        )
        return list(self.db.execute(stmt).scalars())
