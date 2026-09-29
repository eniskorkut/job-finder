"""SearXNG JSON API search provider with client reuse and bounded retries."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.integrations.http import RETRYABLE_STATUS, backoff_delay, parse_retry_after
from app.integrations.web_search.base import (
    SearchPermanentError,
    SearchProvider,
    SearchResult,
    SearchUnavailableError,
)

logger = logging.getLogger("jobhunter.web_search.searxng")


class SearXNGSearchProvider:
    """SearXNG meta-search provider querying the official JSON API.

    Features:
    - Reusable httpx.AsyncClient with connection pooling across batches
    - Bounded retries for transient errors (408, 429, 5xx, timeouts)
    - Retry-After support with jittered exponential backoff
    - Clear distinction between 0 results (empty list) and provider failure (SearchUnavailableError)
    """

    available: bool = True

    def __init__(
        self,
        base_url: str | None = None,
        secret_key: str | None = None,
        timeout_seconds: float | None = None,
        max_concurrency: int | None = None,
        max_attempts: int | None = None,
        client: httpx.AsyncClient | None = None,
        _sleeper: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.base_url = (base_url or settings.web_search_searxng_url).rstrip("/")
        self.secret_key = secret_key or settings.web_search_searxng_secret_key
        self.timeout_seconds = timeout_seconds or settings.web_search_timeout_seconds
        self.max_attempts = max_attempts or settings.web_search_retry_max_attempts
        self.semaphore = asyncio.Semaphore(
            max(1, max_concurrency or settings.web_search_max_concurrency)
        )
        self._external_client = client is not None
        self._client: httpx.AsyncClient | None = client
        self._sleeper = _sleeper

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(
                max_connections=settings.sync_http_max_connections,
                max_keepalive_connections=5,
            )
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                limits=limits,
            )
        return self._client

    async def close(self) -> None:
        """Close connection pool if owned by this instance."""
        if not self._external_client and self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> SearXNGSearchProvider:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Query SearXNG JSON endpoint with bounded backoff retry.

        Raises:
            SearchUnavailableError: When SearXNG is unreachable, timing out, or failing retries.
            SearchPermanentError: When unauthorized (401/403) or request malformed (400/422).
        """
        if not query.strip():
            return []

        async with self.semaphore:
            params = {
                "q": query.strip(),
                "format": "json",
                "categories": "general",
            }
            if self.secret_key:
                params["secret_key"] = self.secret_key

            url = f"{self.base_url}/search?{urlencode(params)}"
            headers = {
                "Accept": "application/json",
                "User-Agent": "JobHunter/1.0",
            }

            client = self._get_client()
            last_error: Exception | None = None

            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = await client.get(url, headers=headers)

                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        raw_items = data.get("results", [])
                        for item in raw_items[:limit]:
                            item_url = item.get("url")
                            item_title = item.get("title", "")
                            item_content = item.get("content", "")
                            if item_url:
                                results.append(
                                    SearchResult(
                                        url=item_url,
                                        title=" ".join(item_title.split()),
                                        snippet=" ".join(item_content.split()),
                                        engine=item.get("engine", "searxng"),
                                        score=float(item.get("score") or 0.0),
                                    )
                                )
                        return results

                    if response.status_code in {401, 403}:
                        msg = f"SearXNG erişim yetkisi reddedildi (HTTP {response.status_code})."
                        logger.error(msg)
                        raise SearchPermanentError(msg)

                    if response.status_code in {400, 422}:
                        msg = f"SearXNG geçersiz sorgu hatası (HTTP {response.status_code}): {response.text[:200]}"
                        logger.warning(msg)
                        raise SearchPermanentError(msg)

                    if response.status_code in RETRYABLE_STATUS:
                        retry_after = parse_retry_after(response.headers.get("retry-after"))
                        delay = retry_after if retry_after is not None else backoff_delay(
                            attempt, base=0.5, maximum=5.0
                        )
                        logger.warning(
                            "SearXNG geçici HTTP %d hatası (deneme %d/%d, gecikme %.2fs): %s",
                            response.status_code,
                            attempt,
                            self.max_attempts,
                            delay,
                            query,
                        )
                        last_error = SearchUnavailableError(
                            f"SearXNG geçici hata (HTTP {response.status_code})"
                        )
                        if attempt < self.max_attempts:
                            await self._sleeper(delay)
                            continue
                        raise last_error

                    # Other non-retryable 4xx/5xx status
                    logger.warning(
                        "SearXNG beklenmeyen yanıt (HTTP %d): %s",
                        response.status_code,
                        response.text[:200],
                    )
                    raise SearchUnavailableError(
                        f"SearXNG beklenmeyen yanıt verdi (HTTP {response.status_code})"
                    )

                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    delay = backoff_delay(attempt, base=0.5, maximum=5.0)
                    logger.warning(
                        "SearXNG bağlantı hatası (deneme %d/%d, gecikme %.2fs): %s",
                        attempt,
                        self.max_attempts,
                        delay,
                        exc,
                    )
                    last_error = SearchUnavailableError(
                        f"SearXNG servisine bağlanılamadı ({self.base_url}): {exc}"
                    )
                    if attempt < self.max_attempts:
                        await self._sleeper(delay)
                        continue
                    raise last_error from exc
                except (SearchPermanentError, SearchUnavailableError):
                    raise
                except Exception as exc:
                    logger.exception("SearXNG çağrısı sırasında beklenmeyen hata: %s", exc)
                    raise SearchUnavailableError(f"SearXNG çağrısı başarısız: {exc}") from exc

            if last_error:
                raise last_error
            raise SearchUnavailableError("SearXNG araması sonuçlanamadı.")
