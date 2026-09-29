"""Deterministic mock search provider for tests and simulation."""

from __future__ import annotations

from app.integrations.web_search.base import SearchResult


class MockSearchProvider:
    """Mock search provider returning pre-configured or deterministic test results."""

    available: bool = True

    def __init__(self, canned_results: dict[str, list[SearchResult]] | None = None) -> None:
        self.canned_results = canned_results or {}
        self.queries_executed: list[str] = []

    def set_results(self, query_substr: str, results: list[SearchResult]) -> None:
        self.canned_results[query_substr.lower()] = results

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.queries_executed.append(query)
        q_lower = query.lower()
        for key, results in self.canned_results.items():
            if key in q_lower:
                return results[:limit]
        return []

    async def close(self) -> None:
        """No-op cleanup."""
        pass

