from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.auth import SessionUserRead
from app.schemas.common import ORMModel


class UserRead(SessionUserRead):
    updated_at: datetime | None = None


class UserUpdateRequest(ORMModel):
    full_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None


class IntegrationStatusSummary(ORMModel):
    provider: str
    label: str
    status: str
    available: bool
    account_count: int = 0
    detail: str | None = None
    last_synced_at: datetime | None = None


class OverviewResponse(ORMModel):
    total_jobs: int
    new_jobs: int
    high_match_jobs: int
    saved_jobs: int
    high_match_threshold: int
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    next_scan_at: datetime | None = None
    integrations: list[IntegrationStatusSummary]
    has_mock_data: bool
    has_active_cv: bool
    sync_available: bool
    connected_accounts: int = 0
    active_job_id: uuid.UUID | None = None
    worker_hint: str | None = None
