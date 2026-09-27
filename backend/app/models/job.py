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

    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, default=None)

    user: Mapped["User"] = relationship(back_populates="jobs")  # noqa: F821
    match: Mapped["JobMatch | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


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

    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.NEW.value)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    job: Mapped[Job] = relationship(back_populates="match")
