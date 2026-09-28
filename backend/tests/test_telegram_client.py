"""Telegram client + message rendering, with no network access."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.core.logging import SecretRedactingFilter, install_secret_filter, redact
from app.integrations.http import ProviderHttpClient
from app.integrations.telegram import TelegramClient, TelegramError
from app.models.enums import ErrorClass, WorkMode

TOKEN = "123456789:AAHfake-token-abcdefghijklmnop"
CHAT_ID = "424242"


def make_client(handler, *, max_attempts: int = 3) -> TelegramClient:
    http = ProviderHttpClient(
        transport=httpx.MockTransport(handler),
        max_attempts=max_attempts,
        base_delay=0.01,
        max_delay=0.02,
    )
    return TelegramClient(bot_token=TOKEN, http=http, max_attempts=max_attempts)


def ok(result: dict) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": result})


class TestTelegramClient:
    async def test_get_me_and_chat(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/getMe"):
                return ok({"id": 1, "username": "jobhunter_bot", "first_name": "JH"})
            return ok({"id": int(CHAT_ID), "type": "private", "username": "enis"})

        client = make_client(handler)
        async with client:
            me = await client.verify()
            chat = await client.get_chat(chat_id=CHAT_ID)
        assert me["username"] == "jobhunter_bot"
        assert chat["id"] == int(CHAT_ID)

    async def test_invalid_token_is_an_auth_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
            )

        client = make_client(handler)
        async with client:
            with pytest.raises(TelegramError) as exc:
                await client.get_me()
        assert exc.value.reason == "invalid_token"
        assert exc.value.error_class == ErrorClass.AUTH
        assert exc.value.retryable is False

    async def test_invalid_chat_is_permanent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "ok": False,
                    "error_code": 400,
                    "description": "Bad Request: chat not found",
                },
            )

        client = make_client(handler)
        async with client:
            with pytest.raises(TelegramError) as exc:
                await client.get_chat(chat_id="999")
        assert exc.value.reason == "invalid_chat"
        assert exc.value.error_class == ErrorClass.PERMANENT

    async def test_bot_blocked_is_an_auth_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "ok": False,
                    "error_code": 403,
                    "description": "Forbidden: bot was blocked by the user",
                },
            )

        client = make_client(handler)
        async with client:
            with pytest.raises(TelegramError) as exc:
                await client.send_message(chat_id=CHAT_ID, text="merhaba")
        assert exc.value.reason == "bot_blocked"
        assert exc.value.error_class == ErrorClass.AUTH

    async def test_rate_limit_exposes_retry_after(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={
                    "ok": False,
                    "error_code": 429,
                    "description": "Too Many Requests: retry after 7",
                    "parameters": {"retry_after": 7},
                },
            )

        client = make_client(handler)
        async with client:
            with pytest.raises(TelegramError) as exc:
                await client.send_message(chat_id=CHAT_ID, text="x")
        assert exc.value.reason == "rate_limited"
        assert exc.value.error_class == ErrorClass.RATE_LIMIT
        assert exc.value.retry_after == 7.0

    async def test_server_error_is_transient_and_retried(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(502, json={"ok": False, "description": "Bad Gateway"})

        client = make_client(handler)
        async with client:
            with pytest.raises(TelegramError) as exc:
                await client.send_message(chat_id=CHAT_ID, text="x")
        assert calls["n"] == 3
        assert exc.value.error_class == ErrorClass.TRANSIENT

    async def test_message_is_truncated_to_the_configured_limit(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "telegram_max_message_chars", 50)
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured.update(json.loads(request.content.decode()))
            return ok({"message_id": 5})

        client = make_client(handler)
        async with client:
            await client.send_message(chat_id=CHAT_ID, text="a" * 500)
        assert len(captured["text"]) == 50
        assert captured["parse_mode"] == "HTML"

    async def test_token_never_appears_in_errors_or_masking(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={})

        client = make_client(handler)
        async with client:
            with pytest.raises(TelegramError) as exc:
                await client.get_me()
        assert TOKEN not in str(exc.value)
        assert client.masked_token.startswith("123456789")
        assert TOKEN not in client.masked_token
        assert TOKEN not in str(client.describe())

    def test_invalid_token_format_is_rejected_locally(self):
        with pytest.raises(TelegramError) as exc:
            TelegramClient(bot_token="bozuk-token")
        assert exc.value.reason == "invalid_token"


class TestLogRedaction:
    def test_redacts_bot_token_in_log_urls(self):
        line = f"GET https://api.telegram.org/bot{TOKEN}/getMe"
        assert TOKEN not in redact(line)
        assert "bot<redacted>" in redact(line)

    def test_filter_rewrites_records(self):
        install_secret_filter()
        captured: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        logger = logging.getLogger("httpx")
        # A migration run inside the test session may have disabled existing
        # loggers before this test; re-enable explicitly.
        logger.disabled = False
        previous_level = logger.level
        handler = Capture()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info(
                "HTTP Request: GET https://api.telegram.org/bot%s/getMe", TOKEN
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        message = captured[0].getMessage()
        assert captured
        assert TOKEN not in message
        # Either marker is fine: the token may be split across msg/args.
        assert "redacted" in message

    def test_filter_handles_dict_args(self):
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="url=%(url)s",
            args=({"url": f"https://api.telegram.org/bot{TOKEN}/getMe"},),
            exc_info=None,
        )
        assert SecretRedactingFilter().filter(record) is True
        assert TOKEN not in record.args["url"]
        assert "bot<redacted>" in record.getMessage()


class TestMessageRendering:
    def _job_match(self, **overrides):
        class Job:
            title = "AI Engineer <script>"
            company = "NovaTech & Co"
            location = "İstanbul"
            work_mode = WorkMode.HYBRID.value
            url = "https://www.linkedin.com/jobs/view/1"
            is_mock = False

        class Match:
            score = 88
            confidence = 76
            matched_skills = ["Python", "FastAPI", "RAG"]
            missing_skills = ["Kubernetes"]
            rationale = "CV ilanın gereksinimlerini karşılıyor. " * 30
            insufficient_information = False

        for key, value in overrides.items():
            setattr(Match, key, value)
        return Job(), Match()

    def test_message_is_escaped_short_and_disclaimed(self):
        from app.services.telegram_message import build_match_message

        job, match = self._job_match()
        message = build_match_message(job=job, match=match, score_threshold=70)
        assert "&lt;script&gt;" in message
        assert "NovaTech &amp; Co" in message
        assert "%88" in message
        assert "Eşik: %70" in message
        assert "işe alınma ihtimali değildir" in message
        assert len(message) <= 3500

    def test_long_rationale_is_truncated(self):
        from app.services.telegram_message import build_match_message

        job, match = self._job_match()
        message = build_match_message(job=job, match=match)
        assert "…" in message
        assert len(message) < 1200

    def test_non_https_link_is_not_clickable(self):
        from app.services.telegram_message import build_match_message

        job, match = self._job_match()
        job.url = "http://insecure.example/job"
        message = build_match_message(job=job, match=match)
        assert "insecure.example" not in message

    def test_insufficient_information_is_flagged(self):
        from app.services.telegram_message import build_match_message

        job, match = self._job_match(insufficient_information=True)
        message = build_match_message(job=job, match=match)
        assert "İlan metni kısıtlı" in message
