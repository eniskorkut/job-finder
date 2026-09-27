from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.preferences import UserPreference
from app.models.user import User
from app.repositories.preferences import PreferenceRepository
from app.schemas.preferences import PreferencesUpdate


class PreferenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.preferences = PreferenceRepository(db)

    def get(self, user: User) -> UserPreference:
        return self.preferences.get_or_create(user)

    def update(self, user: User, payload: PreferencesUpdate) -> UserPreference:
        preference = self.preferences.get_or_create(user)
        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in data.items():
            setattr(preference, field, value)
        self.db.flush()
        return preference
