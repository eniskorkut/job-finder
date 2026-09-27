from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, instance: ModelT) -> ModelT:
        self.db.add(instance)
        self.db.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        self.db.delete(instance)
        self.db.flush()

    def get(self, pk: object) -> ModelT | None:
        return self.db.get(self.model, pk)

    def count(self, *criteria) -> int:
        stmt = select(func.count()).select_from(self.model)
        if criteria:
            stmt = stmt.where(*criteria)
        return int(self.db.execute(stmt).scalar_one())

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, instance: ModelT) -> ModelT:
        self.db.refresh(instance)
        return instance
