from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConnectionStatus


class TelegramIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_integrations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    chat_id: Mapped[str | None] = mapped_column(String(64), default=None)
    username: Mapped[str | None] = mapped_column(String(120), default=None)
    bot_token_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(
        String(20), default=ConnectionStatus.DISCONNECTED.value
    )
    linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    last_error_class: Mapped[str | None] = mapped_column(String(20), default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped["User"] = relationship()  # noqa: F821
