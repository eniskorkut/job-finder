from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: uuid.UUID
    channel: str
    status: str
    message: str | None = None
    error_message: str | None = None
    error_class: str | None = None
    attempts: int = 0
    provider_message_id: str | None = None
    job_id: uuid.UUID | None = None
    job_match_id: uuid.UUID | None = None
    job_title: str | None = None
    company: str | None = None
    score: int | None = None
    sent_at: datetime | None = None
    created_at: datetime
    is_mock: bool


class NotificationSummary(BaseModel):
    sent: int
    failed: int
    skipped: int
    pending: int
    threshold: int
    enabled: bool
    telegram_ready: bool
    last_sent_at: datetime | None = None


class NotificationDispatchResponse(BaseModel):
    queued: bool
    job_id: uuid.UUID | None = None
    total: int = 0
    message: str
