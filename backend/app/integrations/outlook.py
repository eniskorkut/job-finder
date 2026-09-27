from __future__ import annotations

from app.core.config import settings
from app.integrations.base import (
    IntegrationNotImplemented,
    JobPostingCandidate,
    MailProviderClient,
    MailSearchQuery,
    ProviderCapabilities,
    RawMessage,
)

GRAPH_SCOPES = ["offline_access", "User.Read", "Mail.Read"]


class OutlookClient(MailProviderClient):
    """Microsoft Graph mail reader (phase 2)."""

    provider = "outlook"
    phase = "phase-2"
    capabilities = ProviderCapabilities(
        provider=provider,
        phase=phase,
        implemented=False,
        scopes=GRAPH_SCOPES,
    )

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        raise IntegrationNotImplemented(self.provider, self.phase, "authorization_url")

    def exchange_code(self, *, code: str, code_verifier: str) -> dict:
        raise IntegrationNotImplemented(self.provider, self.phase, "exchange_code")

    def refresh_tokens(self, *, refresh_token: str) -> dict:
        raise IntegrationNotImplemented(self.provider, self.phase, "refresh_tokens")

    def search_job_emails(self, *, access_token: str, query: MailSearchQuery) -> list[RawMessage]:
        raise IntegrationNotImplemented(self.provider, self.phase, "search_job_emails")

    def fetch_message(self, *, access_token: str, message_id: str) -> RawMessage:
        raise IntegrationNotImplemented(self.provider, self.phase, "fetch_message")

    def parse_job_emails(self, messages: list[RawMessage]) -> list[JobPostingCandidate]:
        raise IntegrationNotImplemented(self.provider, self.phase, "parse_job_emails")

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{settings.backend_url}/api/v1/integrations/outlook/callback"
