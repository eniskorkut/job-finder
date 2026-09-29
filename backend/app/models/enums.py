from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    TELEGRAM = "telegram"


class ConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    PENDING = "pending"
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"
    ERROR = "error"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobSource(StrEnum):
    MOCK = "mock"
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    MANUAL = "manual"


class MatchStatus(StrEnum):
    NEW = "new"
    VIEWED = "viewed"
    SAVED = "saved"
    DISMISSED = "dismissed"
    NOTIFIED = "notified"


class SyncStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"


class NotificationStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class UserRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class SyncJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncJobAccountStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    RETRY = "retry"
    WORKER_RECOVERY = "worker_recovery"


class CursorKind(StrEnum):
    NONE = "none"
    GMAIL_HISTORY = "gmail_history"
    GRAPH_DELTA = "graph_delta"


class ProcessedMessageStatus(StrEnum):
    PROCESSED = "processed"
    SKIPPED = "skipped"
    ERROR = "error"


class DescriptionStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT = "insufficient_description"


class ErrorClass(StrEnum):
    NONE = "none"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CURSOR_EXPIRED = "cursor_expired"


class EnrichmentStatus(StrEnum):
    PENDING = "pending"
    ENRICHED = "enriched"
    SKIPPED = "skipped"
    NOT_FOUND = "not_found"
    SEARCH_UNAVAILABLE = "search_unavailable"
    SEARCH_DISABLED = "search_disabled"
    FETCH_FAILED = "fetch_failed"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"

