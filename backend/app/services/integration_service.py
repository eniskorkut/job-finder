from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.integrations.gmail import GmailClient
from app.integrations.outlook import OutlookClient
from app.models.enums import ConnectionStatus, Provider
from app.models.mail_account import MailAccount
from app.models.user import User
from app.repositories.integrations import TelegramRepository
from app.repositories.jobs import MailAccountRepository
from app.repositories.oauth_clients import OAuthClientRepository
from app.repositories.sync_jobs import CheckpointRepository
from app.schemas.integration import (
    IntegrationRead,
    MailAccountRead,
    OAuthClientRead,
)
from app.services.oauth_service import OAuthClientService

PROVIDER_LABELS = {
    Provider.GMAIL.value: (
        "Gmail",
        "Kendi Google OAuth uygulamanızla Gmail iş ilanı e-postalarını okur.",
        "phase-2",
    ),
    Provider.OUTLOOK.value: (
        "Hotmail / Outlook",
        "Kendi Microsoft Entra uygulamanızla Microsoft Graph üzerinden okur.",
        "phase-2",
    ),
    Provider.TELEGRAM.value: (
        "Telegram",
        "Yüksek puanlı eşleşmeleri Telegram üzerinden bildirir.",
        "phase-3",
    ),
}

PROVIDER_CLIENTS = {
    Provider.GMAIL.value: GmailClient,
    Provider.OUTLOOK.value: OutlookClient,
}


