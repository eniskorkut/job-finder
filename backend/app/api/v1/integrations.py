from __future__ import annotations

import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentSession, CurrentUser, DbSession
from app.core import errors
from app.core.config import settings
from app.models.enums import ConnectionStatus, Provider
from app.schemas.common import MessageResponse
from app.schemas.integration import (
    AccountTestResponse,
    ConnectResponse,
    IntegrationsResponse,
    MailAccountRead,
    MailAccountUpdateRequest,
    OAuthClientRead,
    OAuthClientSaveRequest,
    TelegramConfigRequest,
    TelegramDetectResponse,
    TelegramTestResponse,
)
from app.services.auth_service import AuthService
from app.services.integration_service import IntegrationService
from app.services.oauth_service import OAuthClientService, OAuthFlowService
from app.services.telegram_service import TelegramConfigService

logger = logging.getLogger("jobhunter.api.integrations")

router = APIRouter(prefix="/integrations", tags=["integrations"])


# --- overview -----------------------------------------------------------
@router.get("", response_model=IntegrationsResponse)
def list_integrations(user: CurrentUser, db: DbSession) -> IntegrationsResponse:
    service = IntegrationService(db)
    return IntegrationsResponse(
        integrations=service.list(user),
        deepseek=service.deepseek_summary(),
        web_search=service.web_search_summary(),
    )


# --- oauth client credentials ------------------------------------------
def _client_read(service: OAuthClientService, user, provider: str) -> OAuthClientRead:
    view = service.public_view(user, provider)
    return OAuthClientRead(
        provider=provider,
        configured=view["configured"],
        client_id=view["client_id"],
        client_secret_hint=view["client_secret_hint"],
        tenant=view["tenant"],
        redirect_uri=view["redirect_uri"],
        scopes=view["scopes"],
        title=view["title"],
        steps=view["steps"],
        notes=view["notes"],
        estimated_minutes=view.get("estimated_minutes", 5),
        prerequisites=view.get("prerequisites", []),
        structured_steps=view.get("structured_steps", []),
        faq=view.get("faq", []),
        troubleshooting=view.get("troubleshooting", []),
        official_links=view.get("official_links", []),
        updated_at=view["updated_at"],
    )


@router.put("/{provider}/client", response_model=OAuthClientRead)
def save_oauth_client(
    provider: Provider,
    payload: OAuthClientSaveRequest,
    user: CurrentUser,
    db: DbSession,
) -> OAuthClientRead:
    service = OAuthClientService(db)
    service.save(
        user,
        provider.value,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        tenant=payload.tenant,
    )
    db.commit()
    return _client_read(service, user, provider.value)


@router.delete("/{provider}/client", response_model=MessageResponse)
def delete_oauth_client(
    provider: Provider, user: CurrentUser, db: DbSession
) -> MessageResponse:
    OAuthClientService(db).delete(user, provider.value)
    db.commit()
    return MessageResponse(
        message="OAuth istemci bilgileri silindi. Bağlı hesaplar yeniden yetkilendirme bekliyor.",
        code="oauth_client_deleted",
    )


