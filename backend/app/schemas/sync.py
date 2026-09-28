from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SyncJobRead(ORMModel):
    id: uuid.UUID
    kind: str = "mail_scan"
    status: str
    trigger: str
    accounts_total: int
    accounts_processed: int
    messages_scanned: int
    jobs_found: int
    jobs_new: int
    jobs_duplicate: int
    messages_skipped: int
    errors_count: int
    attempt: int
    cancel_requested: bool
    payload: dict = Field(default_factory=dict)
    progress: dict = Field(default_factory=dict)
    error_message: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next_attempt_at: datetime | None = None


class SyncAccountProgress(ORMModel):
    id: uuid.UUID
    mail_account_id: uuid.UUID
    email_address: str | None = None
    provider: str | None = None
    status: str
    messages_scanned: int
    jobs_found: int
    jobs_new: int
    jobs_duplicate: int
    messages_skipped: int
    error_class: str
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScoringItemProgress(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str | None = None
    company: str | None = None
    status: str
    attempt: int
    error_class: str | None = None
    error_message: str | None = None
    match_id: uuid.UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SyncJobProgressResponse(BaseModel):
    job: SyncJobRead
    accounts: list[SyncAccountProgress] = Field(default_factory=list)
    items: list[ScoringItemProgress] = Field(default_factory=list)


class SyncRunResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    kind: str = "mail_scan"
    accounts_total: int = 0
    total: int = 0
    requested_at: datetime
    message: str


class SyncRunRequest(BaseModel):
    account_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class ReanalyzeRequest(BaseModel):
    """Manual CV reanalysis. Bounded: all jobs, the last N days, or one job."""

    days: int | None = Field(default=None, ge=1, le=365)
    job_id: uuid.UUID | None = None
    force: bool = False


class SyncHistoryRead(ORMModel):
    id: uuid.UUID
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    jobs_found: int
    jobs_new: int
    matches_created: int
    error_message: str | None = None
    is_mock: bool
    account_email: str | None = None


class SyncStatusResponse(BaseModel):
    available: bool
    phase: str
    running: bool = False
    message: str
    last_sync_at: datetime | None = None
    next_scan_at: datetime | None = None
    last_auto_scan_at: datetime | None = None
    next_auto_scan_at: datetime | None = None
    active_cv: str | None = None
    connected_accounts: int = 0
    active_job_id: uuid.UUID | None = None
    active_job_kind: str | None = None
    worker_hint: str | None = None
    scheduler_enabled: bool = True
    llm_configured: bool = False
