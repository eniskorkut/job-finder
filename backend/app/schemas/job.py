from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MatchStatus
from app.schemas.common import ORMModel


class JobMatchRead(ORMModel):
    id: uuid.UUID
    score: int | None = None
    rationale: str | None = None
    matched_skills: list[str]
    missing_skills: list[str]
    model: str | None = None
    status: str
    is_mock: bool
    notified_at: datetime | None = None
    updated_at: datetime


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
    match: JobMatchRead | None = None


class JobDetail(JobRead):
    description: str | None = None
    mail_account_email: str | None = None


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


class JobFilterOptions(ORMModel):
    sources: list[str]
    locations: list[str]
    companies: list[str]
    work_modes: list[str]
