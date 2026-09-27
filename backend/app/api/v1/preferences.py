from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.preferences import PreferencesRead, PreferencesUpdate
from app.services.preference_service import PreferenceService

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesRead)
def read_preferences(user: CurrentUser, db: DbSession) -> PreferencesRead:
    return PreferencesRead.model_validate(PreferenceService(db).get(user))


@router.put("", response_model=PreferencesRead)
def update_preferences(
    payload: PreferencesUpdate, user: CurrentUser, db: DbSession
) -> PreferencesRead:
    preference = PreferenceService(db).update(user, payload)
    db.commit()
    return PreferencesRead.model_validate(preference)
