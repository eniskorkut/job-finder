"""Null web search provider that performs no network calls."""

from __future__ import annotations

from app.integrations.web_search.base import SearchResult


class NullSearchProvider:
    """Disabled search provider (web_search_provider=none).

    Guarantees that no outbound network requests are made.
    """

    available: bool = False

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Always return empty results without network I/O."""
        return []

    async def close(self) -> None:
        """No-op cleanup."""
        pass
