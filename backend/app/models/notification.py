from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import NotificationChannel, NotificationStatus


class NotificationHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notification_history"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_owner_dedupe"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    job_match_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("job_matches.id", ondelete="SET NULL")
    )

    channel: Mapped[str] = mapped_column(
        String(20), default=NotificationChannel.TELEGRAM.value
    )
    status: Mapped[str] = mapped_column(
        String(20), default=NotificationStatus.SKIPPED.value
    )
    message: Mapped[str | None] = mapped_column(Text, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    provider_message_id: Mapped[str | None] = mapped_column(String(64), default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Set only after a successful send; NULLs never collide, so failed rows
    # stay retryable while a delivered match can never be sent twice.
    dedupe_key: Mapped[str | None] = mapped_column(String(160), default=None)
    error_class: Mapped[str | None] = mapped_column(String(20), default=None)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()  # noqa: F821
    job: Mapped["Job | None"] = relationship()  # noqa: F821
    job_match: Mapped["JobMatch | None"] = relationship()  # noqa: F821
