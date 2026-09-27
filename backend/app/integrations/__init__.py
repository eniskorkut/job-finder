"""Integration layer.

Every external provider (Gmail, Microsoft Graph, DeepSeek, Telegram) is
described by an interface that phase 2 and 3 implement. Phase 1 ships the
contracts only: no network call is performed anywhere in this package, and
every method raises :class:`IntegrationNotImplemented` until the matching
phase lands.
"""

from app.integrations.base import (
    DeepSeekClient,
    IntegrationNotImplemented,
    MailProviderClient,
    NotificationClient,
    ProviderCapabilities,
)
from app.integrations.deepseek import DeepSeekScoringClient
from app.integrations.gmail import GmailClient
from app.integrations.outlook import OutlookClient
from app.integrations.telegram import TelegramClient

__all__ = [
    "DeepSeekClient",
    "DeepSeekScoringClient",
    "GmailClient",
    "IntegrationNotImplemented",
    "MailProviderClient",
    "NotificationClient",
    "OutlookClient",
    "ProviderCapabilities",
    "TelegramClient",
]
