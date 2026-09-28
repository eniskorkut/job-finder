from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    desired_titles: Mapped[list[str]] = mapped_column(JSON, default=list)
    locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    work_modes: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords_include: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords_exclude: Mapped[list[str]] = mapped_column(JSON, default=list)

    min_match_score: Mapped[int] = mapped_column(Integer, default=70)
    daily_scan_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    politeness_delay_seconds: Mapped[int] = mapped_column(Integer, default=30)

    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=True)

    # Scheduler state (DB backed so a worker restart never loses the plan).
    next_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    last_auto_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    auto_scan_failures: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    user: Mapped["User"] = relationship(back_populates="preferences")  # noqa: F821
