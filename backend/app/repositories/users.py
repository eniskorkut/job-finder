from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from app.models.user import User
from app.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(func.lower(User.username) == username.strip().lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_identifier(self, identifier: str) -> User | None:
        value = identifier.strip().lower()
        stmt = select(User).where(
            or_(func.lower(User.username) == value, func.lower(User.email) == value)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def username_exists(self, username: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(User.id).where(func.lower(User.username) == username.strip().lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.execute(stmt).first() is not None

    def email_exists(self, email: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(User.id).where(func.lower(User.email) == email.strip().lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.execute(stmt).first() is not None

    def list_all(self) -> list[User]:
        return list(self.db.execute(select(User).order_by(User.created_at)).scalars())

    def count(self, *criteria) -> int:  # type: ignore[override]
        return super().count(*criteria)

    def touch_last_login(self, user: User, when: datetime | None = None) -> None:
        user.last_login_at = when or datetime.now(timezone.utc)
        self.db.flush()
