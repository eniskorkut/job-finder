"""SearXNG JSON API search provider."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.integrations.web_search.base import SearchProvider, SearchResult

logger = logging.getLogger("jobhunter.web_search.searxng")


class SearXNGSearchProvider:
    """SearXNG meta-search provider querying the official JSON API."""

    def __init__(
        self,
        base_url: str | None = None,
        secret_key: str | None = None,
        timeout_seconds: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.web_search_searxng_url).rstrip("/")
        self.secret_key = secret_key or settings.web_search_searxng_secret_key
        self.timeout_seconds = timeout_seconds or settings.web_search_timeout_seconds
        self.semaphore = asyncio.Semaphore(
            max(1, max_concurrency or settings.web_search_max_concurrency)
        )

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Query SearXNG JSON endpoint with backoff retry."""
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

            max_retries = 2
            for attempt in range(1, max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
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
                        elif response.status_code in {429, 502, 503, 504}:
                            logger.warning(
                                "SearXNG geçici hata (HTTP %d, deneme %d/%d): %s",
                                response.status_code,
                                attempt,
                                max_retries,
                                query,
                            )
                            if attempt < max_retries:
                                await asyncio.sleep(1.0 * attempt)
                                continue
                        else:
                            logger.warning(
                                "SearXNG isteği başarısız (HTTP %d): %s",
                                response.status_code,
                                response.text[:200],
                            )
                            return []
                except (httpx.TimeoutException, httpx.RequestError) as exc:
                    logger.warning(
                        "SearXNG bağlantı hatası (deneme %d/%d): %s",
                        attempt,
                        max_retries,
                        exc,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * attempt)
                        continue
                    return []
            return []
