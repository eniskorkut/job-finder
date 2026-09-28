"""Smoke test for OpenCode Go DeepSeek integration.

Verifies:
POST https://opencode.ai/zen/go/v1/chat/completions
headers:
- Authorization: Bearer <DEEPSEEK_API_KEY>
- Content-Type: application/json
- User-Agent: job-finder/1.0
- x-opencode-session: sabit non-secret UUID
body:
{
  "model": "deepseek-v4.1-flash",
  "messages": [{"role":"user","content":"Reply only with OK"}],
  "max_tokens": 50
}
"""

from __future__ import annotations

import uuid
import httpx
import pytest

from app.core.config import settings
from app.integrations.deepseek import (
    DeepSeekScoringClient,
    build_chat_completions_url,
    build_scoring_session_id,
    clean_model_name,
    run_opencode_smoke_test,
)


def test_clean_model_name():
    assert clean_model_name("opencode-go/deepseek-v4.1-flash") == "deepseek-v4.1-flash"
    assert clean_model_name("deepseek-v4.1-flash") == "deepseek-v4.1-flash"
    assert clean_model_name("  opencode-go/deepseek-v4-flash  ") == "deepseek-v4-flash"


def test_build_scoring_session_id_is_deterministic_and_valid_uuid():
    sid1 = build_scoring_session_id(user_id="user-123", job_id="job-456", cv_checksum="abc123def")
    sid2 = build_scoring_session_id(user_id="user-123", job_id="job-456", cv_checksum="abc123def")
    assert sid1 == sid2
    # Verify it is a valid UUID
    parsed = uuid.UUID(sid1)
    assert str(parsed) == sid1

    # Changing any component changes the session id
    sid3 = build_scoring_session_id(user_id="user-123", job_id="job-999", cv_checksum="abc123def")
    assert sid1 != sid3


def test_endpoint_resolution_avoids_responses_api():
    assert (
        build_chat_completions_url("https://opencode.ai/zen/go/v1")
        == "https://opencode.ai/zen/go/v1/chat/completions"
    )
    assert (
        build_chat_completions_url("https://opencode.ai/zen/go/v1/responses")
        == "https://opencode.ai/zen/go/v1/chat/completions"
    )
    assert (
        build_chat_completions_url("https://opencode.ai/zen/go/v1/chat/completions")
        == "https://opencode.ai/zen/go/v1/chat/completions"
    )


def test_request_headers_include_mandatory_opencode_session():
    client = DeepSeekScoringClient(
        api_key="sk-testkey",
        base_url="https://opencode.ai/zen/go/v1",
        model="deepseek-v4.1-flash",
    )
    headers = client.request_headers()
    assert headers["Authorization"] == "Bearer sk-testkey"
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"] == "job-finder/1.0"
    assert "x-opencode-session" in headers
    # Verify session is a valid UUID
    uuid.UUID(headers["x-opencode-session"])


@pytest.mark.asyncio
async def test_smoke_contract_mocked():
    seen_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_request["url"] = str(request.url)
        seen_request["headers"] = dict(request.headers)
        import json
        seen_request["json"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": "deepseek-v4.1-flash",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "OK"},
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            },
        )

    fixed_sid = "00000000-0000-0000-0000-000000000001"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        endpoint = "https://opencode.ai/zen/go/v1/chat/completions"
        headers = {
            "Authorization": "Bearer sk-test",
            "Content-Type": "application/json",
            "User-Agent": "job-finder/1.0",
            "x-opencode-session": fixed_sid,
        }
        body = {
            "model": "deepseek-v4.1-flash",
            "messages": [{"role": "user", "content": "Reply only with OK"}],
            "max_tokens": 50,
        }
        resp = await mock_client.post(endpoint, headers=headers, json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "OK"

    assert seen_request["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert seen_request["headers"]["authorization"] == "Bearer sk-test"
    assert seen_request["headers"]["content-type"] == "application/json"
    assert seen_request["headers"]["user-agent"] == "job-finder/1.0"
    assert seen_request["headers"]["x-opencode-session"] == fixed_sid
    assert seen_request["json"]["model"] == "deepseek-v4.1-flash"
    assert seen_request["json"]["max_tokens"] == 50


def _resolve_real_key() -> str:
    key = settings.deepseek_api_key
    if key:
        return key
    from app.core.config import BACKEND_DIR
    env_local = BACKEND_DIR / ".env.local"
    if env_local.exists():
        text = env_local.read_text()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("CV_LLM_API_KEY="):
                return line.split("=", 1)[1].strip()
            if line.startswith("DEEPSEEK_API_KEY=") and not line.startswith("DEEPSEEK_API_KEY=${"):
                return line.split("=", 1)[1].strip()
    return ""


@pytest.mark.asyncio
async def test_live_opencode_go_smoke():
    """Live smoke test executed against the OpenCode Go Chat Completions endpoint.

    Must succeed with 200 OK and choices content == 'OK'.
    """
    key = _resolve_real_key()
    if not key:
        pytest.skip("DEEPSEEK_API_KEY is not configured in environment or .env.local.")

    result = await run_opencode_smoke_test(
        api_key=key,
        base_url="https://opencode.ai/zen/go/v1",
        session_id="00000000-0000-0000-0000-000000000001",
    )
    assert isinstance(result, dict)
    choices = result.get("choices") or []
    assert len(choices) > 0
    message = choices[0].get("message") or {}
    assert "OK" in (message.get("content") or "")
