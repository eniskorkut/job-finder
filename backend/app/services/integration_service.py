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
        from app.services.telegram_service import TelegramConfigService

        self.db = db
        self.accounts = MailAccountRepository(db)
        self.telegram = TelegramRepository(db)
        self.clients = OAuthClientRepository(db)
        self.checkpoints = CheckpointRepository(db)
        self.client_service = OAuthClientService(db)
        self.telegram_service = TelegramConfigService(db)

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

            configured = (
                settings.google_oauth_configured
                if provider == Provider.GMAIL.value
                else settings.microsoft_oauth_configured
            )
            available = configured
            unavailable_reason = (
                None if configured else "Yönetici tarafından yapılandırılmamış."
            )

            status = ConnectionStatus.DISCONNECTED.value
            if provider_accounts:
                status = _aggregate_status(provider_accounts)

            items.append(
                IntegrationRead(
                    provider=provider,
                    label=label,
                    description=description,
                    category="mail",
                    status=status,
                    configured=configured,
                    available=available,
                    unavailable_reason=unavailable_reason,
                    phase=phase,
                    mode="personal_accounts",
                    scopes=list(capabilities.scopes),
                    accounts=[
                        MailAccountRead.model_validate(account)
                        for account in provider_accounts
                    ],
                    detail=description,
                    last_synced_at=_latest(provider_accounts),
                    oauth_client=None,
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
        telegram_status = self.telegram_service.status(user)
        items.append(
            IntegrationRead(
                provider=Provider.TELEGRAM.value,
                label=label,
                description=description,
                category="notification",
                status=telegram_status["status"],
                available=True,
                unavailable_reason=None,
                phase=phase,
                detail=(
                    f"@{telegram_status['bot_username']}"
                    if telegram_status.get("bot_username")
                    else description
                ),
                last_synced_at=telegram_status.get("last_notification_at")
                or telegram_status.get("linked_at"),
                capabilities={
                    "implemented": True,
                    "token_hint": telegram_status.get("token_hint"),
                    "chat_id": telegram_status.get("chat_id"),
                    "bot_username": telegram_status.get("bot_username"),
                    "last_error": telegram_status.get("last_error"),
                    "last_error_class": telegram_status.get("last_error_class"),
                    "hint": telegram_status.get("hint"),
                    "message": telegram_status.get("message"),
                },
            )
        )
        return items

    def _client_view(self, user: User, provider: str) -> OAuthClientRead | None:
        guide = self.client_service.public_view(user, provider)
        if self.clients.get_for_user_provider(user.id, provider) is None:
            return OAuthClientRead(
                provider=provider,
                configured=False,
                redirect_uri=guide["redirect_uri"],
                scopes=guide["scopes"],
                title=guide["title"],
                steps=guide["steps"],
                notes=guide["notes"],
                estimated_minutes=guide.get("estimated_minutes", 5),
                prerequisites=guide.get("prerequisites", []),
                structured_steps=guide.get("structured_steps", []),
                faq=guide.get("faq", []),
                troubleshooting=guide.get("troubleshooting", []),
                official_links=guide.get("official_links", []),
            )
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
            estimated_minutes=guide.get("estimated_minutes", 5),
            prerequisites=guide.get("prerequisites", []),
            structured_steps=guide.get("structured_steps", []),
            faq=guide.get("faq", []),
            troubleshooting=guide.get("troubleshooting", []),
            official_links=guide.get("official_links", []),
            updated_at=datetime.fromisoformat(updated_at) if updated_at else None,
        )

    def deepseek_summary(self) -> dict:
        """Shared LLM status: presence and model only, never the key value."""
        from app.integrations.deepseek import DeepSeekScoringClient

        summary = DeepSeekScoringClient().describe()
        summary.update(
            {
                "label": "DeepSeek / OpenAI-uyumlu LLM",
                "prompt_version": settings.llm_prompt_version,
                "note": (
                    "Skorlama ve CV profili için ortak LLM kullanılır. Anahtar "
                    "backend/.env.local içinde tutulur; panelden girilmez ve "
                    "hiçbir zaman tarayıcıya gönderilmez."
                ),
            }
        )
        return summary

    def web_search_summary(self) -> dict:
        """Shared web discovery / SearXNG search status."""
        is_configured = settings.web_search_provider in {"searxng", "mock"}
        return {
            "provider": settings.web_search_provider,
            "label": "SearXNG Web Araması (İş Keşfi & Zenginleştirme)",
            "configured": is_configured,
            "status": "running" if is_configured else "disabled",
            "url": settings.web_search_searxng_url if settings.web_search_provider == "searxng" else None,
            "mode": "server_managed",
            "description": (
                "Kısa iş ilanlarının resmi şirket / ATS sayfalarından tam metnini ve tazelik "
                "bilgisini bulmak için kullanılır. Yerel SearXNG Docker servisi üzerinden "
                "sunucu tarafından yönetilir; kullanıcı API anahtarı gerekmez."
            ),
            "max_concurrency": settings.web_search_max_concurrency,
            "note": "SearXNG yerel konteyner olarak sunucu tarafından yönetilir. Harici API anahtarı gerekmez.",
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

    # --- telegram ------------------------------------------------------
    def telegram_status(self, user: User) -> dict:
        return self.telegram_service.status(user)

    def unlink_telegram(self, user: User) -> dict:
        return self.telegram_service.disconnect(user)


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
