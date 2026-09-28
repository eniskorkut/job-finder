"""Worker side of the scoring pipeline.

Design notes:

* one LLM client (and therefore one connection pool) per job run,
* the CV profile is resolved once per run and reused for every posting,
* each item is an isolated unit: its failure is recorded on the item and the
  match, and never stops the other postings or the mail scan checkpoint,
* DB sessions are opened per step, never held across a network call,
* claiming an item is atomic, so the same (job, cv version) is never analysed
  twice concurrently.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.deepseek import DeepSeekScoringClient
from app.integrations.errors import ProviderError
from app.integrations.prompts import PROMPT_VERSION
from app.models.cv import CV
from app.models.enums import ErrorClass, SyncJobStatus
from app.models.job import Job, JobMatch
from app.models.sync_job import ScoringItem, SyncJob
from app.models.user import User
from app.repositories.jobs import JobRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.sync_jobs import ScoringItemRepository, SyncJobRepository
from app.schemas.llm import LlmOutputError
from app.services.cv_privacy import redact_job_text
from app.services.llm_metrics import LlmUsageRecorder
from app.services.profile_service import CVProfileService
from app.services.scoring_service import (
    ANALYSIS_COMPLETED,
    ANALYSIS_FAILED,
    ANALYSIS_RUNNING,
    ANALYSIS_SKIPPED,
)

logger = logging.getLogger("jobhunter.scoring")

MIN_PROFILE_TEXT_CHARS = 40
OUTCOME_ANALYZED = "analyzed"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"


@dataclass(slots=True)
class ScoringOutcome:
    status: SyncJobStatus = SyncJobStatus.COMPLETED
    analyzed: int = 0
    failed: int = 0
    skipped: int = 0
    profile: str = "cached"
    error_message: str | None = None


def default_llm_factory() -> DeepSeekScoringClient:
    return DeepSeekScoringClient()


class ScoringRunner:
    def __init__(
        self,
        *,
        llm_factory: Callable[[], object] | None = None,
        session_factory=SessionLocal,
        usage_recorder: LlmUsageRecorder | None = None,
        max_concurrency: int | None = None,
        now: datetime | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.llm_factory = llm_factory or default_llm_factory
        self.session_factory = session_factory
        self.usage = usage_recorder or LlmUsageRecorder(session_factory=session_factory)
        self.max_concurrency = max(1, max_concurrency or settings.llm_max_concurrency)
        self._origin = now
        self._cancel_check = cancel_check

    # --- session helpers ------------------------------------------------
    @contextmanager
    def _db(self):
        session: Session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def _llm(self) -> AsyncIterator[object]:
        client = self.llm_factory()
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            yield client
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

    # --- entry point ----------------------------------------------------
    async def run(self, job_id: uuid.UUID) -> ScoringOutcome:
        with self._db() as db:
            job = db.get(SyncJob, job_id)
            if job is None:
                return ScoringOutcome(
                    status=SyncJobStatus.FAILED, error_message="İş bulunamadı."
                )
            user_id = job.user_id
            checksum = str((job.payload or {}).get("cv_checksum") or "") or None

        outcome = ScoringOutcome()
        async with self._llm() as client:
            profile, excerpt, profile_state, profile_error = await self._ensure_profile(
                client, user_id
            )
            outcome.profile = profile_state
            if profile is None:
                outcome.status = SyncJobStatus.FAILED
                outcome.error_message = profile_error or "CV profili oluşturulamadı."
                self._skip_remaining(job_id, reason=outcome.error_message)
                return outcome

            preferences = self._preferences(user_id)
            items = self._pending_items(job_id)
            if not items:
                return outcome

            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def worker(item_id: uuid.UUID) -> str:
                if self._cancel_check is not None and self._cancel_check():
                    return self._finish(
                        item_id,
                        status=ANALYSIS_SKIPPED,
                        error_class=ErrorClass.NONE,
                        error_message="Kullanıcı analizi iptal etti.",
                    )
                async with semaphore:
                    result = await self._score_item(
                        client=client,
                        item_id=item_id,
                        profile=profile,
                        excerpt=excerpt,
                        preferences=preferences,
                        checksum=checksum,
                    )
                    self._bump_progress(job_id, result)
                    return result

            results = await asyncio.gather(
                *(worker(item.id) for item in items), return_exceptions=True
            )

        for result in results:
            if isinstance(result, BaseException):
                logger.error("Skorlama görevi beklenmeyen hata: %s", type(result).__name__)
                outcome.failed += 1
            elif result == OUTCOME_ANALYZED:
                outcome.analyzed += 1
            elif result == OUTCOME_FAILED:
                outcome.failed += 1
            else:
                outcome.skipped += 1

        outcome.status = self._final_status(outcome)
        if outcome.status in {SyncJobStatus.FAILED, SyncJobStatus.PARTIAL_FAILED}:
            outcome.error_message = (
                f"{outcome.failed} ilan analiz edilemedi; ilan detayından tekrar "
                "değerlendirebilirsiniz."
            )
        return outcome

    # --- helpers --------------------------------------------------------
    def _preferences(self, user_id: uuid.UUID) -> dict:
        with self._db() as db:
            user = db.get(User, user_id)
            if user is None:
                return {}
            preference = PreferenceRepository(db).get_or_create(user)
            return {
                "desired_titles": list(preference.desired_titles or []),
                "locations": list(preference.locations or []),
                "work_modes": list(preference.work_modes or []),
                "keywords_include": list(preference.keywords_include or []),
                "keywords_exclude": list(preference.keywords_exclude or []),
                "min_match_score": preference.min_match_score,
            }

    def _pending_items(self, job_id: uuid.UUID) -> list[ScoringItem]:
        with self._db() as db:
            rows = ScoringItemRepository(db).pending_for_job(job_id)
            for row in rows:
                db.expunge(row)
        return rows

    def _bump_progress(self, job_id: uuid.UUID, result: str) -> None:
        key = {
            OUTCOME_ANALYZED: "analyzed",
            OUTCOME_FAILED: "failed",
            OUTCOME_SKIPPED: "skipped",
        }.get(result, "skipped")
        with self._db() as db:
            SyncJobRepository(db).update_progress(job_id, {key: 1})

    @staticmethod
    def _final_status(outcome: ScoringOutcome) -> SyncJobStatus:
        if outcome.analyzed and (outcome.failed or outcome.skipped):
            return SyncJobStatus.PARTIAL_FAILED
        if outcome.analyzed:
            return SyncJobStatus.COMPLETED
        if outcome.skipped and not outcome.failed:
            return SyncJobStatus.CANCELLED
        return SyncJobStatus.FAILED

    def _skip_remaining(self, job_id: uuid.UUID, *, reason: str) -> None:
        with self._db() as db:
            repo = ScoringItemRepository(db)
            pending = repo.pending_for_job(job_id)
            for item in pending:
                repo.mark_finished(
                    item,
                    status=ANALYSIS_SKIPPED,
                    error_class=ErrorClass.PERMANENT,
                    error_message=reason,
                )
            SyncJobRepository(db).update_progress(job_id, {"skipped": len(pending)})

    def _finish(
        self,
        item_id: uuid.UUID,
        *,
        status: str,
        error_class: ErrorClass | str | None = None,
        error_message: str | None = None,
        match_id: uuid.UUID | None = None,
    ) -> str:
        with self._db() as db:
            item = db.get(ScoringItem, item_id)
            if item is None:
                return OUTCOME_SKIPPED
            ScoringItemRepository(db).mark_finished(
                item,
                status=status,
                error_class=error_class,
                error_message=error_message,
                match_id=match_id,
            )
        return {
            "succeeded": OUTCOME_ANALYZED,
            "failed": OUTCOME_FAILED,
        }.get(status, OUTCOME_SKIPPED)

    # --- profile --------------------------------------------------------
    async def _ensure_profile(
        self, client: object, user_id: uuid.UUID
    ) -> tuple[dict | None, str, str, str | None]:
        with self._db() as db:
            user = db.get(User, user_id)
            if user is None:
                return None, "", "failed", "Kullanıcı bulunamadı."
            service = CVProfileService(db)
            cv = service.active_cv(user)
            if cv is None or not cv.extracted_text:
                return (
                    None,
                    "",
                    "failed",
                    "Aktif CV bulunamadı veya CV metni çıkarılmamış. "
                    "CV ve Tercihler ekranından PDF/DOCX yükleyin.",
                )
            cached = service.cached_profile(user)
            if cached is not None:
                return (
                    dict(cached.profile or {}),
                    service.scoring_context(cv),
                    "cached",
                    None,
                )
            text = service.profile_text(cv)
            excerpt = service.scoring_context(cv)
            cv_id = cv.id
            model = getattr(client, "model", None) or None

        if len(text) < MIN_PROFILE_TEXT_CHARS:
            return None, "", "failed", "CV metni profil çıkarmak için çok kısa."

        try:
            profile, info = await client.extract_cv_profile(cv_text=text)  # type: ignore[attr-defined]
        except (ProviderError, LlmOutputError) as exc:
            error_class = (
                exc.error_class if isinstance(exc, ProviderError) else ErrorClass.PERMANENT
            )
            self.usage.record(
                user_id=user_id,
                purpose="profile",
                status="failed",
                attempt=1,
                error_class=error_class,
                error_message=str(exc),
            )
            with self._db() as db:
                user = db.get(User, user_id)
                cv_row = db.get(CV, cv_id)
                if user is not None and cv_row is not None:
                    CVProfileService(db).mark_failed(user, cv_row, message=str(exc), model=model)
            logger.warning(
                "CV profili çıkarılamadı (user=%s, class=%s)", user_id, error_class
            )
            return None, "", "failed", str(exc)

        payload = profile.model_dump() if hasattr(profile, "model_dump") else dict(profile)
        with self._db() as db:
            user = db.get(User, user_id)
            cv_row = db.get(CV, cv_id)
            if user is None or cv_row is None:
                return None, "", "failed", "CV kaydı bulunamadı."
            CVProfileService(db).store(
                user,
                cv_row,
                payload,
                model=info.model,
                prompt_version=getattr(client, "prompt_version", PROMPT_VERSION),
            )
        self.usage.record(user_id=user_id, purpose="profile", status="success", info=info)
        logger.info(
            "CV profili üretildi (user=%s, model=%s, latency=%sms)",
            user_id,
            info.model,
            info.latency_ms,
        )
        return payload, excerpt, "generated", None

    # --- one posting ----------------------------------------------------
    async def _score_item(
        self,
        *,
        client: object,
        item_id: uuid.UUID,
        profile: dict,
        excerpt: str,
        preferences: dict,
        checksum: str | None,
    ) -> str:
        with self._db() as db:
            item = db.get(ScoringItem, item_id)
            if item is None:
                return OUTCOME_SKIPPED
            if not ScoringItemRepository(db).claim(item):
                # Somebody else already owns this (job, cv) pair.
                return OUTCOME_SKIPPED
            job = db.get(Job, item.job_id)
            if job is None:
                ScoringItemRepository(db).mark_finished(
                    item,
                    status=ANALYSIS_SKIPPED,
                    error_class=ErrorClass.PERMANENT,
                    error_message="İlan bulunamadı.",
                )
                return OUTCOME_SKIPPED
            match = JobRepository(db).get_match_for_user(job.user_id, job.id)
            if match is None:
                ScoringItemRepository(db).mark_finished(
                    item,
                    status=ANALYSIS_SKIPPED,
                    error_class=ErrorClass.PERMANENT,
                    error_message="Eşleşme kaydı bulunamadı.",
                )
                return OUTCOME_SKIPPED
            match_id = match.id
            user_id = item.user_id
            if match.analysis_status != ANALYSIS_RUNNING:
                match.analysis_status = ANALYSIS_RUNNING
            snapshot = {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "work_mode": job.work_mode,
                "description": redact_job_text(job.description),
                "description_status": job.description_status,
            }
            db.flush()

        try:
            result, info = await client.score_job(  # type: ignore[attr-defined]
                candidate_profile=profile,
                cv_excerpt=excerpt,
                job_title=snapshot["title"],
                company=snapshot["company"],
                location=snapshot["location"],
                work_mode=snapshot["work_mode"],
                description=snapshot["description"],
                description_status=snapshot["description_status"],
                preferences=preferences,
            )
        except (ProviderError, LlmOutputError) as exc:
            error_class = (
                exc.error_class if isinstance(exc, ProviderError) else ErrorClass.PERMANENT
            )
            message = str(exc)[:500]
            self._record_failure(
                item_id=item_id, match_id=match_id, error_class=error_class, message=message
            )
            self.usage.record(
                user_id=user_id,
                purpose="scoring",
                status="failed",
                job_id=snapshot["id"],
                attempt=1,
                error_class=error_class,
                error_message=message,
            )
            logger.warning(
                "İlan analizi başarısız (user=%s, job=%s, class=%s)",
                user_id,
                snapshot["id"],
                error_class.value if isinstance(error_class, ErrorClass) else error_class,
            )
            return OUTCOME_FAILED

        with self._db() as db:
            match = db.get(JobMatch, match_id)
            if match is None:
                return self._finish(
                    item_id,
                    status=ANALYSIS_SKIPPED,
                    error_message="Eşleşme silinmiş.",
                )
            self._apply_result(
                match,
                result=result,
                model=info.model,
                cv_checksum=checksum,
                prompt_version=getattr(client, "prompt_version", PROMPT_VERSION),
            )
            ScoringItemRepository(db).mark_finished(
                _item_row(db, item_id), status="succeeded", match_id=match.id
            )
            resolved_match_id = match.id

        self.usage.record(
            user_id=user_id,
            purpose="scoring",
            status="success",
            job_id=snapshot["id"],
            info=info,
        )
        logger.info(
            "İlan analiz edildi (user=%s, job=%s, match=%s, score=%s, confidence=%s, latency=%sms)",
            user_id,
            snapshot["id"],
            resolved_match_id,
            result.match_score,
            result.confidence,
            info.latency_ms,
        )
        return OUTCOME_ANALYZED

    @staticmethod
    def _apply_result(
        match: JobMatch,
        *,
        result,
        model: str | None,
        cv_checksum: str | None,
        prompt_version: str,
    ) -> None:
        match.score = result.match_score
        match.confidence = result.confidence
        match.rationale = result.reasoning
        match.matched_skills = list(result.matched_skills)
        match.missing_skills = list(result.missing_skills)
        match.experience_match = result.experience_match.status
        match.location_match = result.location_match.status
        match.work_mode_match = result.work_mode_match.status
        match.title_match = result.title_match.status
        match.match_details = {
            "experience": result.experience_match.model_dump(),
            "location": result.location_match.model_dump(),
            "work_mode": result.work_mode_match.model_dump(),
            "title": result.title_match.model_dump(),
        }
        match.insufficient_information = bool(result.insufficient_information)
        match.model = model
        match.cv_checksum = cv_checksum
        match.prompt_version = prompt_version
        match.analysis_status = ANALYSIS_COMPLETED
        match.analysis_error = None
        match.analysis_attempts = (match.analysis_attempts or 0) + 1
        match.analyzed_at = datetime.now(timezone.utc)

    def _record_failure(
        self,
        *,
        item_id: uuid.UUID,
        match_id: uuid.UUID,
        error_class: ErrorClass,
        message: str,
    ) -> None:
        with self._db() as db:
            match = db.get(JobMatch, match_id)
            if match is not None:
                match.analysis_status = ANALYSIS_FAILED
                match.analysis_error = message
                match.analysis_attempts = (match.analysis_attempts or 0) + 1
            item = db.get(ScoringItem, item_id)
            if item is not None:
                ScoringItemRepository(db).mark_finished(
                    item,
                    status="failed",
                    error_class=error_class,
                    error_message=message,
                    match_id=match_id,
                )
            db.flush()


def _item_row(db: Session, item_id: uuid.UUID) -> ScoringItem:
    item = db.get(ScoringItem, item_id)
    if item is None:  # pragma: no cover - defensive
        raise LookupError(f"scoring item {item_id} kayboldu")
    return item


__all__ = ["ScoringOutcome", "ScoringRunner", "default_llm_factory"]