class IntegrationService:
    """Read model for the integrations screen; OAuth actions live in
    :class:`~app.services.oauth_service.OAuthFlowService`."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.accounts = MailAccountRepository(db)
        self.telegram = TelegramRepository(db)
        self.clients = OAuthClientRepository(db)
        self.checkpoints = CheckpointRepository(db)
        self.client_service = OAuthClientService(db)

    # --- listing --------------------------------------------------------
    def list(self, user: User) -> list[IntegrationRead]:
        accounts = self.accounts.list_for_user(user.id)
        telegram = self.telegram.get_for_user(user.id)

        items: list[IntegrationRead] = []
        for provider in (Provider.GMAIL.value, Provider.OUTLOOK.value):
            label, description, phase = PROVIDER_LABELS[provider]
            provider_accounts = [a for a in accounts if a.provider == provider]
            client_cls = PROVIDER_CLIENTS[provider]
            capabilities = client_cls.capabilities
            client_view = self._client_view(user, provider)

            status = ConnectionStatus.DISCONNECTED.value
            if provider_accounts:
                status = _aggregate_status(provider_accounts)
            elif client_view is None or not client_view.configured:
                status = ConnectionStatus.DISCONNECTED.value

            items.append(
                IntegrationRead(
                    provider=provider,
                    label=label,
                    description=description,
                    category="mail",
                    status=status,
                    available=True,
                    unavailable_reason=None,
                    phase=phase,
                    accounts=[
                        MailAccountRead.model_validate(account)
                        for account in provider_accounts
                    ],
                    detail=description,
                    last_synced_at=_latest(provider_accounts),
                    oauth_client=client_view,
                    capabilities={
                        "implemented": capabilities.implemented,
                        "supports_multiple_accounts": capabilities.supports_multiple_accounts,
                        "scopes": list(capabilities.scopes),
                        "first_scan_window_days": settings.sync_initial_window_days,
                        "first_scan_max_messages": settings.sync_initial_max_messages,
                    },
                )
            )

        label, description, phase = PROVIDER_LABELS[Provider.TELEGRAM.value]
        items.append(
            IntegrationRead(
                provider=Provider.TELEGRAM.value,
                label=label,
                description=description,
                category="notification",
                status=telegram.status if telegram else ConnectionStatus.DISCONNECTED.value,
                available=False,
                unavailable_reason="Telegram bağlantısı henüz geliştirilmedi (3. aşama).",
                phase=phase,
                detail=telegram.username if telegram else description,
                last_synced_at=telegram.linked_at if telegram else None,
                capabilities={
                    "implemented": False,
                    "planned": "Kullanıcı bazlı bot token ve Chat ID 3. aşamada girilecek.",
                },
            )
        )
        return items

    def _client_view(self, user: User, provider: str) -> OAuthClientRead | None:
        if self.clients.get_for_user_provider(user.id, provider) is None:
            guide = self.client_service.public_view(user, provider)
            return OAuthClientRead(
                provider=provider,
                configured=False,
                redirect_uri=guide["redirect_uri"],
                scopes=guide["scopes"],
                title=guide["title"],
                steps=guide["steps"],
                notes=guide["notes"],
            )
        guide = self.client_service.public_view(user, provider)
        updated_at = guide["updated_at"]
        return OAuthClientRead(
            provider=provider,
            configured=bool(guide["configured"]),
            client_id=guide["client_id"],
            client_secret_hint=guide["client_secret_hint"],
            tenant=guide["tenant"],
            redirect_uri=guide["redirect_uri"],
            scopes=guide["scopes"],
            title=guide["title"],
            steps=guide["steps"],
            notes=guide["notes"],
            updated_at=datetime.fromisoformat(updated_at) if updated_at else None,
        )

    def deepseek_summary(self) -> dict:
        configured = bool(settings.deepseek_api_key)
        return {
            "provider": "deepseek",
            "label": "DeepSeek",
            "model": settings.deepseek_model,
            "base_url": settings.deepseek_base_url,
            "shared": True,
            "enabled": False,
            "configured": configured,
            "phase": "phase-3",
            "note": (
                "DeepSeek skorlaması 3. aşamada açılacak. Anahtar backend/.env.local "
                "içinde tutulur ve tüm kullanıcılar için ortaktır; panelden girilmez."
            ),
        }

    # --- account maintenance -------------------------------------------
    def require_account(self, user: User, account_id: uuid.UUID) -> MailAccount:
        account = self.accounts.get_for_user(user.id, account_id)
        if account is None:
            raise errors.not_found("Bağlı e-posta hesabı bulunamadı.")
        return account

    def update_account(
        self,
        user: User,
        account_id: uuid.UUID,
        *,
        display_name: str | None,
        senders: list[str] | None,
        subjects: list[str] | None,
        reset_cursor: bool = False,
    ) -> MailAccount:
        account = self.require_account(user, account_id)
        from app.integrations.parsing.filters import sanitize_filters

        if display_name is not None:
            account.display_name = display_name.strip() or None

        filters = dict(account.filters or {})
        if senders is not None or subjects is not None:
            if senders is not None:
                filters["senders"] = senders
            if subjects is not None:
                filters["subjects"] = subjects
        account.filters = sanitize_filters(filters)

        if reset_cursor:
            checkpoint = self.checkpoints.get_or_create(user.id, account.id)
            self.checkpoints.reset_cursor(
                checkpoint, reason="Kullanıcı tarama geçmişini sıfırladı."
            )
            account.initial_sync_completed = False
        self.db.flush()
        return account

    # --- telegram (phase 3 contract kept) -------------------------------
    def telegram_status(self, user: User) -> dict:
        integration = self.telegram.get_for_user(user.id)
        return {
            "provider": "telegram",
            "status": integration.status if integration else ConnectionStatus.DISCONNECTED.value,
            "chat_id": integration.chat_id if integration else None,
            "username": integration.username if integration else None,
            "available": False,
            "phase": "phase-3",
            "message": "Telegram bağlantısı 3. aşamada eklenecek.",
        }

    def link_telegram(self, user: User) -> None:
        raise errors.not_implemented("phase-3", "Telegram bağlantısı 3. aşamada eklenecek.")

    def unlink_telegram(self, user: User) -> None:
        integration = self.telegram.get_for_user(user.id)
        if integration is None:
            raise errors.not_found("Telegram entegrasyonu bulunamadı.")
        integration.chat_id = None
        integration.bot_token_encrypted = None
        integration.status = ConnectionStatus.DISCONNECTED.value
        integration.linked_at = None
        self.db.flush()


def _aggregate_status(accounts: list[MailAccount]) -> str:
    statuses = {account.status for account in accounts}
    for candidate in (
        ConnectionStatus.ERROR.value,
        ConnectionStatus.NEEDS_REAUTH.value,
        ConnectionStatus.CONNECTED.value,
        ConnectionStatus.PENDING.value,
    ):
        if candidate in statuses:
            return candidate
    return ConnectionStatus.DISCONNECTED.value


def _latest(accounts: list[MailAccount]) -> datetime | None:
    values = [a.last_synced_at for a in accounts if a.last_synced_at is not None]
    if not values:
        return None
    return max(
        values,
        key=lambda value: value
        if value.tzinfo is not None
        else value.replace(tzinfo=timezone.utc),
    )
