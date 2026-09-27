from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.sync import SyncHistoryRead, SyncStatusResponse
from app.services.job_service import JobService
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/history", response_model=Page[SyncHistoryRead])
def read_history(
    user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[SyncHistoryRead]:
    return SyncService(db).list_history(user, page=page, page_size=page_size)


@router.get("/status", response_model=SyncStatusResponse)
def read_status(user: CurrentUser, db: DbSession) -> SyncStatusResponse:
    return JobService(db).sync_status(user)


@router.post("/run", response_model=SyncStatusResponse)
def run_sync(user: CurrentUser, db: DbSession) -> SyncStatusResponse:
    """Explicitly unimplemented until phases 2-3 exist."""
    SyncService(db).trigger(user)
