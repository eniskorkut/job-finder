from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class CVRead(ORMModel):
    id: uuid.UUID
    filename: str
    content_type: str | None = None
    size_bytes: int
    checksum: str | None = None
    summary: str | None = None
    has_extracted_text: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CVUpdate(ORMModel):
    is_active: bool | None = None
    summary: str | None = Field(default=None, max_length=2000)
