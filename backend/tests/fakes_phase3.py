"""Test doubles for the phase 3 providers (never touch the network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.integrations.deepseek import LlmCallInfo
from app.integrations.telegram import TelegramError
from app.models.enums import ErrorClass
from app.schemas.llm import DimensionMatch, LlmCVProfile, LlmMatchResult

DEFAULT_PROFILE = {
    "skills": ["Python", "PyTorch", "FastAPI", "RAG"],
    "languages": ["Türkçe", "İngilizce"],
    "education": ["Bilgisayar Mühendisliği"],
    "experience": ["Kıdemli AI Engineer - 6 yıl"],
    "years_of_experience": 6.0,
    "technologies": ["pgvector", "Docker", "PostgreSQL"],
    "domains": ["LLM uygulamaları"],
    "certifications": [],
    "preferred_roles_from_cv": ["AI Engineer"],
}


def call_info(model: str = "fake-llm", *, latency_ms: int = 12) -> LlmCallInfo:
    return LlmCallInfo(
        model=model,
        latency_ms=latency_ms,
        attempts=1,
        prompt_tokens=120,
        completion_tokens=80,
        total_tokens=200,
        finish_reason="stop",
    )


def match_result(
    score: int = 88, *, confidence: int = 80, insufficient: bool = False
) -> LlmMatchResult:
    return LlmMatchResult(
        match_score=score,
        confidence=confidence,
        matched_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        experience_match=DimensionMatch(status="match", reason="6 yıl deneyim uyuyor"),
        location_match=DimensionMatch(status="partial", reason="Şehir farklı ama hibrit"),
        work_mode_match=DimensionMatch(status="match", reason="Hibrit tercihle uyumlu"),
        title_match=DimensionMatch(status="match", reason="Başlık örtüşüyor"),
        reasoning="CV ilanın temel gereksinimlerini karşılıyor.",
        insufficient_information=insufficient,
    )


@dataclass
class FakeLlmState:
    profile: dict = field(default_factory=lambda: dict(DEFAULT_PROFILE))
    # Optional resolvers let one fake serve several users (see the E2E test).
    profile_resolver: object = None
    score_resolver: object = None
    score_by_title: dict[str, int] = field(default_factory=dict)
    default_score: int = 80
    confidence: int = 80
    profile_error: Exception | None = None
    score_error: Exception | None = None
    score_errors_by_title: dict[str, Exception] = field(default_factory=dict)
    profile_calls: int = 0
    score_calls: list[dict] = field(default_factory=list)
    model: str = "fake-llm"
    prompt_version: str = "phase3-v1"


class FakeLlmClient:
    """Mimics DeepSeekScoringClient without any HTTP."""

    provider = "deepseek"

    def __init__(self, state: FakeLlmState | None = None) -> None:
        self.state = state or FakeLlmState()
        self.model = self.state.model
        self.prompt_version = self.state.prompt_version
        self.entered = False

    @property
    def configured(self) -> bool:
        return True

    async def __aenter__(self) -> "FakeLlmClient":
        self.entered = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.entered = False

    def describe(self) -> dict:
        return {
            "provider": "deepseek",
            "configured": True,
            "shared": True,
            "model": self.model,
            "endpoint_host": "fake.local",
            "prompt_version": self.prompt_version,
            "json_mode": True,
            "max_concurrency": 3,
            "enabled": True,
        }

    async def extract_cv_profile(self, *, cv_text: str):
        self.state.profile_calls += 1
        if self.state.profile_error is not None:
            raise self.state.profile_error
        payload = self.state.profile
        if callable(self.state.profile_resolver):
            payload = self.state.profile_resolver(cv_text)
        return LlmCVProfile.model_validate(payload), call_info(self.model)

    async def score_job(self, **kwargs):
        self.state.score_calls.append(kwargs)
        title = kwargs.get("job_title") or ""
        error = self.state.score_errors_by_title.get(title) or self.state.score_error
        if error is not None:
            raise error
        if callable(self.state.score_resolver):
            score = int(
                self.state.score_resolver(
                    kwargs.get("candidate_profile") or {}, title
                )
            )
        else:
            score = self.state.score_by_title.get(title, self.state.default_score)
        return (
            match_result(score, confidence=self.state.confidence),
            call_info(self.model),
        )


def fake_llm_factory(state: FakeLlmState):
    return lambda: FakeLlmClient(state)


# ----------------------------------------------------------------------
@dataclass
class FakeTelegramState:
    bot_username: str = "jobhunter_test_bot"
    bot_id: int = 123456789
    chats: dict[str, dict] = field(default_factory=dict)
    updates: list[dict] = field(default_factory=list)
    send_error: TelegramError | None = None
    send_errors_by_chat: dict[str, TelegramError] = field(default_factory=dict)
    sent: list[dict] = field(default_factory=list)
    token: str = "123456789:FAKE-token-value"

    def register_chat(self, chat_id: str, *, title: str = "Test Kullanıcı") -> None:
        self.chats[str(chat_id)] = {
            "id": int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id,
            "type": "private",
            "first_name": title,
            "username": "testuser",
        }


class FakeTelegramClient:
    def __init__(self, token: str, state: FakeTelegramState) -> None:
        if not token or ":" not in token:
            raise TelegramError("invalid_token", error_class=ErrorClass.AUTH)
        self.token = token
        self.state = state

    async def __aenter__(self) -> "FakeTelegramClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def verify(self) -> dict:
        return {
            "id": self.state.bot_id,
            "username": self.state.bot_username,
            "first_name": "Job Hunter",
        }

    async def get_me(self) -> dict:
        return await self.verify()

    async def get_chat(self, *, chat_id: str) -> dict:
        chat = self.state.chats.get(str(chat_id))
        if chat is None:
            raise TelegramError(
                "invalid_chat", error_class=ErrorClass.PERMANENT, status_code=400
            )
        return chat

    async def get_updates(self, *, limit: int = 20, timeout: int = 0) -> list[dict]:
        return list(self.state.updates[:limit])

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> dict:
        error = self.state.send_errors_by_chat.get(str(chat_id)) or self.state.send_error
        if error is not None:
            raise error
        if str(chat_id) not in self.state.chats:
            raise TelegramError(
                "invalid_chat", error_class=ErrorClass.PERMANENT, status_code=400
            )
        self.state.sent.append({"chat_id": str(chat_id), "text": text})
        return {"message_id": len(self.state.sent), "chat": {"id": chat_id}}

    def describe(self) -> dict:
        return {"provider": "telegram", "configured": True, "token_hint": "123456789…alue"}


def fake_telegram_factory(state: FakeTelegramState):
    return lambda token: FakeTelegramClient(token, state)


def update_with_message(chat_id: str, *, title: str = "Test Kullanıcı", message_id: int = 1) -> dict:
    return {
        "update_id": message_id,
        "message": {
            "message_id": message_id,
            "date": int(datetime.now(timezone.utc).timestamp()),
            "chat": {
                "id": int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id,
                "type": "private",
                "first_name": title,
            },
            "from": {"id": 42, "username": "testuser"},
            "text": "/start",
        },
    }


__all__ = [
    "DEFAULT_PROFILE",
    "FakeLlmClient",
    "FakeLlmState",
    "FakeTelegramClient",
    "FakeTelegramState",
    "call_info",
    "fake_llm_factory",
    "fake_telegram_factory",
    "match_result",
    "timedelta",
    "update_with_message",
]
