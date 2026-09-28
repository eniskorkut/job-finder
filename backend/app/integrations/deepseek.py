"""Shared LLM client (OpenAI-compatible chat completions).

DeepSeek's hosted API and OpenAI-compatible gateways (OpenCode, vLLM, LiteLLM)
all accept the same ``/chat/completions`` contract, so the provider is
described entirely by configuration: ``DEEPSEEK_API_KEY``,
``DEEPSEEK_BASE_URL``, ``DEEPSEEK_MODEL``. Nothing is hardcoded, and the key
never leaves the backend.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.integrations.base import JobScoringClient
from app.integrations.errors import ProviderError
from app.integrations.http import ProviderHttpClient
from app.integrations.prompts import (
    PROFILE_SYSTEM_PROMPT,
    PROMPT_VERSION,
    REPAIR_INSTRUCTION,
    SCORING_SYSTEM_PROMPT,
    build_profile_user_message,
    build_scoring_user_message,
)
from app.models.enums import ErrorClass
from app.schemas.llm import (
    LlmCVProfile,
    LlmMatchResult,
    LlmOutputError,
    extract_json_object,
)

logger = logging.getLogger("jobhunter.llm")

T = TypeVar("T", bound=BaseModel)


def build_chat_completions_url(base_url: str) -> str:
    """Resolve an OpenAI-compatible chat completions endpoint.

    Accepts a base URL with or without a trailing ``/v1`` and a full endpoint
    URL, so a misconfigured deployment cannot silently produce a bad path.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("LLM base URL tanımlı değil.")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def llm_host_allowlist(base_url: str) -> list[str]:
    host = (urlsplit(base_url or "").hostname or "").lower()
    return [host] if host else []


@dataclass(slots=True)
class LlmCallInfo:
    model: str
    latency_ms: int
    attempts: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(slots=True)
class LlmCall:
    data: dict[str, Any]
    info: LlmCallInfo


class LlmConcurrencyGate:
    """Process wide limit on simultaneous LLM calls.

    Kept separate from mailbox concurrency so a slow model never starves mail
    scanning (and vice versa). One semaphore per event loop keeps it safe for
    both the API process and the worker.
    """

    def __init__(self, limit: int | None = None) -> None:
        self.limit = max(1, limit or settings.llm_max_concurrency)
        self._semaphores: dict[int, asyncio.Semaphore] = {}

    def _semaphore(self) -> asyncio.Semaphore:
        key = id(asyncio.get_running_loop())
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(self.limit)
        return self._semaphores[key]

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        semaphore = self._semaphore()
        await semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()


llm_gate = LlmConcurrencyGate()


