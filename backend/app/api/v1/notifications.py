from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.notification import (
    NotificationDispatchResponse,
    NotificationRead,
    NotificationSummary,
)
from app.schemas.integration import TelegramTestResponse
from app.services.notification_service import NotificationService
from app.services.sync_service import NotificationService as NotificationListService
from app.services.telegram_service import TelegramConfigService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationRead]:
    return NotificationListService(db).list(user, page=page, page_size=page_size)


@router.get("/summary", response_model=NotificationSummary)
def notification_summary(user: CurrentUser, db: DbSession) -> NotificationSummary:
    """Per-user delivery counters. Another user's numbers are unreachable."""
    return NotificationSummary.model_validate(NotificationService(db).summary(user))


@router.post(
    "/dispatch", response_model=NotificationDispatchResponse, status_code=status.HTTP_202_ACCEPTED
)
def dispatch_notifications(
    user: CurrentUser, db: DbSession
) -> NotificationDispatchResponse:
    """Queue a delivery attempt for every eligible, not yet delivered match."""
    service = NotificationService(db)
    job = service.enqueue(user)
    db.commit()
    if job is None:
        return NotificationDispatchResponse(
            queued=False,
            total=0,
            message=(
                "Gönderilecek yeni bildirim yok. Eşik üstü ve henüz bildirilmemiş "
                "eşleşmeler buraya düşer."
            ),
        )
    total = int((job.progress or {}).get("total", 0))
    return NotificationDispatchResponse(
        queued=True,
        job_id=job.id,
        total=total,
        message=f"{total} bildirim kuyruğa alındı.",
    )


@router.post("/test", response_model=TelegramTestResponse)
async def send_test_notification(
    user: CurrentUser, db: DbSession
) -> TelegramTestResponse:
    """Send a Telegram test message through the user's own bot."""
    service = TelegramConfigService(db)
    outcome = await service.send_test(user)
    db.commit()
    return TelegramTestResponse.model_validate(outcome)
