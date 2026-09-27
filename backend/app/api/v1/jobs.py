from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models.enums import MatchStatus, WorkMode
from app.schemas.common import Page
from app.schemas.job import (
    JobDetail,
    JobFilterOptions,
    JobMatchUpdate,
    JobRead,
    JobStats,
)
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobRead])
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    search: str | None = Query(default=None, max_length=200),
    company: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    work_mode: WorkMode | None = None,
    source: str | None = Query(default=None, max_length=20),
    status: MatchStatus | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
    sort: str = Query(default="recent"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[JobRead]:
    items, total = JobService(db).list(
        user,
        search=search,
        company=company,
        location=location,
        work_mode=work_mode.value if work_mode else None,
        source=source,
        status=status.value if status else None,
        min_score=min_score,
        max_score=max_score,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page.build(items, total, page, page_size)


@router.get("/stats", response_model=JobStats)
def read_job_stats(user: CurrentUser, db: DbSession) -> JobStats:
    return JobService(db).stats(user)


@router.get("/filters", response_model=JobFilterOptions)
def read_filter_options(user: CurrentUser, db: DbSession) -> JobFilterOptions:
    return JobService(db).filter_options(user)


@router.get("/{job_id}", response_model=JobDetail)
def read_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobDetail:
    service = JobService(db)
    detail = service.get_detail(user, job_id)
    service.mark_viewed(user, job_id)
    db.commit()
    return detail


@router.patch("/{job_id}", response_model=JobRead)
def update_job_match(
    job_id: uuid.UUID, payload: JobMatchUpdate, user: CurrentUser, db: DbSession
) -> JobRead:
    job = JobService(db).update_match_status(user, job_id, payload.status)
    db.commit()
    return JobRead.model_validate(job)
