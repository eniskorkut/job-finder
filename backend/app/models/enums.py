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
