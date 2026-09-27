from __future__ import annotations

from app.repositories.base import Repository
from app.repositories.cvs import CVRepository
from app.repositories.integrations import (
    NotificationRepository,
    SyncHistoryRepository,
    TelegramRepository,
)
from app.repositories.invitations import InvitationRepository
from app.repositories.jobs import JobRepository, MailAccountRepository
from app.repositories.oauth import OAuthStateRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository

__all__ = [
    "CVRepository",
    "InvitationRepository",
    "JobRepository",
    "MailAccountRepository",
    "NotificationRepository",
    "OAuthStateRepository",
    "PreferenceRepository",
    "Repository",
    "SessionRepository",
    "SyncHistoryRepository",
    "TelegramRepository",
    "UserRepository",
]
