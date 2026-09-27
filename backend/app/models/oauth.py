from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class OAuthState(UUIDPrimaryKeyMixin, Base):
    """Short lived CSRF/PKCE state for the Gmail and Microsoft Graph flows."""

    __tablename__ = "oauth_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(20), index=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_verifier_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    redirect_uri: Mapped[str | None] = mapped_column(String(500), default=None)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped["User"] = relationship()  # noqa: F821
