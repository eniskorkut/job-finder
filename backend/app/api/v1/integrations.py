from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models.enums import Provider
from app.schemas.common import MessageResponse
from app.schemas.integration import IntegrationsResponse
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=IntegrationsResponse)
def list_integrations(user: CurrentUser, db: DbSession) -> IntegrationsResponse:
    service = IntegrationService(db)
    return IntegrationsResponse(
        integrations=service.list(user), deepseek=service.deepseek_summary()
    )


@router.post("/{provider}/connect", response_model=MessageResponse)
def connect_provider(
    provider: Provider, user: CurrentUser, db: DbSession
) -> MessageResponse:
    """Phase 2/3 stub: answers 501 instead of faking a successful connect."""
    IntegrationService(db).create_oauth_state(user, provider.value)


@router.delete("/{provider}/accounts/{account_id}", response_model=MessageResponse)
def disconnect_mail_account(
    provider: str, account_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MessageResponse:
    IntegrationService(db).disconnect_mail_account(user, provider, account_id)
    db.commit()
    return MessageResponse(message="E-posta hesabı kaydı kaldırıldı.", code="account_removed")


@router.get("/telegram/status")
def telegram_status(user: CurrentUser, db: DbSession) -> dict:
    return IntegrationService(db).telegram_status(user)


@router.post("/telegram/link", response_model=MessageResponse)
def link_telegram(user: CurrentUser, db: DbSession) -> MessageResponse:
    IntegrationService(db).link_telegram(user)


@router.delete("/telegram", response_model=MessageResponse)
def unlink_telegram(user: CurrentUser, db: DbSession) -> MessageResponse:
    IntegrationService(db).unlink_telegram(user)
    db.commit()
    return MessageResponse(message="Telegram bağlantısı kaldırıldı.", code="telegram_unlinked")
