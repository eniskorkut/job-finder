from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CV(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cvs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120), default=None)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[str | None] = mapped_column(String(64), default=None)

    summary: Mapped[str | None] = mapped_column(Text, default=None)
    extracted_text: Mapped[str | None] = mapped_column(Text, default=None)
    extraction_status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending"
    )
    extraction_warning: Mapped[str | None] = mapped_column(String(300), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="cvs")  # noqa: F821
