"""Health and configuration verification for SearXNG search engine."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("jobhunter.web_search.health")


async def check_searxng_health(
    base_url: str | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Non-blocking status check for SearXNG JSON API endpoint.

    Queries ``/search?q=test&format=json`` with a short timeout.
    Returns status dictionary and never blocks application startup.
    """
    target_url = (base_url or settings.web_search_searxng_url).rstrip("/")
    endpoint = f"{target_url}/search?q=test&format=json"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                endpoint,
                headers={"Accept": "application/json", "User-Agent": "JobHunter-HealthCheck/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results_count = len(data.get("results", []))
                return {
                    "status": "healthy",
                    "url": target_url,
                    "http_status": 200,
                    "results_count": results_count,
                    "available": True,
                }
            return {
                "status": "degraded",
                "url": target_url,
                "http_status": resp.status_code,
                "error": f"SearXNG returned HTTP {resp.status_code}",
                "available": False,
            }
    except Exception as exc:
        logger.debug("SearXNG health check unreachable (%s): %s", target_url, exc)
        return {
            "status": "unavailable",
            "url": target_url,
            "error": str(exc),
            "available": False,
        }
