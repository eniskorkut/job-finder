from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OAuthClientConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's own OAuth application credentials for one provider.

    Every user registers their own Google / Microsoft Entra application, so the
    client id and secret are per user and stored encrypted. A single config can
    authorize several mailboxes.
    """

    __tablename__ = "oauth_client_configs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", name="uq_oauth_client_configs_owner_provider"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), index=True)
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    tenant: Mapped[str | None] = mapped_column(String(120), default=None)
    redirect_uri: Mapped[str | None] = mapped_column(String(500), default=None)

    user: Mapped["User"] = relationship()  # noqa: F821
