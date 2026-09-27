from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

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
from app.integrations.errors import CursorExpiredError, ProviderError
from app.integrations.http import ProviderHttpClient
from app.integrations.parsing.mime import parse_message_bytes
from app.models.enums import CursorKind, ErrorClass

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
IDENTITY_SCOPES = ("openid", "email")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_HOSTS = ("accounts.google.com", "oauth2.googleapis.com", "gmail.googleapis.com", "www.googleapis.com")

TOKEN_EXPIRY_SKEW = timedelta(seconds=90)


class GmailClient(MailProviderClient):
    """Gmail REST client using the user's own OAuth application credentials."""

    provider = "gmail"
    capabilities = ProviderCapabilities(
        provider=provider,
        phase="phase-2",
        implemented=True,
        scopes=[GMAIL_READONLY_SCOPE, *IDENTITY_SCOPES],
    )

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str | None = None,
        http: ProviderHttpClient | None = None,
    ) -> None:
        if not client_id:
            raise ProviderError(
                "Gmail istemci kimliği tanımlı değil.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or settings.gmail_redirect_uri
        self._http = http
        self._owns_http = http is None

    # --- lifecycle -----------------------------------------------------
    async def __aenter__(self) -> "GmailClient":
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
            raise RuntimeError("GmailClient async with ile açılmalı.")
        return self._http

    # --- oauth ---------------------------------------------------------
    def authorization_url(
        self,
        *,
        state: str,
        code_challenge: str | None = None,
        login_hint: str | None = None,
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join([GMAIL_READONLY_SCOPE, *IDENTITY_SCOPES]),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        if login_hint:
            params["login_hint"] = login_hint
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str | None = None,
        cache: str | None = None,
    ) -> TokenSet:
        payload = {
            "client_id": self.client_id,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        if code_verifier:
            payload["code_verifier"] = code_verifier

        data = await self.http.request_json(
            "POST",
            TOKEN_URL,
            provider=self.provider,
            allowed_hosts=GOOGLE_HOSTS,
            data=payload,
            expected=(200,),
        )
        return self._token_set(data)

    async def refresh(
        self,
        *,
        refresh_token: str | None = None,
        cache: str | None = None,
        account_id: str | None = None,
    ) -> TokenSet:
        if not refresh_token:
            from app.integrations.errors import ProviderAuthError

            raise ProviderAuthError(
                "Gmail yenileme anahtarı yok; hesabı yeniden bağlayın.",
                provider=self.provider,
            )
        payload = {
            "client_id": self.client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        data = await self.http.request_json(
            "POST",
            TOKEN_URL,
            provider=self.provider,
            allowed_hosts=GOOGLE_HOSTS,
            data=payload,
            expected=(200,),
        )
        return self._token_set(data, fallback_refresh_token=refresh_token)

    def _token_set(
        self, data: dict, *, fallback_refresh_token: str | None = None
    ) -> TokenSet:
        access_token = str(data.get("access_token") or "")
        if not access_token:
            raise ProviderError(
                "Gmail erişim anahtarı alınamadı.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        expires_in = data.get("expires_in")
        expires_at = None
        if isinstance(expires_in, (int, float)):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))
        scopes = str(data.get("scope") or "").split()
        return TokenSet(
            access_token=access_token,
            # Google may omit the refresh token on re-consent; never drop it.
            refresh_token=str(data.get("refresh_token") or "") or fallback_refresh_token,
            expires_at=expires_at,
            scopes=scopes,
        )

    async def verify_identity(self, *, access_token: str) -> ProviderIdentity:
        profile = await self.http.request_json(
            "GET",
            USERINFO_URL,
            provider=self.provider,
            allowed_hosts=GOOGLE_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            expected=(200,),
        )
        email = str(profile.get("email") or "")
        if not email:
            raise ProviderError(
                "Gmail hesap adresi doğrulanamadı.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        return ProviderIdentity(
            email_address=email.lower(),
            provider_account_id=str(profile.get("sub") or email.lower()),
            display_name=profile.get("name"),
        )

    async def get_profile(self, *, access_token: str) -> dict:
        return await self.http.request_json(
            "GET",
            f"{API_BASE}/users/me/profile",
            provider=self.provider,
            allowed_hosts=GOOGLE_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            expected=(200,),
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
        if mode is ScanMode.INCREMENTAL and cursor:
            return await self._history_page(access_token=access_token, cursor=cursor)
        return await self._list_page(
            access_token=access_token, query=query, page_token=cursor
        )

    async def _list_page(
        self,
        *,
        access_token: str,
        query: MailQuery,
        page_token: str | None,
    ) -> MessagePage:
        params: dict[str, object] = {
            "maxResults": min(max(query.batch_size, 1), 100),
            "q": build_gmail_query(query),
        }
        if page_token:
            params["pageToken"] = page_token

        payload = await self.http.request_json(
            "GET",
            f"{API_BASE}/users/me/messages",
            provider=self.provider,
            allowed_hosts=GOOGLE_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            expected=(200,),
        )
        refs = [
            str(item["id"])
            for item in payload.get("messages", [])
            if isinstance(item, dict) and item.get("id")
        ]
        next_token = payload.get("nextPageToken")
        if next_token:
            return MessagePage(refs=refs, next_cursor=str(next_token), done=False)

        # Last page of the initial sweep: pin the checkpoint to "now" so mail
        # that arrives during the scan is picked up by the next run.
        profile = await self.get_profile(access_token=access_token)
        checkpoint = str(profile.get("historyId") or "") or None
        return MessagePage(
            refs=refs,
            next_cursor=None,
            checkpoint_cursor=checkpoint,
            cursor_kind=CursorKind.GMAIL_HISTORY,
            done=True,
        )

    async def _history_page(self, *, access_token: str, cursor: str) -> MessagePage:
        payload = await self._history_request(access_token, cursor)

        refs: list[str] = []
        for record in payload.get("history", []) or []:
            for added in record.get("messagesAdded", []) or []:
                message = added.get("message") or {}
                message_id = message.get("id")
                labels = message.get("labelIds") or []
                if message_id and "SPAM" not in labels and "TRASH" not in labels:
                    refs.append(str(message_id))

        history_id = str(payload.get("historyId") or cursor)
        next_token = payload.get("nextPageToken")
        if next_token:
            return MessagePage(refs=refs, next_cursor=str(next_token), done=False)
        return MessagePage(
            refs=refs,
            next_cursor=None,
            checkpoint_cursor=history_id,
            cursor_kind=CursorKind.GMAIL_HISTORY,
            done=True,
        )

    async def _history_request(self, access_token: str, cursor: str) -> dict:
        try:
            return await self.http.request_json(
                "GET",
                f"{API_BASE}/users/me/history",
                provider=self.provider,
                allowed_hosts=GOOGLE_HOSTS,
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "startHistoryId": cursor,
                    "historyTypes": "messageAdded",
                    "maxResults": 100,
                },
                expected=(200,),
            )
        except ProviderError as exc:
            if exc.status_code == 404:
                # Google expired the history window: re-run a bounded initial
                # scan instead of surfacing a user facing error.
                raise CursorExpiredError(
                    "Gmail geçmiş penceresi kapandı; sınırlı yeniden tarama yapılacak.",
                    provider=self.provider,
                ) from exc
            raise

    async def fetch_message(self, *, access_token: str, message_id: str) -> RawMessage:
        payload = await self.http.request_json(
            "GET",
            f"{API_BASE}/users/me/messages/{message_id}",
            provider=self.provider,
            allowed_hosts=GOOGLE_HOSTS,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "raw"},
            expected=(200,),
        )
        raw = payload.get("raw")
        if not raw:
            raise ProviderError(
                "Gmail mesaj gövdesi alınamadı.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )
        try:
            decoded = base64.urlsafe_b64decode(str(raw) + "===")
        except (ValueError, TypeError) as exc:
            raise ProviderError(
                "Gmail mesaj gövdesi çözümlenemedi.",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            ) from exc
        return parse_message_bytes(decoded, external_id=message_id)


def build_gmail_query(query: MailQuery) -> str:
    parts: list[str] = []
    if query.senders:
        parts.append("from:(" + " OR ".join(query.senders) + ")")
    if query.subjects:
        quoted = " OR ".join(f'"{subject}"' for subject in query.subjects)
        parts.append(f"subject:({quoted})")
    if query.since is not None:
        since = query.since
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        parts.append(f"after:{since.astimezone(timezone.utc):%Y/%m/%d}")
    if not parts:
        return "in:inbox"
    return " ".join(parts)
