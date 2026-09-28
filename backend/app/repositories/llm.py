from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.llm import CVProfile, LlmUsage
from app.repositories.base import Repository


class CVProfileRepository(Repository[CVProfile]):
    model = CVProfile

    def get_for_user(self, user_id: uuid.UUID) -> CVProfile | None:
        stmt = select(CVProfile).where(CVProfile.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()


class LlmUsageRepository(Repository[LlmUsage]):
    model = LlmUsage

    def list_for_user(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> list[LlmUsage]:
        stmt = (
            select(LlmUsage)
            .where(LlmUsage.user_id == user_id)
            .order_by(LlmUsage.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())
