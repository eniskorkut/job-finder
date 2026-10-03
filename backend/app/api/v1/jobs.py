from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import MatchStatus, SyncTrigger, WorkMode
from app.schemas.common import Page
from app.schemas.job import (
    JobDetail,
    JobFilterOptions,
    JobMatchUpdate,
    JobRead,
    JobStats,
    ReanalyzeResponse,
    RefreshJobResponse,
)
from app.services.job_service import JobService
from app.services.scoring_service import MODE_NEW, MODE_REANALYZE, ScoringService
from app.schemas.sync import ReanalyzeRequest

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobRead])
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    response: Response,
    search: str | None = Query(default=None, max_length=200),
    company: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    work_mode: WorkMode | None = None,
    source: str | None = Query(default=None, max_length=20),
    status: MatchStatus | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
    analysis_status: str | None = Query(default=None, max_length=20),
    notification: str | None = Query(default=None, pattern="^(sent|pending)$"),
    freshness_status: str | None = Query(default=None, max_length=20),
    enrichment_status: str | None = Query(default=None, max_length=20),
    sort: str = Query(default="recent"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[JobRead]:
    response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
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
        analysis_status=analysis_status,
        notification=notification,
        freshness_status=freshness_status,
        enrichment_status=enrichment_status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page.build(items, total, page, page_size)


@router.get("/stats", response_model=JobStats)
def read_job_stats(user: CurrentUser, db: DbSession, response: Response) -> JobStats:
    response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
    return JobService(db).stats(user)


@router.get("/filters", response_model=JobFilterOptions)
def read_filter_options(user: CurrentUser, db: DbSession, response: Response) -> JobFilterOptions:
    response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
    return JobService(db).filter_options(user)


# --- manual reanalysis (durable, always 202) ---------------------------
@router.post(
    "/reanalyze", response_model=ReanalyzeResponse, status_code=status.HTTP_202_ACCEPTED
)
def reanalyze_jobs(
    payload: ReanalyzeRequest, user: CurrentUser, db: DbSession
) -> ReanalyzeResponse:
    """Re-run the CV <-> job analysis for stale or failed postings.

    Long work never happens inside the request: a durable scoring job is
    queued and the worker analyses it with bounded concurrency.
    """
    service = ScoringService(db)
    job, total = service.enqueue(
        user,
        mode=MODE_REANALYZE if (payload.days or payload.job_id) else MODE_NEW,
        days=payload.days,
        job_id=payload.job_id,
        force=payload.force,
        trigger=SyncTrigger.MANUAL,
    )
    db.commit()
    return ReanalyzeResponse(
        job_id=job.id,
        total=total,
        status=job.status,
        message=(
            f"{total} ilan analiz kuyruğuna alındı. İlerlemeyi Tarama Geçmişi ekranından "
            "izleyebilirsiniz."
        ),
    )


@router.post(
    "/{job_id}/reanalyze",
    response_model=ReanalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reanalyze_single_job(
    job_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ReanalyzeResponse:
    """Force a fresh analysis for one posting (detail screen action)."""
    service = ScoringService(db)
    service.get_job_or_404(user, job_id)
    job, total = service.enqueue(
        user, mode=MODE_REANALYZE, job_id=job_id, force=True, trigger=SyncTrigger.MANUAL
    )
    db.commit()
    return ReanalyzeResponse(
        job_id=job.id,
        total=total,
        status=job.status,
        message="İlan yeniden analiz kuyruğuna alındı.",
    )


@router.post(
    "/{job_id}/refresh",
    response_model=RefreshJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def refresh_single_job(
    job_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> RefreshJobResponse:
    """Trigger on-demand web discovery and enrichment refresh for a single job posting."""
    from app.services.enrichment_service import EnrichmentService

    job_service = JobService(db)
    job_service.get(user, job_id)
    enrich_service = EnrichmentService(db)
    sync_job, _ = enrich_service.enqueue(
        user, job_id=job_id, force=True, trigger=SyncTrigger.MANUAL
    )
    db.commit()
    return RefreshJobResponse(
        job_id=job_id,
        sync_job_id=sync_job.id,
        status=sync_job.status,
        message="İlan zenginleştirme ve tazelik kontrolü kuyruğa alındı.",
    )


@router.get("/{job_id}", response_model=JobDetail)
def read_job(
    job_id: uuid.UUID, user: CurrentUser, db: DbSession, response: Response
) -> JobDetail:
    response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
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
