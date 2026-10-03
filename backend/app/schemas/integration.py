from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class MailAccountRead(ORMModel):
    id: uuid.UUID
    provider: str
    email_address: str
    display_name: str | None = None
    status: str
    filters: dict = Field(default_factory=dict)
    initial_sync_completed: bool = False
    last_synced_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime


class GuideStepRead(BaseModel):
    step_number: int
    title: str
    description: str
    action_url: str | None = None
    action_label: str | None = None
    copyable_text: str | None = None
    warning: str | None = None


class GuideFAQRead(BaseModel):
    question: str
    answer: str


class GuideTroubleshootingRead(BaseModel):
    error_code: str
    title: str
    cause: str
    solution: str


class OfficialLinkRead(BaseModel):
    label: str
    url: str


class OAuthClientRead(ORMModel):
    provider: str
    configured: bool
    client_id: str | None = None
    client_secret_hint: str | None = None
    tenant: str | None = None
    redirect_uri: str
    scopes: list[str]
    title: str
    steps: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    estimated_minutes: int = 5
    prerequisites: list[str] = Field(default_factory=list)
    structured_steps: list[GuideStepRead] = Field(default_factory=list)
    faq: list[GuideFAQRead] = Field(default_factory=list)
    troubleshooting: list[GuideTroubleshootingRead] = Field(default_factory=list)
    official_links: list[OfficialLinkRead] = Field(default_factory=list)
    updated_at: datetime | None = None


class OAuthClientSaveRequest(BaseModel):
    client_id: str = Field(min_length=8, max_length=255)
    client_secret: str | None = Field(default=None, max_length=400)
    tenant: str | None = Field(default=None, max_length=120)

    @field_validator("client_id")
    @classmethod
    def _strip_client_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("client_secret")
    @classmethod
    def _strip_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tenant")
    @classmethod
    def _strip_tenant(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class MailAccountUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    senders: list[str] | None = Field(default=None, max_length=25)
    subjects: list[str] | None = Field(default=None, max_length=25)
    reset_cursor: bool = False

    @field_validator("senders", "subjects")
    @classmethod
    def _clean_terms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [" ".join(item.split())[:120] for item in value]
        return [item for item in cleaned if item]


class ConnectResponse(BaseModel):
    provider: str
    authorization_url: str
    redirect_uri: str
    expires_at: datetime
    account_id: str | None = None


class AccountTestResponse(BaseModel):
    ok: bool
    status: str
    message: str


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
    oauth_client: OAuthClientRead | None = None
    capabilities: dict = Field(default_factory=dict)


class IntegrationsResponse(ORMModel):
    integrations: list[IntegrationRead]
    deepseek: dict
    web_search: dict = Field(default_factory=dict)


class TelegramConfigRequest(BaseModel):
    bot_token: str | None = Field(default=None, max_length=200)
    chat_id: str | None = Field(default=None, max_length=64)


class TelegramChatCandidate(BaseModel):
    chat_id: str
    type: str | None = None
    title: str | None = None
    username: str | None = None
    last_message_at: int | None = None


class TelegramDetectResponse(BaseModel):
    bot_username: str | None = None
    candidates: list[TelegramChatCandidate] = Field(default_factory=list)
    suggested_chat_id: str | None = None
    requires_manual_choice: bool = False
    message: str


class TelegramTestResponse(BaseModel):
    ok: bool
    message: str
    status: str
    message_id: int | None = None


# --- Custom Sites and ATS Crawler ---
class CrawlSiteRequest(BaseModel):
    url: str = Field(min_length=3, max_length=1000)


class CrawlJobItem(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    source: str
    is_new: bool


class CrawlSiteResponse(BaseModel):
    success: bool
    url: str
    jobs_found: int
    jobs_created: int
    jobs: list[CrawlJobItem] = Field(default_factory=list)
    message: str


class CrawlJobEnqueuedResponse(BaseModel):
    job_id: uuid.UUID
    status: str = "queued"
    url: str
    message: str


class VerifySitesRequest(BaseModel):
    sites: list[str] = Field(default_factory=list, max_length=20)


class SiteVerificationItem(BaseModel):
    site: str
    status: str
    status_code: int | None = None
    jobs_found: int = 0
    message: str | None = None


class VerifySitesResponse(BaseModel):
    success: bool
    total_checked: int
    active_sites: int
    results: list[SiteVerificationItem]
    message: str