class DeepSeekScoringClient(JobScoringClient):
    """Async client for structured CV/profile and CV/job scoring calls."""

    provider = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool | None = None,
        prompt_version: str | None = None,
        http: ProviderHttpClient | None = None,
        gate: LlmConcurrencyGate | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.deepseek_api_key).strip()
        self.base_url = (base_url if base_url is not None else settings.deepseek_base_url).strip()
        self.model = (model if model is not None else settings.deepseek_model).strip()
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
        )
        self.max_attempts = (
            max_attempts if max_attempts is not None else settings.llm_retry_max_attempts
        )
        self.max_tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.json_mode = settings.llm_json_mode if json_mode is None else json_mode
        self.prompt_version = prompt_version or PROMPT_VERSION
        self._http = http
        self._owns_http = http is None
        self._gate = gate or llm_gate
        self._json_mode_supported = self.json_mode
        self._json_mode_checked = False

    # --- lifecycle ------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    @property
    def endpoint(self) -> str:
        return build_chat_completions_url(self.base_url)

    @property
    def allowed_hosts(self) -> list[str]:
        return llm_host_allowlist(self.base_url)

    async def __aenter__(self) -> "DeepSeekScoringClient":
        if self._http is None:
            self._http = ProviderHttpClient(
                timeout=self.timeout_seconds,
                max_attempts=self.max_attempts,
            )
            self._owns_http = True
        if not self._http.is_open:
            await self._http.__aenter__()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._http is not None and self._http.is_open:
            await self._http.__aexit__()
            self._http = None

    @property
    def http(self) -> ProviderHttpClient:
        if self._http is None:
            raise RuntimeError("LLM istemcisi async with ile açılmalı.")
        return self._http

    def describe(self) -> dict:
        """Safe summary for the UI/API: never includes the key."""
        host = (urlsplit(self.base_url or "").hostname or "") or None
        return {
            "provider": self.provider,
            "configured": self.configured,
            "shared": True,
            "model": self.model or None,
            "endpoint_host": host,
            "endpoint_path": urlsplit(self.endpoint).path if self.base_url else None,
            "prompt_version": self.prompt_version,
            "json_mode": bool(self._json_mode_supported),
            "max_concurrency": self._gate.limit,
            "enabled": self.configured,
        }

    # --- transport ------------------------------------------------------
    async def _chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, LlmCallInfo, int]:
        if not self.configured:
            raise ProviderError(
                "LLM yapılandırılmadı (DEEPSEEK_API_KEY / BASE_URL / MODEL eksik).",
                provider=self.provider,
                error_class=ErrorClass.PERMANENT,
                retryable=False,
            )

        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if self._json_mode_supported:
            body["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        async with self._gate.slot():
            response = await self.http.request(
                "POST",
                self.endpoint,
                provider=self.provider,
                allowed_hosts=self.allowed_hosts,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json_body=body,
                expected=(200, 400),
            )
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code == 400 and self._json_mode_supported:
            # Some gateways reject response_format: remember that and retry.
            logger.warning("LLM response_format desteklenmiyor; JSON modu kapatıldı.")
            self._json_mode_supported = False
            self._json_mode_checked = True
            body.pop("response_format", None)
            started = time.monotonic()
            async with self._gate.slot():
                response = await self.http.request(
                    "POST",
                    self.endpoint,
                    provider=self.provider,
                    allowed_hosts=self.allowed_hosts,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json_body=body,
                    expected=(200,),
                )
            latency_ms = int((time.monotonic() - started) * 1000)

        payload = response.json() if response.content else {}
        if not isinstance(payload, dict):
            payload = {}

        usage = payload.get("usage") or {}
        choices = payload.get("choices") or []
        content = ""
        finish_reason = None
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "")
            finish_reason = choices[0].get("finish_reason")

        info = LlmCallInfo(
            model=str(payload.get("model") or self.model),
            latency_ms=latency_ms,
            attempts=self.max_attempts,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=str(finish_reason) if finish_reason else None,
        )

        if not content.strip():
            raise LlmOutputError("Model boş içerik döndürdü.")
        return content, info, latency_ms

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int | None = None,
    ) -> tuple[T, LlmCallInfo]:
        """Call the model and validate its JSON, with a single repair attempt."""
        content, info, _ = await self._chat(system=system, user=user, max_tokens=max_tokens)
        validation_error = ""
        try:
            return schema.model_validate(extract_json_object(content)), info
        except (LlmOutputError, ValidationError) as first_error:
            # Python clears the exception variable after the except block, so
            # keep a plain copy for the repair prompt.
            validation_error = f"{type(first_error).__name__}: {first_error}"
            logger.info(
                "LLM çıktısı doğrulanamadı (%s); tek onarım denemesi yapılıyor.",
                type(first_error).__name__,
            )

        repair_user = (
            f"{user}\n\n{REPAIR_INSTRUCTION}\n"
            f"Doğrulama hatası: {validation_error[:300]}"
        )
        content, info, _ = await self._chat(system=system, user=repair_user, max_tokens=max_tokens)
        try:
            return schema.model_validate(extract_json_object(content)), info
        except (LlmOutputError, ValidationError) as second_error:
            raise LlmOutputError(
                f"LLM yanıtı iki denemede de şemaya uymadı: {type(second_error).__name__}",
                raw=content,
            ) from second_error

    # --- use cases ------------------------------------------------------
    async def extract_cv_profile(self, *, cv_text: str) -> tuple[LlmCVProfile, LlmCallInfo]:
        return await self.complete_json(
            system=PROFILE_SYSTEM_PROMPT,
            user=build_profile_user_message(cv_text=cv_text),
            schema=LlmCVProfile,
            max_tokens=min(self.max_tokens, 900),
        )

    async def score_job(
        self,
        *,
        candidate_profile: dict,
        cv_excerpt: str,
        job_title: str,
        company: str,
        location: str | None,
        work_mode: str,
        description: str | None,
        description_status: str,
        preferences: dict,
    ) -> tuple[LlmMatchResult, LlmCallInfo]:
        return await self.complete_json(
            system=SCORING_SYSTEM_PROMPT,
            user=build_scoring_user_message(
                candidate_profile=candidate_profile,
                cv_excerpt=cv_excerpt,
                job_title=job_title,
                company=company,
                location=location,
                work_mode=work_mode,
                description=description,
                description_status=description_status,
                preferences=preferences,
            ),
            schema=LlmMatchResult,
        )


__all__ = [
    "DeepSeekScoringClient",
    "LlmCall",
    "LlmCallInfo",
    "LlmConcurrencyGate",
    "build_chat_completions_url",
    "llm_gate",
    "llm_host_allowlist",
]
