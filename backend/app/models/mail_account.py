from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConnectionStatus


class MailAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Gmail / Outlook mailbox a user connects.

    One user can connect several mailboxes per provider, therefore the
    uniqueness constraint spans (user, provider, address).
    """

    __tablename__ = "mail_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "email_address", name="uq_mail_accounts_owner_address"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(20), index=True)
    email_address: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(
        String(20), default=ConnectionStatus.DISCONNECTED.value
    )

    access_token_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)

    search_query: Mapped[str | None] = mapped_column(String(300), default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

    user: Mapped["User"] = relationship(back_populates="mail_accounts")  # noqa: F821
