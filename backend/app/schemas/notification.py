from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: uuid.UUID
    channel: str
    status: str
    message: str | None = None
    error_message: str | None = None
    job_id: uuid.UUID | None = None
    job_match_id: uuid.UUID | None = None
    job_title: str | None = None
    company: str | None = None
    sent_at: datetime | None = None
    created_at: datetime
    is_mock: bool
