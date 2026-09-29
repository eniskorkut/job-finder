"""Base search interfaces and data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WebSearchError(Exception):
    """Base exception for web search errors."""


class SearchUnavailableError(WebSearchError):
    """Raised when search provider is unconfigured, unreachable, or timing out."""


class SearchPermanentError(WebSearchError):
    """Raised on permanent client errors (e.g. 400, 401, 403, 422)."""


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    engine: str = ""
    score: float = 0.0


class SearchProvider(Protocol):
    """Protocol for search engine providers."""

    available: bool = True

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Execute a search query and return top results."""
        ...

    async def close(self) -> None:
        """Release underlying network resources."""
        ...

