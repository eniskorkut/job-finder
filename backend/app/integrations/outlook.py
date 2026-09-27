from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import msal

from app.core.config import settings
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
from app.integrations.errors import (
    CursorExpiredError,
    ProviderAuthError,
    ProviderError,
)
from app.integrations.http import ProviderHttpClient, assert_allowed_host
from app.integrations.parsing.mime import build_raw_message
from app.models.enums import CursorKind, ErrorClass

GRAPH_SCOPES = ("Mail.Read", "User.Read", "offline_access")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_TENANT = "consumers"
TENANT_RE = re.compile(r"^[A-Za-z0-9.-]{1,120}$")

GRAPH_HOSTS = ("graph.microsoft.com",)
AUTH_HOSTS = (
    "login.microsoftonline.com",
    "login.live.com",
    "login.windows.net",
    "graph.microsoft.com",
)

MESSAGE_SELECT = (
    "id,subject,from,receivedDateTime,body,webLink,hasAttachments,bodyPreview"
)


class OutlookClient(MailProviderClient):
    """Microsoft Graph reader for personal (Hotmail/Outlook/Live) mailboxes.

    Uses MSAL's confidential-client authorization-code flow with a serialized
    (encrypted, at rest) token cache so ``acquire_token_silent`` can refresh
    without asking the user again. MSAL is synchronous, so every call is
    offloaded to a worker thread instead of blocking the event loop.
    """

    provider = "outlook"
    capabilities = ProviderCapabilities(
        provider=provider,
        phase="phase-2",
        implemented=True,
        scopes=list(GRAPH_SCOPES),
    )

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str | None = None,
        tenant: str | None = None,
        http: ProviderHttpClient | None = None,
    ) -> None:
        if not client_id:
            raise ProviderError(
                "Microsoft istemci kimliği tanımlı değil.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        tenant = (tenant or DEFAULT_TENANT).strip()
        if not TENANT_RE.match(tenant):
            raise ProviderError(
                "Geçersiz Microsoft kiracı değeri.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant = tenant
        self.redirect_uri = redirect_uri or settings.outlook_redirect_uri
        self._http = http
        self._owns_http = http is None

    # --- lifecycle -----------------------------------------------------
    async def __aenter__(self) -> "OutlookClient":
        if self._http is None:
            self._http = await ProviderHttpClient().__aenter__()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_http and self._http is not None:
            await self._http.__aexit__()
            self._http = None

    @property
    def http(self) -> ProviderHttpClient:
        if self._http is None:
            raise RuntimeError("OutlookClient async with ile açılmalı.")
        return self._http

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}"

    # --- oauth ---------------------------------------------------------
    def authorization_url(
        self,
        *,
        state: str,
        code_challenge: str | None = None,
        login_hint: str | None = None,
    ) -> str:
        """Confidential client flow: the secret authenticates the app, so PKCE
        is not required (and not supported by MSAL for this client type)."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": " ".join(GRAPH_SCOPES),
            "state": state,
            "prompt": "select_account",
        }
        if login_hint:
            params["login_hint"] = login_hint
        return f"{self.authority}/oauth2/v2.0/authorize?{urlencode(params)}"

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str | None = None,
        cache: str | None = None,
    ) -> TokenSet:
        def _call() -> tuple[dict, str]:
            token_cache = msal.SerializableTokenCache()
            if cache:
                token_cache.deserialize(cache)
            app = self._build_app(token_cache)
            result = app.acquire_token_by_authorization_code(
                code, scopes=list(GRAPH_SCOPES), redirect_uri=self.redirect_uri
            )
            return result, token_cache.serialize()

        result, serialized = await asyncio.to_thread(_call)
        return self._token_set(result, cache_serialized=serialized)

    async def refresh(
        self,
        *,
        refresh_token: str | None = None,
        cache: str | None = None,
        account_id: str | None = None,
    ) -> TokenSet:
        def _call() -> tuple[dict, str]:
            token_cache = msal.SerializableTokenCache()
            if cache:
                token_cache.deserialize(cache)
            app = self._build_app(token_cache)
            account = self._select_account(app, account_id)
            result = app.acquire_token_silent(list(GRAPH_SCOPES), account=account)
            return result or {}, token_cache.serialize()

        result, serialized = await asyncio.to_thread(_call)
        if not result.get("access_token"):
            raise ProviderAuthError(
                "Microsoft oturumu yenilenemedi; hesabı yeniden bağlayın.",
                provider=self.provider,
            )
        return self._token_set(result, cache_serialized=serialized)

    @staticmethod
    def _select_account(app: msal.ConfidentialClientApplication, account_id: str | None):
        accounts = app.get_accounts()
        if not accounts:
            return None
        if account_id:
            for account in accounts:
                candidates = {
                    str(account.get("home_account_id") or ""),
                    str(account.get("username") or ""),
                    str(account.get("local_account_id") or ""),
                }
                if account_id in candidates:
                    return account
        return accounts[0]

    def _build_app(self, token_cache: msal.SerializableTokenCache) -> msal.ConfidentialClientApplication:
        return msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority,
            token_cache=token_cache,
        )

    def _token_set(self, result: dict, *, cache_serialized: str | None = None) -> TokenSet:
        access_token = str(result.get("access_token") or "")
        if not access_token:
            error = result.get("error") or "unknown_error"
            description = str(result.get("error_description") or "")[:300]
            raise ProviderAuthError(
                f"Microsoft yetkilendirmesi başarısız ({error}). {description}".strip(),
                provider=self.provider,
            )
        expires_in = result.get("expires_in")
        expires_at = None
        if isinstance(expires_in, (int, float)):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))
        return TokenSet(
            access_token=access_token,
            refresh_token=None,
            expires_at=expires_at,
            scopes=str(result.get("scope") or "").split(),
            cache_serialized=cache_serialized,
        )

    # --- identity ------------------------------------------------------
    async def verify_identity(self, *, access_token: str) -> ProviderIdentity:
        payload = await self.http.request_json(
            "GET",
            f"{GRAPH_BASE}/me",
            provider=self.provider,
            allowed_hosts=GRAPH_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id,mail,userPrincipalName,displayName"},
            expected=(200,),
        )
        email = str(payload.get("mail") or payload.get("userPrincipalName") or "")
        account_id = str(payload.get("id") or "")
        if not email or not account_id:
            raise ProviderError(
                "Microsoft hesabı doğrulanamadı.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        return ProviderIdentity(
            email_address=email.lower(),
            provider_account_id=account_id,
            display_name=payload.get("displayName"),
        )

    # --- scanning ------------------------------------------------------
    async def fetch_page(
        self,
        *,
        access_token: str,
        mode: ScanMode,
        query: MailQuery,
        cursor: str | None = None,
        first_page: bool = False,
    ) -> MessagePage:
        if mode is ScanMode.INCREMENTAL:
            if not cursor:
                return await self._initial_page(access_token=access_token, query=query, cursor=None)
            return await self._follow(access_token=access_token, url=cursor, delta=True)

        if cursor:
            return await self._follow(access_token=access_token, url=cursor, delta=False)

        page = await self._initial_page(access_token=access_token, query=query, cursor=None)
        if page.done and page.checkpoint_cursor is None:
            # Bootstrap a delta baseline so the next run is incremental.
            page.checkpoint_cursor = await self._delta_baseline(access_token=access_token)
            page.cursor_kind = CursorKind.GRAPH_DELTA
        return page

    async def _initial_page(
        self, *, access_token: str, query: MailQuery, cursor: str | None
    ) -> MessagePage:
        params: dict[str, object] = {
            "$select": MESSAGE_SELECT,
            "$top": min(max(query.batch_size, 1), 100),
            "$orderby": "receivedDateTime desc",
        }
        if query.since is not None:
            since = query.since
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            params["$filter"] = (
                f"receivedDateTime ge {since.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"
            )
        payload = await self.http.request_json(
            "GET",
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
            provider=self.provider,
            allowed_hosts=GRAPH_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            expected=(200,),
        )
        messages = self._messages_from_payload(payload)
        next_link = payload.get("@odata.nextLink")
        if next_link:
            assert_allowed_host(str(next_link), GRAPH_HOSTS, provider=self.provider)
            return MessagePage(
                refs=[message.external_id for message in messages],
                messages=messages,
                next_cursor=str(next_link),
                done=False,
            )
        return MessagePage(
            refs=[message.external_id for message in messages],
            messages=messages,
            next_cursor=None,
            checkpoint_cursor=None,
            cursor_kind=CursorKind.GRAPH_DELTA,
            done=True,
        )

    async def _delta_baseline(self, *, access_token: str) -> str | None:
        payload = await self.http.request_json(
            "GET",
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages/delta",
            provider=self.provider,
            allowed_hosts=GRAPH_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id", "$top": 1},
            expected=(200,),
        )
        delta_link = payload.get("@odata.deltaLink")
        if delta_link:
            assert_allowed_host(str(delta_link), GRAPH_HOSTS, provider=self.provider)
            return str(delta_link)
        next_link = payload.get("@odata.nextLink")
        if next_link:  # follow once more to reach the delta link
            follow = await self._follow(access_token=access_token, url=str(next_link), delta=True)
            return follow.checkpoint_cursor
        return None

    async def _follow(self, *, access_token: str, url: str, delta: bool) -> MessagePage:
        try:
            payload = await self.http.request_json(
                "GET",
                url,
                provider=self.provider,
                allowed_hosts=GRAPH_HOSTS,
                headers={"Authorization": f"Bearer {access_token}"},
                expected=(200,),
            )
        except ProviderError as exc:
            if delta and exc.status_code in {410, 404}:
                # Graph invalidated the delta token: ask for a bounded resync.
                raise CursorExpiredError(
                    "Microsoft delta bağlantısı geçersiz; sınırlı yeniden tarama yapılacak.",
                    provider=self.provider,
                ) from exc
            raise
        messages = self._messages_from_payload(payload)

        next_link = payload.get("@odata.nextLink")
        delta_link = payload.get("@odata.deltaLink")
        if next_link:
            assert_allowed_host(str(next_link), GRAPH_HOSTS, provider=self.provider)
            return MessagePage(
                refs=[message.external_id for message in messages],
                messages=messages,
                next_cursor=str(next_link),
                done=False,
            )
        if delta and delta_link is None:
            raise CursorExpiredError(
                "Microsoft delta bağlantısı geçersiz; sınırlı yeniden tarama yapılacak.",
                provider=self.provider,
            )
        if delta_link:
            assert_allowed_host(str(delta_link), GRAPH_HOSTS, provider=self.provider)
        return MessagePage(
            refs=[message.external_id for message in messages],
            messages=messages,
            next_cursor=None,
            checkpoint_cursor=str(delta_link) if delta_link else None,
            cursor_kind=CursorKind.GRAPH_DELTA,
            done=True,
        )

    async def fetch_message(self, *, access_token: str, message_id: str) -> RawMessage:
        payload = await self.http.request_json(
            "GET",
            f"{GRAPH_BASE}/me/messages/{message_id}",
            provider=self.provider,
            allowed_hosts=GRAPH_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": MESSAGE_SELECT},
            expected=(200,),
        )
        return convert_graph_message(payload)

    @staticmethod
    def _messages_from_payload(payload: dict) -> list[RawMessage]:
        messages: list[RawMessage] = []
        for item in payload.get("value", []) or []:
            if not isinstance(item, dict) or item.get("@removed"):
                continue
            if not item.get("id"):
                continue
            messages.append(convert_graph_message(item))
        return messages


def convert_graph_message(item: dict) -> RawMessage:
    body = item.get("body") or {}
    content = str(body.get("content") or "")
    content_type = str(body.get("contentType") or "text").lower()
    sender_info = (item.get("from") or {}).get("emailAddress") or {}
    received_raw = str(item.get("receivedDateTime") or "")
    received_at = _parse_iso(received_raw)

    html = content if content_type == "html" else None
    text = content if content_type != "html" else None
    if not text and not html:
        text = str(item.get("bodyPreview") or "")

    message = build_raw_message(
        external_id=str(item.get("id")),
        subject=str(item.get("subject") or ""),
        sender=str(sender_info.get("address") or ""),
        received_at=received_at,
        text=text,
        html=html,
    )
    message.headers["web_link"] = str(item.get("webLink") or "")
    if not message.body_text and item.get("bodyPreview"):
        message.body_text = str(item.get("bodyPreview"))
    return message


def _parse_iso(value: str) -> datetime:
    if value:
        try:
            cleaned = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


__all__ = ["GRAPH_SCOPES", "OutlookClient", "convert_graph_message"]
