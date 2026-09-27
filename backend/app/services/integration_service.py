from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.models.enums import ConnectionStatus, Provider
from app.models.user import User
from app.repositories.integrations import TelegramRepository
from app.repositories.jobs import MailAccountRepository
from app.repositories.users import UserRepository
from app.schemas.integration import IntegrationRead, MailAccountRead

PROVIDER_LABELS = {
    Provider.GMAIL.value: ("Gmail", "Google OAuth ile iş ilanı e-postalarını okur.", "phase-2"),
    Provider.OUTLOOK.value: (
        "Hotmail / Outlook",
        "Microsoft Graph ile iş ilanı e-postalarını okur.",
        "phase-2",
    ),
    Provider.TELEGRAM.value: (
        "Telegram",
        "Yüksek puanlı eşleşmeleri Telegram üzerinden bildirir.",
        "phase-3",
    ),
}


class IntegrationService:
    """Phase 1 exposes integration state only - no provider calls are made."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.accounts = MailAccountRepository(db)
        self.telegram = TelegramRepository(db)
        self.users = UserRepository(db)

    def list(self, user: User) -> list[IntegrationRead]:
        accounts = self.accounts.list_for_user(user.id)
        telegram = self.telegram.get_for_user(user.id)

        items: list[IntegrationRead] = []
        for provider in (Provider.GMAIL.value, Provider.OUTLOOK.value):
            label, description, phase = PROVIDER_LABELS[provider]
            provider_accounts = [a for a in accounts if a.provider == provider]
            status = ConnectionStatus.DISCONNECTED.value
            if provider_accounts:
                status = provider_accounts[0].status
            items.append(
                IntegrationRead(
                    provider=provider,
                    label=label,
                    description=description,
                    category="mail",
                    status=status,
                    available=False,
                    unavailable_reason="Bu entegrasyon henüz geliştirilmedi (2. aşama).",
                    phase=phase,
                    accounts=[
                        MailAccountRead.model_validate(account)
                        for account in provider_accounts
                    ],
                    detail=description,
                    last_synced_at=_latest(provider_accounts),
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
            )
        )
        return items

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
                "DeepSeek skorlaması 3. aşamada açılacak. Anahtar tüm kullanıcılar için ortaktır."
            ),
        }

    def create_oauth_state(self, user: User, provider: str) -> None:
        raise errors.not_implemented(
            "phase-2",
            f"{PROVIDER_LABELS.get(provider, (provider,))[0]} bağlantısı 2. aşamada eklenecek.",
        )

    def disconnect_mail_account(self, user: User, provider: str, account_id: uuid.UUID) -> None:
        account = self.accounts.get_by_provider(user.id, provider, account_id)
        if account is None:
            raise errors.not_found("Bağlı e-posta hesabı bulunamadı.")
        if account.status == ConnectionStatus.CONNECTED.value:
            raise errors.not_implemented(
                "phase-2",
                "Bağlı hesapların kaldırılması OAuth altyapısı ile birlikte 2. aşamada gelecek.",
            )
        self.accounts.delete(account)

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
        raise errors.not_implemented(
            "phase-3", "Telegram bağlantısı 3. aşamada eklenecek."
        )

    def unlink_telegram(self, user: User) -> None:
        integration = self.telegram.get_for_user(user.id)
        if integration is None:
            raise errors.not_found("Telegram entegrasyonu bulunamadı.")
        integration.chat_id = None
        integration.bot_token_encrypted = None
        integration.status = ConnectionStatus.DISCONNECTED.value
        integration.linked_at = None
        self.db.flush()


def _latest(accounts: list) -> datetime | None:
    values = [a.last_synced_at for a in accounts if a.last_synced_at is not None]
    if not values:
        return None
    return max(
        values,
        key=lambda value: value
        if value.tzinfo is not None
        else value.replace(tzinfo=timezone.utc),
    )
