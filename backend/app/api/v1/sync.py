from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import SyncJobStatus
from app.schemas.common import Page
from app.schemas.sync import (
    SyncHistoryRead,
    SyncJobProgressResponse,
    SyncJobRead,
    SyncRunRequest,
    SyncRunResponse,
    SyncStatusResponse,
)
from app.services.job_service import JobService
from app.services.sync_job_service import SyncJobService
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post(
    "/run", response_model=SyncRunResponse, status_code=status.HTTP_202_ACCEPTED
)
def run_sync(
    user: CurrentUser, db: DbSession, payload: SyncRunRequest | None = None
) -> SyncRunResponse:
    """Queue a durable scan. The request returns immediately (202) with the job
    id; the worker process does the provider calls and the UI polls progress."""
    service = SyncJobService(db)
    job = service.enqueue(
        user, account_ids=payload.account_ids if payload else None
    )
    db.commit()
    return SyncRunResponse(
        job_id=job.id,
        status=job.status,
        accounts_total=job.accounts_total,
        requested_at=job.requested_at,
        message=(
            "Tarama kuyruğa alındı. İlerlemeyi bu ekrandan takip edebilirsiniz. "
            "İşçi süreci çalışmıyorsa: python -m app.worker"
        ),
    )


@router.get("/jobs", response_model=Page[SyncJobRead])
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    kind: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[SyncJobRead]:
    items, total = SyncJobService(db).list_jobs(
        user, page=page, page_size=page_size, kind=kind
    )
    return Page.build(
        [SyncJobRead.model_validate(job) for job in items], total, page, page_size
    )


@router.get("/jobs/{job_id}", response_model=SyncJobProgressResponse)
def read_job_progress(
    job_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SyncJobProgressResponse:
    progress = SyncJobService(db).progress(user, job_id)
    return SyncJobProgressResponse.model_validate(progress)


@router.post("/jobs/{job_id}/cancel", response_model=SyncJobProgressResponse)
def cancel_job(
    job_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SyncJobProgressResponse:
    SyncJobService(db).cancel(user, job_id)
    db.commit()
    return SyncJobProgressResponse.model_validate(SyncJobService(db).progress(user, job_id))


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
    service = SyncJobService(db)
    active = service.jobs.active_for_user(user.id)
    latest = service.latest(user)
    base = JobService(db).sync_status(user)
    return _status_response(base, active, latest)


def _status_response(base, active, latest) -> SyncStatusResponse:
    terminal = {
        SyncJobStatus.COMPLETED.value,
        SyncJobStatus.PARTIAL_FAILED.value,
        SyncJobStatus.FAILED.value,
        SyncJobStatus.CANCELLED.value,
    }
    last_activity = None
    if latest is not None:
        last_activity = latest.finished_at or latest.started_at or latest.requested_at

    return base.model_copy(
        update={
            "available": True,
            "running": active is not None,
            "active_job_id": active.id if active else None,
            "active_job_kind": active.kind if active else None,
            "last_sync_at": last_activity or base.last_sync_at,
            "message": (
                "Tarama sürüyor; ilerleme canlı güncelleniyor."
                if active is not None
                else (
                    "Son tarama tamamlandı."
                    if latest is not None and latest.status in terminal
                    else "Manuel tarama hazır. Kuyruğu işlemek için worker süreci çalışmalı."
                )
            ),
            "worker_hint": "python -m app.worker",
        }
    )
