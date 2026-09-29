from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import JobSource, MatchStatus, WorkMode


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A job posting discovered for one specific user.

    Jobs are stored per user (not shared) so every query can be scoped by
    ``user_id`` and the same external posting can exist for two users with
    independent match results.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "external_id", name="uq_jobs_owner_source_external"
        ),
        UniqueConstraint(
            "user_id", "fingerprint_hash", name="uq_jobs_owner_fingerprint"
        ),
        Index("ix_jobs_user_discovered", "user_id", "discovered_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mail_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mail_accounts.id", ondelete="SET NULL")
    )

    source: Mapped[str] = mapped_column(String(20), default=JobSource.MOCK.value)
    external_id: Mapped[str | None] = mapped_column(String(255), default=None)

    title: Mapped[str] = mapped_column(String(300), index=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    work_mode: Mapped[str] = mapped_column(String(20), default=WorkMode.UNKNOWN.value)
    employment_type: Mapped[str | None] = mapped_column(String(60), default=None)
    seniority: Mapped[str | None] = mapped_column(String(60), default=None)
    salary_text: Mapped[str | None] = mapped_column(String(160), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    url: Mapped[str | None] = mapped_column(String(600), default=None)

    # Deduplication keys. Priority: LinkedIn job id (external_id) -> normalized
    # URL -> fingerprint of title/company/location. Only ever scoped per user.
    url_normalized: Mapped[str | None] = mapped_column(String(600), default=None)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    description_status: Mapped[str] = mapped_column(
        String(30), default="ok", server_default="ok"
    )

    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Phase 4: Job Discovery, Enrichment & Freshness
    linkedin_url: Mapped[str | None] = mapped_column(Text, default=None)
    company_job_url: Mapped[str | None] = mapped_column(Text, default=None)
    canonical_url: Mapped[str | None] = mapped_column(Text, default=None)
    application_url: Mapped[str | None] = mapped_column(Text, default=None)
    source_url: Mapped[str | None] = mapped_column(Text, default=None)

    email_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    valid_through: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    posted_at_source: Mapped[str | None] = mapped_column(String(30), default=None)
    posted_at_confidence: Mapped[str | None] = mapped_column(String(20), default=None)

    freshness_status: Mapped[str] = mapped_column(
        String(20), default="fresh", server_default="fresh", index=True
    )
    availability_status: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    enrichment_status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending", index=True
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), default=None, index=True
    )

    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, default=None)

    user: Mapped["User"] = relationship(back_populates="jobs")  # noqa: F821
    match: Mapped["JobMatch | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    web_sources: Mapped[list["JobWebSource"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobWebSource(UUIDPrimaryKeyMixin, Base):
    """Web source discovered for a job (ATS, official site, etc.)."""

    __tablename__ = "job_web_sources"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "normalized_url", name="uq_job_web_sources_job_normalized_url"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )

    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(30))
    trust_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    match_confidence: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none"
    )
    title: Mapped[str | None] = mapped_column(Text, default=None)
    snippet: Mapped[str | None] = mapped_column(Text, default=None)
    http_status: Mapped[int | None] = mapped_column(Integer, default=None)
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    selected_as_canonical: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    job: Mapped["Job"] = relationship(back_populates="web_sources")


class JobMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """CV <-> job scoring result, owned by the same user as the job."""

    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_matches_owner_job"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    cv_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cvs.id", ondelete="SET NULL")
    )

    score: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    rationale: Mapped[str | None] = mapped_column(Text, default=None)
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    model: Mapped[str | None] = mapped_column(String(80), default=None)

    # Phase 3 analysis detail. ``score`` is a CV <-> job requirement fit, never
    # a hiring probability; the UI states that explicitly.
    confidence: Mapped[int | None] = mapped_column(Integer, default=None)
    experience_match: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    location_match: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    work_mode_match: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    title_match: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    match_details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    insufficient_information: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )

    analysis_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", index=True
    )
    analysis_error: Mapped[str | None] = mapped_column(Text, default=None)
    analysis_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    cv_checksum: Mapped[str | None] = mapped_column(String(64), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(40), default=None)

    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.NEW.value)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    job: Mapped[Job] = relationship(back_populates="match")