# --- connect / callback -------------------------------------------------
@router.post("/{provider}/connect", response_model=ConnectResponse)
def start_connect(
    provider: Provider,
    request: Request,
    session: CurrentSession,
    db: DbSession,
    account_id: uuid.UUID | None = Query(default=None),
) -> ConnectResponse:
    result = OAuthFlowService(db).start(
        session.user, session.session, provider.value, account_id=account_id
    )
    db.commit()
    return ConnectResponse(**result)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: Provider,
    request: Request,
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Provider redirect target. Always answers with a redirect so the browser
    lands back on the integrations screen with a readable message."""
    frontend = settings.frontend_url.rstrip("/")
    provider_value = provider.value

    cookie = request.cookies.get(settings.session_cookie_name)
    context = AuthService(db).resolve_session(cookie) if cookie else None

    def redirect(**params: str) -> RedirectResponse:
        query = urlencode({"provider": provider_value, **params})
        return RedirectResponse(url=f"{frontend}/integrations?{query}", status_code=303)

    if state is None:
        return redirect(oauth="error", reason="state_missing")
    if context is None:
        return redirect(oauth="error", reason="session_missing")

    try:
        result = await OAuthFlowService(db).complete(
            state_token=state,
            provider=provider_value,
            code=code,
            error=error or error_description,
            session=context.session,
        )
        db.commit()
    except errors.AppError as exc:
        db.rollback()
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.warning(
            "OAuth callback reddedildi (provider=%s, code=%s)",
            provider_value,
            detail.get("code"),
        )
        return redirect(
            oauth="error",
            reason=str(detail.get("code") or "rejected"),
            detail=str(detail.get("message") or "")[:200],
        )
    except Exception as exc:  # pragma: no cover - provider surprise
        db.rollback()
        logger.exception("OAuth callback hatası: %s", type(exc).__name__)
        return redirect(oauth="error", reason="provider_error")

    return redirect(
        oauth="success",
        account=result.account.email_address,
        created="1" if result.created else "0",
    )


# --- accounts -----------------------------------------------------------
@router.get("/accounts", response_model=list[MailAccountRead])
def list_accounts(user: CurrentUser, db: DbSession) -> list[MailAccountRead]:
    accounts = IntegrationService(db).accounts.list_for_user(user.id)
    return [MailAccountRead.model_validate(account) for account in accounts]


@router.patch("/accounts/{account_id}", response_model=MailAccountRead)
def update_account(
    account_id: uuid.UUID,
    payload: MailAccountUpdateRequest,
    user: CurrentUser,
    db: DbSession,
) -> MailAccountRead:
    account = IntegrationService(db).update_account(
        user,
        account_id,
        display_name=payload.display_name,
        senders=payload.senders,
        subjects=payload.subjects,
        reset_cursor=payload.reset_cursor,
    )
    db.commit()
    return MailAccountRead.model_validate(account)


@router.post("/accounts/{account_id}/test", response_model=AccountTestResponse)
async def test_account(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> AccountTestResponse:
    service = IntegrationService(db)
    account = service.require_account(user, account_id)
    outcome = await OAuthFlowService(db).test_connection(user, account)
    db.commit()
    return AccountTestResponse(**outcome)


@router.post("/accounts/{account_id}/reconnect", response_model=ConnectResponse)
def reconnect_account(
    account_id: uuid.UUID,
    session: CurrentSession,
    db: DbSession,
) -> ConnectResponse:
    service = IntegrationService(db)
    account = service.require_account(session.user, account_id)
    result = OAuthFlowService(db).start(
        session.user, session.session, account.provider, account_id=account.id
    )
    db.commit()
    return ConnectResponse(**result)


@router.delete("/accounts/{account_id}", response_model=MessageResponse)
def disconnect_account(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MessageResponse:
    service = IntegrationService(db)
    account = service.require_account(user, account_id)
    OAuthFlowService(db).disconnect(user, account)
    db.commit()
    return MessageResponse(
        message=(
            "Hesabın erişim anahtarları silindi. Daha önce bulunan ilanlar korunur, "
            "istenirse hesap yeniden bağlanabilir."
        ),
        code="account_disconnected",
    )


@router.delete("/accounts/{account_id}/purge", response_model=MessageResponse)
def purge_account(
    account_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MessageResponse:
    """Remove a disconnected mailbox record entirely (keeps its jobs)."""
    service = IntegrationService(db)
    account = service.require_account(user, account_id)
    if account.status != ConnectionStatus.DISCONNECTED.value:
        raise errors.conflict(
            "Önce hesabın bağlantısını kesin, ardından kaydı kaldırabilirsiniz."
        )
    service.accounts.delete(account)
    db.commit()
    return MessageResponse(message="Hesap kaydı kaldırıldı.", code="account_removed")


# --- telegram (per user, token encrypted) -------------------------------
@router.get("/telegram/status")
def telegram_status(user: CurrentUser, db: DbSession) -> dict:
    return IntegrationService(db).telegram_status(user)


@router.post("/telegram/config")
async def configure_telegram(
    payload: TelegramConfigRequest, user: CurrentUser, db: DbSession
) -> dict:
    """Validate (getMe/getChat) and store the bot token + chat id for this user."""
    service = TelegramConfigService(db)
    status = await service.save_config(
        user, bot_token=payload.bot_token, chat_id=payload.chat_id
    )
    db.commit()
    return status


@router.post("/telegram/link", include_in_schema=False)
async def link_telegram_compat(
    payload: TelegramConfigRequest, user: CurrentUser, db: DbSession
) -> dict:
    """Backwards compatible alias of /telegram/config."""
    return await configure_telegram(payload, user, db)


@router.post("/telegram/detect-chat", response_model=TelegramDetectResponse)
async def detect_telegram_chat(
    user: CurrentUser, db: DbSession, payload: TelegramConfigRequest | None = None
) -> TelegramDetectResponse:
    """Find the chat id from recent /start messages (getUpdates)."""
    service = TelegramConfigService(db)
    result = await service.detect_chat(
        user, bot_token=payload.bot_token if payload else None
    )
    db.commit()
    return TelegramDetectResponse.model_validate(result)


@router.post("/telegram/test", response_model=TelegramTestResponse)
async def test_telegram(user: CurrentUser, db: DbSession) -> TelegramTestResponse:
    service = TelegramConfigService(db)
    outcome = await service.send_test(user)
    db.commit()
    return TelegramTestResponse.model_validate(outcome)


@router.delete("/telegram")
def unlink_telegram(user: CurrentUser, db: DbSession) -> dict:
    service = TelegramConfigService(db)
    status = service.disconnect(user)
    db.commit()
    return {**status, "message": "Telegram bağlantısı kaldırıldı."}
