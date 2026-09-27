from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.message import Message


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


@dataclass(slots=True)
class MatchScore:
    score: int
    rationale: str
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    model: str | None = None


class MailProviderClient(ABC):
    """Read-only mailbox access used by the scan pipeline."""

    provider: str
    phase: str
    capabilities: ProviderCapabilities

    @abstractmethod
    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        """Return the provider consent URL for the OAuth dance."""

    @abstractmethod
    def exchange_code(self, *, code: str, code_verifier: str) -> dict:
        """Exchange an authorization code for tokens."""

    @abstractmethod
    def refresh_tokens(self, *, refresh_token: str) -> dict:
        """Refresh an access token."""

    @abstractmethod
    def search_job_emails(self, *, access_token: str, query: MailSearchQuery) -> list[RawMessage]:
        """List candidate job alert e-mails."""

    @abstractmethod
    def fetch_message(self, *, access_token: str, message_id: str) -> RawMessage:
        """Fetch one full message."""

    @abstractmethod
    def parse_job_emails(self, messages: list[RawMessage]) -> list[JobPostingCandidate]:
        """Turn raw alert e-mails into structured job posting candidates."""

    def describe(self) -> ProviderCapabilities:
        return self.capabilities


class JobScoringClient(ABC):
    """Shared LLM scoring client (DeepSeek). Not user specific."""

    provider: str
    phase: str

    @abstractmethod
    def score_job(
        self, *, cv_text: str, job_title: str, job_description: str, preferences: dict
    ) -> MatchScore:
        """Return a 0-100 match score with rationale."""

    @abstractmethod
    def extract_profile(self, *, cv_text: str) -> dict:
        """Extract structured profile data from a CV."""


class NotificationClient(ABC):
    provider: str
    phase: str

    @abstractmethod
    def send_message(self, *, destination: str, text: str) -> dict:
        """Send a single notification message."""

    @abstractmethod
    def verify_destination(self, *, destination: str) -> bool:
        """Check that the destination (chat id) is reachable."""


class DeepSeekClient(JobScoringClient):
    """Alias kept for readability at call sites."""


def parse_headers(message: Message) -> dict[str, str]:
    """Small helper kept here so phase 2 parsers share one implementation."""

    return {key: value for key, value in message.items()}
