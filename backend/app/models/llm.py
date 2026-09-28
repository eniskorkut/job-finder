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


class CVProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured CV profile, cached per user until the CV checksum changes.

    Scoring sends this profile plus a bounded CV excerpt instead of the whole
    document on every call.
    """

    __tablename__ = "cv_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_cv_profiles_owner"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    cv_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cvs.id", ondelete="SET NULL")
    )
    cv_checksum: Mapped[str] = mapped_column(String(64), index=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    model: Mapped[str | None] = mapped_column(String(80), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(40), default=None)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped["User"] = relationship()  # noqa: F821


class LlmUsage(UUIDPrimaryKeyMixin, Base):
    """Per-user LLM call metrics. The shared API key never appears here."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        Index("ix_llm_usage_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )

    purpose: Mapped[str] = mapped_column(String(20), default="scoring")
    status: Mapped[str] = mapped_column(String(20), default="success")
    model: Mapped[str | None] = mapped_column(String(80), default=None)

    prompt_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    total_tokens: Mapped[int | None] = mapped_column(Integer, default=None)

    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    error_class: Mapped[str | None] = mapped_column(String(20), default=None)
    error_message: Mapped[str | None] = mapped_column(String(300), default=None)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
