from __future__ import annotations

import uuid

from sqlalchemy import select, update

from app.models.cv import CV
from app.repositories.base import Repository


class CVRepository(Repository[CV]):
    model = CV

    def list_for_user(self, user_id: uuid.UUID) -> list[CV]:
        stmt = (
            select(CV)
            .where(CV.user_id == user_id)
            .order_by(CV.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_for_user(self, user_id: uuid.UUID, cv_id: uuid.UUID) -> CV | None:
        stmt = select(CV).where(CV.id == cv_id, CV.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_active_for_user(self, user_id: uuid.UUID) -> CV | None:
        stmt = (
            select(CV)
            .where(CV.user_id == user_id, CV.is_active.is_(True))
            .order_by(CV.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def deactivate_all(self, user_id: uuid.UUID, *, keep: uuid.UUID | None = None) -> None:
        stmt = update(CV).where(CV.user_id == user_id)
        if keep is not None:
            stmt = stmt.where(CV.id != keep)
        self.db.execute(stmt.values(is_active=False))
        self.db.flush()
