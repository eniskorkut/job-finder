from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MatchStatus
from app.schemas.common import ORMModel


class DimensionMatchRead(BaseModel):
    status: str = "unknown"
    reason: str = ""


class JobMatchRead(ORMModel):
    id: uuid.UUID
    score: int | None = None
    confidence: int | None = None
    rationale: str | None = None
    matched_skills: list[str]
    missing_skills: list[str]
    model: str | None = None
    status: str
    is_mock: bool
    notified_at: datetime | None = None
    updated_at: datetime

    # phase 3 analysis detail
    analysis_status: str = "pending"
    analysis_error: str | None = None
    analysis_attempts: int = 0
    analyzed_at: datetime | None = None
    cv_checksum: str | None = None
    prompt_version: str | None = None
    insufficient_information: bool = False
    experience_match: str = "unknown"
    location_match: str = "unknown"
    work_mode_match: str = "unknown"
    title_match: str = "unknown"
    match_details: dict = Field(default_factory=dict)


class JobSourceRead(ORMModel):
    provider: str
    provider_message_id: str
    subject: str | None = None
    sender: str | None = None
    received_at: datetime | None = None
    discovered_at: datetime
    account_email: str | None = None


class JobRead(ORMModel):
    id: uuid.UUID
    title: str
    company: str
    location: str | None = None
    work_mode: str
    employment_type: str | None = None
    seniority: str | None = None
    salary_text: str | None = None
    url: str | None = None
    source: str
    is_mock: bool
    posted_at: datetime | None = None
    discovered_at: datetime
    description_status: str = "ok"
    match: JobMatchRead | None = None


class JobDetail(JobRead):
    description: str | None = None
    mail_account_email: str | None = None
    sources: list[JobSourceRead] = Field(default_factory=list)
    analysis_cv: dict | None = None


class JobMatchUpdate(BaseModel):
    status: MatchStatus


class JobStats(ORMModel):
    total_jobs: int
    new_jobs: int
    high_match_jobs: int
    saved_jobs: int
    dismissed_jobs: int
    mock_jobs: int
    high_match_threshold: int
    average_score: float | None = None
    jobs_by_source: dict[str, int] = Field(default_factory=dict)
    top_companies: list[dict] = Field(default_factory=list)
    # phase 3
    real_jobs: int = 0
    discovered_today: int = 0
    analyzed_jobs: int = 0
    pending_analysis: int = 0
    failed_analysis: int = 0
    notified_jobs: int = 0
    average_confidence: float | None = None


class JobFilterOptions(ORMModel):
    sources: list[str]
    locations: list[str]
    companies: list[str]
    work_modes: list[str]
    analysis_statuses: list[str] = Field(default_factory=list)


class ReanalyzeResponse(BaseModel):
    job_id: uuid.UUID
    total: int
    status: str
    message: str
