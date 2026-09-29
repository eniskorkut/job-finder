"""Web search provider package."""

from __future__ import annotations

from app.core.config import settings
from app.integrations.web_search.base import SearchProvider, SearchResult
from app.integrations.web_search.mock import MockSearchProvider
from app.integrations.web_search.searxng import SearXNGSearchProvider


def get_search_provider() -> SearchProvider:
    """Factory to get the configured search provider."""
    provider_type = (settings.web_search_provider or "searxng").lower()
    if provider_type == "mock":
        return MockSearchProvider()
    return SearXNGSearchProvider()


__all__ = [
    "MockSearchProvider",
    "SearchProvider",
    "SearchResult",
    "SearXNGSearchProvider",
    "get_search_provider",
]
