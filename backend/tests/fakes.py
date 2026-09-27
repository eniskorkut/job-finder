"""Test doubles for provider clients.

No test ever performs a network call: the scan pipeline is exercised through
these fakes, and HTTP behaviour itself is tested separately with a mock
transport in ``test_http_retry.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.integrations.base import (
    MailProviderClient,
    MailQuery,
    MessagePage,
    ProviderCapabilities,
    ProviderIdentity,
    RawMessage,
    ScanMode,
    TokenSet,
)
from app.integrations.gmail import GMAIL_READONLY_SCOPE
from app.integrations.outlook import GRAPH_SCOPES
from app.models.enums import CursorKind


@dataclass
class FakeProviderState:
    """Mutable state shared between the fake client and the assertions."""

    pages: list[MessagePage] = field(default_factory=list)
    messages: dict[str, RawMessage] = field(default_factory=dict)
    identity: ProviderIdentity = field(
        default_factory=lambda: ProviderIdentity(
            email_address="fake@example.com",
            provider_account_id="fake-account-1",
            display_name="Fake Hesap",
        )
    )
    page_requests: list[dict] = field(default_factory=list)
    fetch_requests: list[str] = field(default_factory=list)
    refresh_requests: list[dict] = field(default_factory=list)
    exchange_requests: list[dict] = field(default_factory=list)
    fail_on_page: int | None = None
    fail_error: Exception | None = None
    exchange_error: Exception | None = None
    refresh_error: Exception | None = None
    fetch_error: Exception | None = None
    page_offset: int = 0
    access_token: str = "access-token-1"
    refresh_token: str | None = "refresh-token-1"
    cache_serialized: str | None = "msal-cache-1"


class FakeMailProviderClient(MailProviderClient):
    def __init__(
        self,
        *,
        provider: str = "gmail",
        state: FakeProviderState | None = None,
    ) -> None:
        self.provider = provider
        self.state = state or FakeProviderState()
        scopes = [GMAIL_READONLY_SCOPE] if provider == "gmail" else list(GRAPH_SCOPES)
        self.capabilities = ProviderCapabilities(
            provider=provider, phase="phase-2", implemented=True, scopes=scopes
        )
        self.entered = False

    # --- lifecycle -----------------------------------------------------
    async def __aenter__(self) -> "FakeMailProviderClient":
        self.entered = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.entered = False

    # --- oauth ---------------------------------------------------------
    def authorization_url(
        self, *, state: str, code_challenge: str | None = None, login_hint: str | None = None
    ) -> str:
        self.last_state = state
        self.last_code_challenge = code_challenge
        return f"https://provider.test/authorize?state={state}"

    async def exchange_code(
        self, *, code: str, code_verifier: str | None = None, cache: str | None = None
    ) -> TokenSet:
        self.state.exchange_requests.append({"code": code, "verifier": code_verifier})
        if self.state.exchange_error is not None:
            raise self.state.exchange_error
        return TokenSet(
            access_token=self.state.access_token,
            refresh_token=self.state.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=self.capabilities.scopes,
            cache_serialized=self.state.cache_serialized if self.provider == "outlook" else None,
        )

    async def refresh(
        self,
        *,
        refresh_token: str | None = None,
        cache: str | None = None,
        account_id: str | None = None,
    ) -> TokenSet:
        self.state.refresh_requests.append(
            {"refresh_token": refresh_token, "cache": cache, "account_id": account_id}
        )
        if self.state.refresh_error is not None:
            raise self.state.refresh_error
        return TokenSet(
            access_token=self.state.access_token,
            refresh_token=self.state.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=self.capabilities.scopes,
            cache_serialized=self.state.cache_serialized if self.provider == "outlook" else None,
        )

    async def verify_identity(self, *, access_token: str) -> ProviderIdentity:
        return self.state.identity

    # --- scanning ------------------------------------------------------
    def reset_pages(self, pages: list[MessagePage]) -> None:
        """Swap the page script for the next scan (keeps earlier history)."""
        self.state.pages = list(pages)
        self.state.page_offset = len(self.state.page_requests)

    async def fetch_page(
        self,
        *,
        access_token: str,
        mode: ScanMode,
        query: MailQuery,
        cursor: str | None = None,
        first_page: bool = False,
    ) -> MessagePage:
        self.state.page_requests.append(
            {"mode": mode, "cursor": cursor, "query": query, "access_token": access_token}
        )
        index = len(self.state.page_requests) - 1 - self.state.page_offset
        if self.state.fail_on_page is not None and index == self.state.fail_on_page:
            assert self.state.fail_error is not None
            raise self.state.fail_error
        if index < len(self.state.pages):
            return self.state.pages[index]
        return MessagePage(done=True)

    async def fetch_message(self, *, access_token: str, message_id: str) -> RawMessage:
        self.state.fetch_requests.append(message_id)
        if self.state.fetch_error is not None:
            raise self.state.fetch_error
        if message_id not in self.state.messages:
            from app.integrations.errors import ProviderError
            from app.models.enums import ErrorClass

            raise ProviderError(
                "Mesaj bulunamadı (test).",
                provider=self.provider,
                error_class=ErrorClass.TRANSIENT,
            )
        return self.state.messages[message_id]


class FakeClientFactory:
    """Injected into the OAuth and scan services instead of real HTTP."""

    def __init__(self, clients: dict[str, FakeMailProviderClient]) -> None:
        self.clients = clients

    def build(self, *, provider: str, **kwargs: object) -> FakeMailProviderClient:
        if provider not in self.clients:
            raise AssertionError(f"Beklenmeyen sağlayıcı: {provider}")
        self.clients[provider].build_kwargs = kwargs  # type: ignore[attr-defined]
        return self.clients[provider]


def gmail_page(
    refs: list[str],
    *,
    next_cursor: str | None = None,
    checkpoint: str | None = None,
    cursor_kind: CursorKind = CursorKind.GMAIL_HISTORY,
) -> MessagePage:
    return MessagePage(
        refs=refs,
        next_cursor=next_cursor,
        checkpoint_cursor=checkpoint,
        cursor_kind=cursor_kind,
        done=next_cursor is None,
    )


def graph_page(
    messages: list[RawMessage],
    *,
    next_cursor: str | None = None,
    checkpoint: str | None = None,
) -> MessagePage:
    return MessagePage(
        refs=[message.external_id for message in messages],
        messages=messages,
        next_cursor=next_cursor,
        checkpoint_cursor=checkpoint,
        cursor_kind=CursorKind.GRAPH_DELTA,
        done=next_cursor is None,
    )
