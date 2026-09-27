from __future__ import annotations

from app.core.config import settings
from app.integrations.base import (
    DeepSeekClient,
    IntegrationNotImplemented,
    MatchScore,
)


class DeepSeekScoringClient(DeepSeekClient):
    """Shared (deployment wide) DeepSeek V4.1 Flash client - phase 3.

    Every user shares this client; per-user data isolation happens before the
    call because the caller passes the owner's CV and job description only.
    """

    provider = "deepseek"
    phase = "phase-3"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.deepseek_api_key
        self.base_url = base_url or settings.deepseek_base_url
        self.model = model or settings.deepseek_model
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def score_job(
        self, *, cv_text: str, job_title: str, job_description: str, preferences: dict
    ) -> MatchScore:
        raise IntegrationNotImplemented(self.provider, self.phase, "score_job")

    def extract_profile(self, *, cv_text: str) -> dict:
        raise IntegrationNotImplemented(self.provider, self.phase, "extract_profile")

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "configured": self.configured,
            "phase": self.phase,
            "shared": True,
        }
