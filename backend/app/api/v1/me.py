from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.user import OverviewResponse, UserRead, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserRead)
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("", response_model=UserRead)
def update_me(payload: UserUpdateRequest, user: CurrentUser, db: DbSession) -> UserRead:
    updated = UserService(db).update_profile(
        user, full_name=payload.full_name, email=str(payload.email) if payload.email else None
    )
    db.commit()
    return UserRead.model_validate(updated)


@router.get("/overview", response_model=OverviewResponse)
def read_overview(user: CurrentUser, db: DbSession) -> OverviewResponse:
    return UserService(db).overview(user)
