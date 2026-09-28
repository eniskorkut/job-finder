from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.message import Message
from enum import StrEnum
from typing import Any

from app.models.enums import CursorKind


class IntegrationNotImplemented(NotImplementedError):
    """Raised by phase 2/3 interfaces until their phase is implemented."""

    def __init__(self, provider: str, phase: str, operation: str) -> None:
        self.provider = provider
        self.phase = phase
        self.operation = operation
        super().__init__(
            f"{provider}::{operation} is not implemented yet (scheduled for {phase})."
        )


@dataclass(slots=True)
class ProviderCapabilities:
    provider: str
    phase: str
    supports_oauth: bool = True
    supports_multiple_accounts: bool = True
    implemented: bool = False
    scopes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RawMessage:
    external_id: str
    subject: str
    sender: str
    received_at: datetime
    body_text: str
    body_html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MailSearchQuery:
    """Search window for a mailbox scan."""

    keywords: list[str] = field(default_factory=list)
    senders: list[str] = field(default_factory=list)
    since: datetime | None = None
    max_results: int = 100


@dataclass(slots=True)
class JobPostingCandidate:
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    description: str | None = None
    external_id: str | None = None
    raw_message: RawMessage | None = None
    # "ok" when the alert carried enough text to be useful, otherwise
    # DescriptionStatus.INSUFFICIENT - the UI badges those instead of the
    # parser inventing content that was not in the e-mail.
    description_status: str = "ok"


@dataclass(slots=True)
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scopes: list[str] = field(default_factory=list)
    token_type: str = "Bearer"
    # MSAL keeps its own cache (encrypted at rest); Gmail does not use it.
    cache_serialized: str | None = None


@dataclass(slots=True)
class ProviderIdentity:
    """Who the provider says the mailbox belongs to. Never client supplied."""

    email_address: str
    provider_account_id: str
    display_name: str | None = None


class ScanMode(StrEnum):
    INITIAL = "initial"
    INCREMENTAL = "incremental"


@dataclass(slots=True)
class MailQuery:
    senders: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    since: datetime | None = None
    limit: int = 100
    batch_size: int = 25


@dataclass(slots=True)
class MessagePage:
    """One page of a scan.

    ``next_cursor`` continues pagination; ``checkpoint_cursor`` is what may be
    persisted once this page is fully processed (a Gmail ``historyId`` or a
    Graph ``deltaLink``).
    """

    refs: list[str] = field(default_factory=list)
    messages: list[RawMessage] = field(default_factory=list)
    next_cursor: str | None = None
    checkpoint_cursor: str | None = None
    cursor_kind: CursorKind = CursorKind.NONE
    done: bool = True


class MailProviderClient(ABC):
    """Async, read-only mailbox access used by the scan pipeline.

    Implementations must never receive a database session: the scan service
    owns persistence so provider code stays testable with a fake transport.
    """

    provider: str
    capabilities: ProviderCapabilities

    @abstractmethod
    def authorization_url(
        self,
        *,
        state: str,
        code_challenge: str | None = None,
        login_hint: str | None = None,
    ) -> str:
        """Provider consent URL for the OAuth authorization-code flow."""

    @abstractmethod
    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str | None = None,
        cache: str | None = None,
    ) -> TokenSet:
        """Exchange an authorization code for tokens."""

    @abstractmethod
    async def refresh(
        self,
        *,
        refresh_token: str | None = None,
        cache: str | None = None,
        account_id: str | None = None,
    ) -> TokenSet:
        """Obtain a fresh access token (refresh token or MSAL silent cache)."""

    @abstractmethod
    async def verify_identity(self, *, access_token: str) -> ProviderIdentity:
        """Resolve the real mailbox address from the provider."""

    @abstractmethod
    async def fetch_page(
        self,
        *,
        access_token: str,
        mode: ScanMode,
        query: MailQuery,
        cursor: str | None = None,
        first_page: bool = False,
    ) -> MessagePage:
        """List candidate job-alert messages (ids, or full bodies for Graph)."""

    @abstractmethod
    async def fetch_message(self, *, access_token: str, message_id: str) -> RawMessage:
        """Fetch and decode one full message."""

    def describe(self) -> ProviderCapabilities:
        return self.capabilities


class JobScoringClient(ABC):
    """Shared LLM client contract (implemented by the OpenAI-compatible client).

    Not user specific: the caller has already scoped the data to one owner.
    """

    provider: str

    @property
    @abstractmethod
    def configured(self) -> bool:
        """True when key, base URL and model are all present."""

    @abstractmethod
    async def extract_cv_profile(self, *, cv_text: str) -> tuple[Any, Any]:
        """Structured profile extracted from one CV."""

    @abstractmethod
    async def score_job(self, **kwargs: Any) -> tuple[Any, Any]:
        """Requirement fit between one CV and one job posting."""

    @abstractmethod
    def describe(self) -> dict:
        """Safe (secret free) summary for the API/UI."""


class NotificationClient(ABC):
    """Per-user notification transport contract (Telegram today)."""

    provider: str

    @abstractmethod
    async def send_message(self, *, chat_id: str, text: str) -> dict:
        """Send a single notification message."""

    @abstractmethod
    async def get_chat(self, *, chat_id: str) -> dict:
        """Resolve a chat to confirm the destination exists."""

    @abstractmethod
    def describe(self) -> dict:
        """Safe (token free) summary for the API/UI."""


def parse_headers(message: Message) -> dict[str, str]:
    """Small helper kept here so phase 2 parsers share one implementation."""

    return {key: value for key, value in message.items()}
