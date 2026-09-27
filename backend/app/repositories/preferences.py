from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.preferences import UserPreference
from app.models.user import User
from app.repositories.base import Repository


class PreferenceRepository(Repository[UserPreference]):
    model = UserPreference

    def get_for_user(self, user_id: uuid.UUID) -> UserPreference | None:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(self, user: User) -> UserPreference:
        existing = self.get_for_user(user.id)
        if existing is not None:
            return existing
        preference = UserPreference(user_id=user.id)
        self.db.add(preference)
        self.db.flush()
        return preference
