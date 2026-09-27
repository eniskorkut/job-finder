from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.models.cv import CV
from app.models.user import User
from app.repositories.cvs import CVRepository

ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
MAX_CV_SIZE_BYTES = 10 * 1024 * 1024


class CVService:
    """CV storage scoped to a single owner.

    Text extraction and parsing arrive in phase 2; phase 1 stores the file with
    a checksum and keeps the metadata needed later.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cvs = CVRepository(db)

    def list(self, user: User) -> list[CV]:
        return self.cvs.list_for_user(user.id)

    def get(self, user: User, cv_id: uuid.UUID) -> CV:
        cv = self.cvs.get_for_user(user.id, cv_id)
        if cv is None:
            raise errors.not_found("CV bulunamadı.")
        return cv

    def upload(
        self,
        user: User,
        *,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> CV:
        if not content:
            raise errors.validation_error("Boş dosya yüklenemez.")
        if len(content) > MAX_CV_SIZE_BYTES:
            raise errors.validation_error("CV dosyası en fazla 10 MB olabilir.")

        suffix = Path(filename).suffix.lower()
        if content_type in ALLOWED_CONTENT_TYPES:
            suffix = ALLOWED_CONTENT_TYPES[content_type]
        if suffix not in {".pdf", ".doc", ".docx", ".txt", ".md"}:
            raise errors.validation_error(
                "Desteklenmeyen dosya türü. PDF, DOC, DOCX, TXT veya MD yükleyin."
            )

        checksum = hashlib.sha256(content).hexdigest()
        user_dir = settings.cv_storage_path / str(user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        target = user_dir / f"{uuid.uuid4().hex}{suffix}"
        target.write_bytes(content)

        cv = CV(
            user_id=user.id,
            filename=Path(filename).name,
            content_type=content_type,
            size_bytes=len(content),
            storage_path=str(target.relative_to(settings.data_path)),
            checksum=checksum,
            is_active=True,
        )
        self.db.add(cv)
        self.db.flush()
        self.cvs.deactivate_all(user.id, keep=cv.id)
        return cv

    def update(self, user: User, cv_id: uuid.UUID, *, is_active: bool | None, summary: str | None) -> CV:
        cv = self.get(user, cv_id)
        if is_active is not None:
            cv.is_active = is_active
            if is_active:
                self.cvs.deactivate_all(user.id, keep=cv.id)
        if summary is not None:
            cv.summary = summary
        self.db.flush()
        return cv

    def delete(self, user: User, cv_id: uuid.UUID) -> None:
        cv = self.get(user, cv_id)
        path = settings.data_path / cv.storage_path
        self.db.delete(cv)
        self.db.flush()
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    def path_for(self, cv: CV) -> Path:
        return settings.data_path / cv.storage_path
