from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OAuthClientConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """[LEGACY / DEPRECATED] Per-user OAuth application credentials table.

    Retained for backward compatibility and non-destructive migrations.
    The runtime integration flow now uses deployment-wide Google and Microsoft
    OAuth applications configured via environment variables.
    Do not use this table for new authentication or sync flows.
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
