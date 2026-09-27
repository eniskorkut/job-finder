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
from app.models.enums import (
    CursorKind,
    ErrorClass,
    ProcessedMessageStatus,
    SyncJobAccountStatus,
    SyncJobStatus,
    SyncTrigger,
)


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A durable scan job. Created by the API, executed by the worker.

    The job row is the source of truth for progress: the API answers 202 with
    the id and the UI polls it. A worker holds a lease (``worker_id`` +
    ``lease_expires_at``) and refreshes it with heartbeats, so a crashed worker
    can be taken over after the lease expires.
    """

    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_user_requested", "user_id", "requested_at"),
        Index("ix_sync_jobs_status_lease", "status", "lease_expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default=SyncJobStatus.QUEUED.value, index=True
    )
    trigger: Mapped[str] = mapped_column(String(20), default=SyncTrigger.MANUAL.value)
    account_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    accounts_total: Mapped[int] = mapped_column(Integer, default=0)
    accounts_processed: Mapped[int] = mapped_column(Integer, default=0)
    messages_scanned: Mapped[int] = mapped_column(Integer, default=0)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    messages_skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)

    attempt: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(120), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped["User"] = relationship()  # noqa: F821
    accounts: Mapped[list["SyncJobAccount"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class SyncJobAccount(UUIDPrimaryKeyMixin, Base):
    """Per mailbox slice of a sync job: one mailbox failing never blocks the rest."""

    __tablename__ = "sync_job_accounts"
    __table_args__ = (
        UniqueConstraint(
            "sync_job_id", "mail_account_id", name="uq_sync_job_accounts_job_account"
        ),
    )

    sync_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sync_jobs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mail_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mail_accounts.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default=SyncJobAccountStatus.QUEUED.value
    )
    messages_scanned: Mapped[int] = mapped_column(Integer, default=0)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    messages_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str] = mapped_column(String(20), default=ErrorClass.NONE.value)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    job: Mapped[SyncJob] = relationship(back_populates="accounts")
    mail_account: Mapped["MailAccount"] = relationship()  # noqa: F821


class SyncCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Incremental cursor for one mailbox (Gmail historyId / Graph delta link).

    The cursor only moves forward after the pages it covers are committed, so a
    crash re-reads the same window instead of losing mail.
    """

    __tablename__ = "sync_checkpoints"
    __table_args__ = (
        UniqueConstraint("mail_account_id", name="uq_sync_checkpoints_account"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mail_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mail_accounts.id", ondelete="CASCADE"), index=True
    )

    cursor_kind: Mapped[str] = mapped_column(String(20), default=CursorKind.NONE.value)
    cursor_value: Mapped[str | None] = mapped_column(Text, default=None)
    cursor_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    initial_sync_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    last_error_class: Mapped[str] = mapped_column(String(20), default=ErrorClass.NONE.value)


class ProcessedMessage(UUIDPrimaryKeyMixin, Base):
    """Idempotency ledger: a provider message is handled at most once per mailbox."""

    __tablename__ = "processed_messages"
    __table_args__ = (
        UniqueConstraint(
            "mail_account_id",
            "provider_message_id",
            name="uq_processed_messages_account_message",
        ),
        Index("ix_processed_messages_user_processed", "user_id", "processed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mail_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mail_accounts.id", ondelete="CASCADE"), index=True
    )

    provider_message_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(20), default=ProcessedMessageStatus.PROCESSED.value
    )
    reason: Mapped[str | None] = mapped_column(String(160), default=None)

    subject: Mapped[str | None] = mapped_column(String(500), default=None)
    sender: Mapped[str | None] = mapped_column(String(320), default=None)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobSource(UUIDPrimaryKeyMixin, Base):
    """Which mailbox/message a job was extracted from.

    One posting can be delivered by several messages (two accounts, repeated
    alerts); all of them are kept instead of collapsing into a single column.
    """

    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "provider_message_id", name="uq_job_sources_job_message"
        ),
        Index("ix_job_sources_user_account", "user_id", "mail_account_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    mail_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mail_accounts.id", ondelete="SET NULL")
    )

    provider: Mapped[str] = mapped_column(String(20))
    provider_message_id: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500), default=None)
    sender: Mapped[str | None] = mapped_column(String(320), default=None)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
