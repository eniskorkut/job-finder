from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


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
    active_cv: str | None = None
    connected_accounts: int = 0
