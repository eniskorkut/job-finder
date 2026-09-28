"""Per-user LLM metrics.

Recording must never break the pipeline, so writes happen in their own short
transaction and every failure is swallowed after a log line. The shared API
key is never stored (only the model name and provider side numbers).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.integrations.deepseek import LlmCallInfo
from app.models.enums import ErrorClass
from app.models.llm import LlmUsage

logger = logging.getLogger("jobhunter.llm.metrics")


class LlmUsageRecorder:
    def __init__(self, *, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def record(
        self,
        *,
        user_id: uuid.UUID,
        purpose: str,
        status: str,
        model: str | None = None,
        job_id: uuid.UUID | None = None,
        info: LlmCallInfo | None = None,
        attempt: int = 1,
        error_class: ErrorClass | str | None = None,
        error_message: str | None = None,
    ) -> None:
        try:
            with self.session_factory() as session:
                session.add(
                    LlmUsage(
                        user_id=user_id,
                        job_id=job_id,
                        purpose=purpose,
                        status=status,
                        model=model or (info.model if info else None),
                        prompt_tokens=info.prompt_tokens if info else None,
                        completion_tokens=info.completion_tokens if info else None,
                        total_tokens=info.total_tokens if info else None,
                        latency_ms=info.latency_ms if info else None,
                        attempt=attempt,
                        error_class=(
                            error_class.value
                            if isinstance(error_class, ErrorClass)
                            else error_class
                        ),
                        error_message=(error_message or None) and error_message[:300],
                    )
                )
                session.commit()
        except Exception as exc:  # pragma: no cover - never break scoring
            logger.warning("LLM metrik kaydı yazılamadı: %s", type(exc).__name__)

    def summary_for_user(self, user_id: uuid.UUID, *, days: int = 30) -> dict:
        from datetime import timedelta

        since = datetime.now(timezone.utc) - timedelta(days=days)
        with self.session_factory() as session:
            rows = session.execute(
                select(
                    LlmUsage.status,
                    func.count(LlmUsage.id),
                    func.avg(LlmUsage.latency_ms),
                    func.sum(LlmUsage.total_tokens),
                )
                .where(LlmUsage.user_id == user_id, LlmUsage.created_at >= since)
                .group_by(LlmUsage.status)
            ).all()
        result = {
            "window_days": days,
            "requests": 0,
            "success": 0,
            "failed": 0,
            "invalid": 0,
            "avg_latency_ms": None,
            "tokens": None,
        }
        latencies: list[float] = []
        tokens = 0
        for status, count, avg_latency, total_tokens in rows:
            count = int(count or 0)
            result["requests"] += count
            if status in result:
                result[status] = count
            if avg_latency:
                latencies.extend([float(avg_latency)] * count)
            tokens += int(total_tokens or 0)
        if latencies:
            result["avg_latency_ms"] = round(sum(latencies) / len(latencies))
        if tokens:
            result["tokens"] = tokens
        return result
