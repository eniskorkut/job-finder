"""Structured CV profile cache.

The profile is derived from the active CV's checksum: as long as the CV does
not change, scoring reuses it instead of sending the whole document to the LLM
again. Personal contact data is stripped before the text leaves the server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cv import CV
from app.models.llm import CVProfile
from app.models.user import User
from app.repositories.cvs import CVRepository
from app.repositories.llm import CVProfileRepository
from app.schemas.llm import LlmCVProfile
from app.services.cv_privacy import redact_job_text, redact_pii

MAX_PROFILE_TEXT_CHARS = 20000


class CVProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.cvs = CVRepository(db)
        self.profiles = CVProfileRepository(db)

    # --- reads ----------------------------------------------------------
    def active_cv(self, user: User) -> CV | None:
        return self.cvs.get_active_for_user(user.id)

    def cached_profile(self, user: User) -> CVProfile | None:
        """Return the cached profile only when it matches the active CV."""
        profile = self.profiles.get_for_user(user.id)
        if profile is None:
            return None
        cv = self.active_cv(user)
        if cv is None or not cv.checksum or profile.cv_checksum != cv.checksum:
            return None
        return profile

    def needs_refresh(self, user: User) -> bool:
        cv = self.active_cv(user)
        if cv is None or not cv.checksum:
            return False
        return self.cached_profile(user) is None

    def status(self, user: User) -> dict:
        cv = self.active_cv(user)
        profile = self.profiles.get_for_user(user.id)
        return {
            "cv_id": cv.id if cv else None,
            "cv_checksum": cv.checksum if cv else None,
            "has_profile": bool(profile and cv and profile.cv_checksum == cv.checksum),
            "status": profile.status if profile else "missing",
            "generated_at": profile.generated_at if profile else None,
            "model": profile.model if profile else None,
            "prompt_version": profile.prompt_version if profile else None,
            "error": profile.error_message if profile else None,
        }

    # --- prompt inputs --------------------------------------------------
    @staticmethod
    def scoring_context(cv: CV) -> str:
        """Bounded, redacted CV excerpt used alongside the structured profile."""
        text = redact_pii(cv.extracted_text or "")[:MAX_PROFILE_TEXT_CHARS]
        return text

    @staticmethod
    def profile_text(cv: CV) -> str:
        return redact_pii(cv.extracted_text or "")[:MAX_PROFILE_TEXT_CHARS]

    # --- writes ---------------------------------------------------------
    def store(
        self,
        user: User,
        cv: CV,
        profile: LlmCVProfile | dict,
        *,
        model: str,
        prompt_version: str,
    ) -> CVProfile:
        payload = profile.model_dump() if isinstance(profile, LlmCVProfile) else dict(profile)
        record = self.profiles.get_for_user(user.id)
        if record is None:
            record = CVProfile(user_id=user.id, cv_checksum=cv.checksum or "")
            self.db.add(record)
        record.cv_id = cv.id
        record.cv_checksum = cv.checksum or ""
        record.profile = payload
        record.status = "ready"
        record.error_message = None
        record.model = model
        record.prompt_version = prompt_version
        record.generated_at = datetime.now(timezone.utc)
        self.db.flush()
        return record

    def mark_failed(self, user: User, cv: CV, *, message: str, model: str | None) -> CVProfile:
        record = self.profiles.get_for_user(user.id)
        if record is None:
            record = CVProfile(user_id=user.id, cv_checksum=cv.checksum or "")
            self.db.add(record)
        record.cv_id = cv.id
        record.cv_checksum = cv.checksum or ""
        record.status = "failed"
        record.error_message = message[:500]
        record.model = model
        self.db.flush()
        return record

    def invalidate(self, user_id: uuid.UUID, *, reason: str = "cv_changed") -> None:
        record = self.profiles.get_for_user(user_id)
        if record is None:
            return
        record.status = "stale"
        record.error_message = reason[:500]
        self.db.flush()

    def profile_dict(self, user: User) -> dict:
        cached = self.cached_profile(user)
        return dict(cached.profile or {}) if cached else {}


def redact_for_prompt(text: str | None) -> str:
    """Job text keeps its meaning but loses tracking URLs."""
    return redact_job_text(text)


__all__ = ["CVProfileService", "redact_for_prompt", "settings"]
