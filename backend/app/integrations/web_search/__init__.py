"""Web search provider package."""

from __future__ import annotations

from app.core.config import settings
from app.integrations.web_search.base import (
    SearchPermanentError,
    SearchProvider,
    SearchResult,
    SearchUnavailableError,
    WebSearchError,
)
from app.integrations.web_search.health import check_searxng_health
from app.integrations.web_search.mock import MockSearchProvider
from app.integrations.web_search.null import NullSearchProvider
from app.integrations.web_search.searxng import SearXNGSearchProvider


def get_search_provider() -> SearchProvider:
    """Factory to get the configured search provider.

    Returns:
        NullSearchProvider when web_search_provider == 'none'
        MockSearchProvider when web_search_provider == 'mock'
        SearXNGSearchProvider when web_search_provider == 'searxng' (default)
    """
    provider_type = (settings.web_search_provider or "searxng").lower().strip()
    if provider_type == "none":
        return NullSearchProvider()
    if provider_type == "mock":
        return MockSearchProvider()
    return SearXNGSearchProvider()


__all__ = [
    "MockSearchProvider",
    "NullSearchProvider",
    "SearchPermanentError",
    "SearchProvider",
    "SearchResult",
    "SearchUnavailableError",
    "SearXNGSearchProvider",
    "WebSearchError",
    "check_searxng_health",
    "get_search_provider",
]
