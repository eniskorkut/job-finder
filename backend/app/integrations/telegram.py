"""Telegram Bot API client (per user, token stored encrypted).

The bot token is part of the request URL, so it is never placed in an error
message, returned to the API layer or written to a log line (the secret filter
in ``app.core.logging`` rewrites it even if httpx logs the URL).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings
from app.integrations.base import NotificationClient
from app.integrations.errors import ProviderError
from app.integrations.http import ProviderHttpClient
from app.models.enums import ErrorClass

TELEGRAM_REASONS = {
    "invalid_token": "Bot token geçersiz.",
    "invalid_chat": "Chat ID bulunamadı veya bot bu sohbete erişemiyor.",
    "bot_blocked": "Bot kullanıcı tarafından engellenmiş.",
    "rate_limited": "Telegram hız sınırı uyguladı.",
    "timeout": "Telegram yanıt vermedi (zaman aşımı).",
    "server_error": "Telegram geçici bir hata döndürdü.",
    "bad_request": "Telegram isteği reddetti.",
    "unknown": "Telegram isteği başarısız oldu.",
}


class TelegramError(ProviderError):
    def __init__(
        self,
        reason: str,
        *,
        error_class: ErrorClass,
        status_code: int | None = None,
        retry_after: float | None = None,
        detail: str | None = None,
    ) -> None:
        message = TELEGRAM_REASONS.get(reason, TELEGRAM_REASONS["unknown"])
        if detail and reason in {"bad_request", "unknown"}:
            message = f"{message} ({detail[:160]})"
        super().__init__(
            message,
            provider="telegram",
            error_class=error_class,
            status_code=status_code,
            retry_after=retry_after,
            retryable=error_class in {ErrorClass.TRANSIENT, ErrorClass.RATE_LIMIT},
        )
        self.reason = reason


class TelegramClient(NotificationClient):
    """Minimal Bot API surface: getMe, getChat, getUpdates, sendMessage."""

    provider = "telegram"

    def __init__(
        self,
        *,
        bot_token: str,
        api_base: str | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
        http: ProviderHttpClient | None = None,
    ) -> None:
        token = (bot_token or "").strip()
        if not token or ":" not in token:
            raise TelegramError("invalid_token", error_class=ErrorClass.AUTH)
        self.bot_token = token
        self.api_base = (api_base or settings.telegram_api_base).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.telegram_timeout_seconds
        )
        self.max_attempts = (
            max_attempts if max_attempts is not None else settings.telegram_retry_max_attempts
        )
        self._http = http
        self._owns_http = http is None

    # --- lifecycle ------------------------------------------------------
    @property
    def allowed_hosts(self) -> list[str]:
        host = (urlsplit(self.api_base).hostname or "").lower()
        return [host] if host else []

    @property
    def masked_token(self) -> str:
        prefix, _, suffix = self.bot_token.partition(":")
        tail = suffix[-4:] if len(suffix) > 4 else suffix
        return f"{prefix}…{tail}"

    async def __aenter__(self) -> "TelegramClient":
        if self._http is None:
            self._http = ProviderHttpClient(
                timeout=self.timeout_seconds,
                max_attempts=self.max_attempts,
            )
            self._owns_http = True
        if not self._http.is_open:
            await self._http.__aenter__()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._http is not None and self._http.is_open:
            await self._http.__aexit__()
            self._http = None

    @property
    def http(self) -> ProviderHttpClient:
        if self._http is None:
            raise RuntimeError("Telegram istemcisi async with ile açılmalı.")
        return self._http

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "configured": True,
            "token_hint": self.masked_token,
            "api_base": urlsplit(self.api_base).netloc,
        }

    # --- transport ------------------------------------------------------
    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.bot_token}/{method}"

    async def _request(self, method: str, payload: dict[str, Any] | None) -> dict:
        """Telegram answers HTTP 200 with ok=false; map that honestly."""
        http_method = "POST" if payload is not None else "GET"
        try:
            response = await self.http.request(
                http_method,
                self._url(method),
                provider=self.provider,
                allowed_hosts=self.allowed_hosts,
                json_body=payload if payload is not None else None,
                expected=tuple(range(200, 500)),
            )
        except ProviderError as exc:
            if exc.error_class == ErrorClass.TRANSIENT:
                raise TelegramError(
                    "timeout" if "ağ hatası" in str(exc) else "server_error",
                    error_class=ErrorClass.TRANSIENT,
                ) from exc
            raise

        try:
            body = response.json() if response.content else {}
        except ValueError as exc:
            raise TelegramError("server_error", error_class=ErrorClass.TRANSIENT) from exc
        if not isinstance(body, dict):
            body = {}

        if response.status_code >= 400 or body.get("ok") is False:
            raise self._map_error(response.status_code, body)

        result = body.get("result")
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _map_error(status_code: int, body: dict) -> TelegramError:
        error_code = body.get("error_code") or status_code
        description = str(body.get("description") or "")
        parameters = body.get("parameters") or {}
        retry_after = parameters.get("retry_after")

        if error_code == 429:
            return TelegramError(
                "rate_limited",
                error_class=ErrorClass.RATE_LIMIT,
                status_code=429,
                retry_after=float(retry_after) if retry_after else None,
                detail=description,
            )
        if error_code in {401, 404} and "chat" not in description.lower():
            return TelegramError(
                "invalid_token", error_class=ErrorClass.AUTH, status_code=error_code
            )
        if error_code == 403:
            return TelegramError("bot_blocked", error_class=ErrorClass.AUTH, status_code=403)
        if error_code == 400:
            lowered = description.lower()
            if "chat not found" in lowered or "chat_id" in lowered or "chat id" in lowered:
                return TelegramError(
                    "invalid_chat", error_class=ErrorClass.PERMANENT, status_code=400
                )
            return TelegramError(
                "bad_request",
                error_class=ErrorClass.PERMANENT,
                status_code=400,
                detail=description,
            )
        if status_code >= 500 or error_code >= 500:
            return TelegramError(
                "server_error", error_class=ErrorClass.TRANSIENT, status_code=status_code
            )
        return TelegramError(
            "unknown",
            error_class=ErrorClass.PERMANENT,
            status_code=status_code,
            detail=description,
        )

    # --- API surface ----------------------------------------------------
    async def get_me(self) -> dict:
        return await self._request("getMe", None)

    async def get_chat(self, *, chat_id: str) -> dict:
        return await self._request("getChat", {"chat_id": chat_id})

    async def get_updates(self, *, limit: int = 20, timeout: int = 0) -> list[dict]:
        result = await self._request(
            "getUpdates", {"limit": limit, "timeout": timeout, "allowed_updates": ["message"]}
        )
        updates = result.get("result")
        return [item for item in updates if isinstance(item, dict)] if isinstance(updates, list) else []

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> dict:
        limit = settings.telegram_max_message_chars
        payload = {
            "chat_id": chat_id,
            "text": text[:limit],
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        return await self._request("sendMessage", payload)

    # --- helpers --------------------------------------------------------
    async def verify(self) -> dict:
        """getMe + optional getChat, used by the connection form."""
        me = await self.get_me()
        return {
            "id": me.get("id"),
            "username": me.get("username"),
            "first_name": me.get("first_name"),
        }

__all__ = ["TelegramClient", "TelegramError"]
