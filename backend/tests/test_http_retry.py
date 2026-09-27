"""Outbound HTTP policy: retries, Retry-After, host allowlist, error classes."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.errors import (
    DisallowedHostError,
    ProviderAuthError,
    ProviderError,
)
from app.integrations.http import (
    ProviderHttpClient,
    assert_allowed_host,
    backoff_delay,
    parse_retry_after,
)
from app.models.enums import ErrorClass

GRAPH = ["graph.microsoft.com"]


class SleepRecorder:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def make_client(handler, recorder: SleepRecorder, **kwargs) -> ProviderHttpClient:
    return ProviderHttpClient(
        transport=httpx.MockTransport(handler),
        sleep=recorder,
        max_attempts=kwargs.pop("max_attempts", 3),
        base_delay=1.0,
        max_delay=5.0,
        **kwargs,
    )


def test_parse_retry_after():
    assert parse_retry_after("2") == 2.0
    assert parse_retry_after("0.5") == 0.5
    assert parse_retry_after(None) is None
    assert parse_retry_after("soon") is None
    # Never sleep for an absurd amount just because a server said so.
    assert parse_retry_after("99999") == 300.0


def test_backoff_is_jittered_and_bounded():
    delays = [backoff_delay(attempt, base=1.0, maximum=4.0) for attempt in range(1, 8)]
    assert all(0 <= delay <= 4.0 for delay in delays)
    assert len(set(delays)) > 1  # jitter
    assert delays[0] <= 1.0


@pytest.mark.asyncio
async def test_retry_after_is_honoured_on_429():
    recorder = SleepRecorder()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json={"value": []})

    client = make_client(handler, recorder)
    async with client:
        response = await client.request(
            "GET", "https://graph.microsoft.com/v1.0/me", provider="outlook", allowed_hosts=GRAPH
        )
    assert response.status_code == 200
    assert recorder.waits == [2.0]


@pytest.mark.asyncio
async def test_server_errors_are_retried_then_raised():
    recorder = SleepRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    client = make_client(handler, recorder)
    async with client:
        with pytest.raises(ProviderError) as exc:
            await client.request(
                "GET", "https://graph.microsoft.com/v1.0/me", provider="outlook", allowed_hosts=GRAPH
            )
    assert exc.value.error_class == ErrorClass.TRANSIENT
    assert exc.value.status_code == 503
    assert len(recorder.waits) == 2  # attempts - 1


@pytest.mark.asyncio
async def test_transport_errors_are_retried():
    recorder = SleepRecorder()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, recorder)
    async with client:
        payload = await client.request_json(
            "GET", "https://graph.microsoft.com/v1.0/me", provider="outlook", allowed_hosts=GRAPH
        )
    assert payload == {"ok": True}
    assert len(recorder.waits) == 1


@pytest.mark.asyncio
async def test_auth_errors_are_not_retried():
    recorder = SleepRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    client = make_client(handler, recorder)
    async with client:
        with pytest.raises(ProviderAuthError):
            await client.request(
                "GET", "https://graph.microsoft.com/v1.0/me", provider="outlook", allowed_hosts=GRAPH
            )
    assert recorder.waits == []


@pytest.mark.asyncio
async def test_unexpected_status_is_permanent():
    recorder = SleepRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    client = make_client(handler, recorder)
    async with client:
        with pytest.raises(ProviderError) as exc:
            await client.request(
                "GET", "https://graph.microsoft.com/v1.0/me", provider="outlook", allowed_hosts=GRAPH
            )
    assert exc.value.error_class == ErrorClass.PERMANENT
    assert exc.value.retryable is False


class TestHostAllowlist:
    def test_allows_provider_host_and_subdomains(self):
        assert assert_allowed_host("https://graph.microsoft.com/v1.0/me", GRAPH, provider="outlook")
        assert assert_allowed_host(
            "https://sub.graph.microsoft.com/x", GRAPH, provider="outlook"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/steal",
            "http://graph.microsoft.com/insecure",
            "https://graph.microsoft.com.evil.example.com/x",
            "https:///no-host",
        ],
    )
    def test_rejects_everything_else(self, url: str):
        with pytest.raises(DisallowedHostError):
            assert_allowed_host(url, GRAPH, provider="outlook")

    @pytest.mark.asyncio
    async def test_token_is_never_sent_to_a_foreign_host(self):
        recorder = SleepRecorder()
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            seen.append(str(request.url))
            return httpx.Response(200, json={})

        client = make_client(handler, recorder)
        async with client:
            with pytest.raises(DisallowedHostError):
                await client.request(
                    "GET",
                    "https://attacker.example/next",
                    provider="outlook",
                    allowed_hosts=GRAPH,
                    headers={"Authorization": "Bearer secret-token"},
                )
        assert seen == []
