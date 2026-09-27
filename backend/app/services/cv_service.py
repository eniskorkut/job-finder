from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.integrations.cv_extraction import ExtractionResult, ExtractionStatus, extract, sniff_kind
from app.models.cv import CV
from app.models.user import User
from app.repositories.cvs import CVRepository

# Declared types are a hint only: the real format is verified from magic bytes.
DECLARED_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_CV_SIZE_BYTES = 10 * 1024 * 1024
LEGACY_EXTENSIONS = {".doc", ".rtf", ".odt"}


class CVService:
    """CV storage and text extraction, always scoped to one owner."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cvs = CVRepository(db)

    # --- reads ----------------------------------------------------------
    def list(self, user: User) -> list[CV]:
        return self.cvs.list_for_user(user.id)

    def get(self, user: User, cv_id: uuid.UUID) -> CV:
        cv = self.cvs.get_for_user(user.id, cv_id)
        if cv is None:
            # Another user's CV id is indistinguishable from a missing one.
            raise errors.not_found("CV bulunamadı.")
        return cv

    def preview(self, user: User, cv_id: uuid.UUID) -> dict:
        """Extracted text, visible to the owner only. Never sent to a provider."""
        cv = self.get(user, cv_id)
        text = cv.extracted_text or ""
        return {
            "id": cv.id,
            "filename": cv.filename,
            "content_type": cv.content_type,
            "size_bytes": cv.size_bytes,
            "is_active": cv.is_active,
            "extraction_status": cv.extraction_status,
            "extraction_warning": cv.extraction_warning,
            "has_extracted_text": bool(cv.extracted_text),
            "character_count": len(text),
            "line_count": len(text.splitlines()),
            "text": text,
            "truncated": False,
        }

    # --- writes ---------------------------------------------------------
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

        safe_name = Path(filename).name or "cv"
        suffix = Path(safe_name).suffix.lower()
        if suffix in LEGACY_EXTENSIONS:
            raise errors.validation_error(
                "Legacy .doc/.rtf biçimi desteklenmiyor. Lütfen PDF, DOCX, TXT veya MD yükleyin."
            )
        if content_type in DECLARED_EXTENSIONS:
            suffix = DECLARED_EXTENSIONS[content_type]
        if suffix not in ALLOWED_EXTENSIONS and suffix != "":
            raise errors.validation_error(
                "Desteklenmeyen dosya türü. PDF, DOCX, TXT veya MD yükleyin."
            )

        kind = sniff_kind(content)
        expected_kind = {".pdf": "pdf", ".docx": "docx", ".txt": "text", ".md": "text"}.get(
            suffix, "text"
        )
        if kind != expected_kind:
            raise errors.validation_error(
                "Dosya içeriği uzantısıyla eşleşmiyor "
                f"(uzantı: {suffix or 'yok'}, algılanan biçim: {kind})."
            )

        extraction = extract(filename=safe_name, content=content, content_type=content_type)

        checksum = hashlib.sha256(content).hexdigest()
        user_dir = settings.cv_storage_path / str(user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        target = user_dir / f"{uuid.uuid4().hex}{suffix or '.txt'}"
        target.write_bytes(content)

        cv = CV(
            user_id=user.id,
            filename=safe_name,
            content_type=content_type,
            size_bytes=len(content),
            storage_path=str(target.relative_to(settings.data_path)),
            checksum=checksum,
            extracted_text=extraction.text,
            extraction_status=extraction.status.value,
            extraction_warning=extraction.warning,
            is_active=True,
        )
        self.db.add(cv)
        self.db.flush()
        self.cvs.deactivate_all(user.id, keep=cv.id)
        return cv

    def update(
        self, user: User, cv_id: uuid.UUID, *, is_active: bool | None, summary: str | None
    ) -> CV:
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

    def reextract(self, user: User, cv_id: uuid.UUID) -> CV:
        cv = self.get(user, cv_id)
        path = self.path_for(cv)
        if not path.is_file():
            raise errors.not_found("CV dosyası diskte bulunamadı.")
        content = path.read_bytes()
        result: ExtractionResult = extract(
            filename=cv.filename, content=content, content_type=cv.content_type
        )
        cv.extracted_text = result.text
        cv.extraction_status = result.status.value
        cv.extraction_warning = result.warning
        self.db.flush()
        return cv

    @staticmethod
    def is_supported_status(status: str) -> bool:
        return status in {item.value for item in ExtractionStatus}
