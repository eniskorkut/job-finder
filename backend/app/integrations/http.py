"""Outbound HTTP for provider calls.

Responsibilities kept in one place so every provider shares the same rules:

* connection pool and timeout limits (no unbounded parallelism),
* retry with jittered exponential backoff, honouring ``Retry-After``,
* an allowlist check before an Authorization header is attached, so a
  malformed/attacker controlled continuation link can never receive a token.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.integrations.errors import DisallowedHostError, ProviderAuthError, ProviderError
from app.models.enums import ErrorClass

logger = logging.getLogger("jobhunter.integrations.http")

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def assert_allowed_host(url: str, allowed_hosts: Sequence[str], *, provider: str) -> str:
    """Reject anything that is not an https URL on an allowlisted host."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DisallowedHostError(url, provider=provider)
    host = (parts.hostname or "").lower()
    if not host:
        raise DisallowedHostError(url, provider=provider)
    for allowed in allowed_hosts:
        allowed = allowed.lower()
        if host == allowed or host.endswith(f".{allowed}"):
            return host
    raise DisallowedHostError(url, provider=provider)


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return max(0.0, min(seconds, 300.0))


def backoff_delay(attempt: int, *, base: float, maximum: float) -> float:
    """Exponential backoff with full jitter (attempt is 1-based)."""
    raw = base * (2 ** max(0, attempt - 1))
    return min(maximum, raw) * (0.5 + random.random() / 2)


class ProviderHttpClient:
    """Small async wrapper around httpx with provider friendly retries."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_connections: int | None = None,
        max_attempts: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self.timeout = timeout if timeout is not None else settings.sync_http_timeout_seconds
        self.max_connections = (
            max_connections
            if max_connections is not None
            else settings.sync_http_max_connections
        )
        self.max_attempts = (
            max_attempts if max_attempts is not None else settings.sync_retry_max_attempts
        )
        self.base_delay = (
            base_delay if base_delay is not None else settings.sync_retry_base_delay_seconds
        )
        self.max_delay = (
            max_delay if max_delay is not None else settings.sync_retry_max_delay_seconds
        )
        self._sleep = sleep
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ProviderHttpClient":
        limits = httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=max(1, self.max_connections // 2),
        )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=limits,
            transport=self._transport,
            follow_redirects=False,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def is_open(self) -> bool:
        return self._client is not None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ProviderHttpClient kullanılmadan önce açılmalı (async with).")
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        provider: str,
        allowed_hosts: Sequence[str] | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        data: Mapping[str, Any] | None = None,
        expected: Sequence[int] = (200,),
    ) -> httpx.Response:
        if allowed_hosts:
            assert_allowed_host(url, allowed_hosts, provider=provider)

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self.client.request(
                    method,
                    url,
                    headers=dict(headers or {}),
                    params=dict(params or {}),
                    json=json_body,
                    data=dict(data or {}) if data else None,
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = ProviderError(
                    f"{provider} ağ hatası: {type(exc).__name__}",
                    provider=provider,
                    error_class=ErrorClass.TRANSIENT,
                )
                if attempt >= self.max_attempts:
                    raise last_error from exc
                await self._sleep(backoff_delay(attempt, base=self.base_delay, maximum=self.max_delay))
                continue

            if response.status_code in expected:
                return response

            retry_after = parse_retry_after(response.headers.get("retry-after"))

            if response.status_code in {401, 403}:
                raise ProviderAuthError(
                    f"{provider} yetkilendirmesi geçersiz (HTTP {response.status_code}).",
                    provider=provider,
                    status_code=response.status_code,
                )

            if response.status_code in RETRYABLE_STATUS:
                error_class = (
                    ErrorClass.RATE_LIMIT
                    if response.status_code == 429
                    else ErrorClass.TRANSIENT
                )
                last_error = ProviderError(
                    f"{provider} geçici hata (HTTP {response.status_code}).",
                    provider=provider,
                    error_class=error_class,
                    status_code=response.status_code,
                    retry_after=retry_after,
                )
                if attempt >= self.max_attempts:
                    raise last_error
                delay = retry_after if retry_after is not None else backoff_delay(
                    attempt, base=self.base_delay, maximum=self.max_delay
                )
                logger.info(
                    "%s HTTP %s, %.1fs sonra tekrar denenecek (%s/%s)",
                    provider,
                    response.status_code,
                    delay,
                    attempt,
                    self.max_attempts,
                )
                await self._sleep(delay)
                continue

            raise ProviderError(
                f"{provider} beklenmeyen yanıt (HTTP {response.status_code}).",
                provider=provider,
                error_class=ErrorClass.PERMANENT,
                status_code=response.status_code,
                retryable=False,
            )

        raise last_error or ProviderError(
            f"{provider} isteği başarısız oldu.", provider=provider
        )

    async def request_json(
        self, method: str, url: str, **kwargs: Any
    ) -> dict[str, Any]:
        response = await self.request(method, url, **kwargs)
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - provider contract violation
            raise ProviderError(
                "Sağlayıcı geçersiz JSON döndürdü.",
                provider=kwargs.get("provider", "unknown"),
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            ) from exc
        return payload if isinstance(payload, dict) else {"value": payload}
