from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class MailAccountRead(ORMModel):
    id: uuid.UUID
    provider: str
    email_address: str
    display_name: str | None = None
    status: str
    last_synced_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime


class IntegrationRead(ORMModel):
    provider: str
    label: str
    description: str
    category: str
    status: str
    available: bool
    unavailable_reason: str | None = None
    phase: str
    accounts: list[MailAccountRead] = []
    detail: str | None = None
    last_synced_at: datetime | None = None


class IntegrationsResponse(ORMModel):
    integrations: list[IntegrationRead]
    deepseek: dict
