from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.notification import NotificationRead
from app.services.sync_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationRead]:
    return NotificationService(db).list(user, page=page, page_size=page_size)


@router.post("/test")
def send_test_notification(user: CurrentUser, db: DbSession) -> dict:
    """Phase 3 stub - returns 501, never a fake success."""
    NotificationService(db).send_test(user)
