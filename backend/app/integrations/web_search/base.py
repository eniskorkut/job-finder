"""Base search interfaces and data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    engine: str = ""
    score: float = 0.0


class SearchProvider(Protocol):
    """Protocol for search engine providers."""

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Execute a search query and return top results."""
        ...
