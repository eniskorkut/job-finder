from __future__ import annotations

import uuid

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.core import errors
from app.schemas.common import MessageResponse
from app.schemas.cv import CVRead, CVUpdate
from app.services.cv_service import CVService


def _to_read(cv) -> CVRead:  # type: ignore[no-untyped-def]
    data = CVRead.model_validate(cv)
    data.has_extracted_text = bool(cv.extracted_text)
    return data


router = APIRouter(prefix="/cvs", tags=["cvs"])


@router.get("", response_model=list[CVRead])
def list_cvs(user: CurrentUser, db: DbSession) -> list[CVRead]:
    return [_to_read(cv) for cv in CVService(db).list(user)]


@router.post("", response_model=CVRead, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> CVRead:
    content = await file.read()
    cv = CVService(db).upload(
        user,
        filename=file.filename or "cv",
        content=content,
        content_type=file.content_type,
    )
    db.commit()
    return _to_read(cv)


@router.get("/{cv_id}", response_model=CVRead)
def read_cv(cv_id: uuid.UUID, user: CurrentUser, db: DbSession) -> CVRead:
    return _to_read(CVService(db).get(user, cv_id))


@router.patch("/{cv_id}", response_model=CVRead)
def update_cv(
    cv_id: uuid.UUID, payload: CVUpdate, user: CurrentUser, db: DbSession
) -> CVRead:
    cv = CVService(db).update(
        user, cv_id, is_active=payload.is_active, summary=payload.summary
    )
    db.commit()
    return _to_read(cv)


@router.delete("/{cv_id}", response_model=MessageResponse)
def delete_cv(cv_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MessageResponse:
    CVService(db).delete(user, cv_id)
    db.commit()
    return MessageResponse(message="CV silindi.", code="cv_deleted")


@router.get("/{cv_id}/download")
def download_cv(cv_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FileResponse:
    service = CVService(db)
    cv = service.get(user, cv_id)
    path = service.path_for(cv)
    if not path.is_file():
        raise errors.not_found("CV dosyası diskte bulunamadı.")
    return FileResponse(
        path,
        filename=cv.filename,
        media_type=cv.content_type or "application/octet-stream",
    )
