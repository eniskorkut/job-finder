"""Per-user Telegram configuration.

The bot token is encrypted with ``APP_ENCRYPTION_KEY`` and only ever leaves the
server masked. Validation always goes through the Bot API (getMe / getChat) so
a saved configuration is a verified one.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core import errors
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.config import settings
from app.integrations.telegram import TelegramClient, TelegramError
from app.models.enums import ConnectionStatus
from app.models.user import User
from app.repositories.integrations import TelegramRepository
from app.services.telegram_message import build_detect_hint

MAX_CHAT_ID_LENGTH = 64
MAX_TOKEN_LENGTH = 200


def default_telegram_factory(bot_token: str) -> TelegramClient:
    return TelegramClient(bot_token=bot_token)


class TelegramConfigService:
    def __init__(
        self,
        db: Session,
        *,
        client_factory: Callable[[str], object] | None = None,
    ) -> None:
        self.db = db
        self.telegram = TelegramRepository(db)
        self.client_factory = client_factory or default_telegram_factory

    # --- reads ----------------------------------------------------------
    def integration(self, user: User):
        return self.telegram.get_or_create(user.id)

    def status(self, user: User) -> dict:
        integration = self.integration(user)
        token_hint = None
        if integration.bot_token_encrypted:
            token_hint = mask_secret(decrypt_secret(integration.bot_token_encrypted), 4)
        return {
            "provider": "telegram",
            "status": integration.status,
            "connected": integration.status == ConnectionStatus.CONNECTED.value,
            "bot_username": integration.username,
            "chat_id": integration.chat_id,
            "token_hint": token_hint,
            "has_token": bool(integration.bot_token_encrypted),
            "last_error": integration.last_error,
            "last_error_class": integration.last_error_class,
            "last_checked_at": integration.last_checked_at,
            "last_notification_at": integration.last_notification_at,
            "linked_at": integration.linked_at,
            "available": True,
            "phase": "phase-3",
            "message": self._status_message(integration),
            "hint": build_detect_hint(bot_username=integration.username),
        }

    @staticmethod
    def _status_message(integration) -> str:
        if integration.status == ConnectionStatus.CONNECTED.value:
            return "Telegram bağlı; eşik üstü eşleşmeler bu sohbete gönderilecek."
        if integration.status == ConnectionStatus.NEEDS_REAUTH.value:
            return "Bot token geçersiz; yeni token girip yeniden doğrulayın."
        if integration.chat_id and not integration.username:
            return "Chat ID kayıtlı ama bot doğrulanmadı."
        return "Bot token ve Chat ID girip doğrulayın."

    def client_for_token(self, bot_token: str) -> object:
        """Build a client; an unusable token becomes a validation error."""
        try:
            return self.client_factory(bot_token)
        except TelegramError as exc:
            raise errors.validation_error(str(exc)) from exc

    def saved_token(self, user: User) -> str | None:
        integration = self.integration(user)
        if not integration.bot_token_encrypted:
            return None
        return decrypt_secret(integration.bot_token_encrypted)

    # --- writes ---------------------------------------------------------
    async def save_config(
        self,
        user: User,
        *,
        bot_token: str | None,
        chat_id: str | None,
        verify: bool = True,
    ) -> dict:
        integration = self.integration(user)

        if bot_token is not None:
            token = bot_token.strip()
            if token and len(token) > MAX_TOKEN_LENGTH:
                raise errors.validation_error("Bot token çok uzun görünüyor.")
            if token:
                info = await self._verify_token(token)
                integration.bot_token_encrypted = encrypt_secret(token)
                integration.username = info.get("username")
                integration.last_error = None
                integration.last_error_class = None
            else:
                # Explicit clear: drop the token and any verified state.
                integration.bot_token_encrypted = None
                integration.username = None

        if chat_id is not None:
            chat = chat_id.strip()
            if chat and len(chat) > MAX_CHAT_ID_LENGTH:
                raise errors.validation_error("Chat ID çok uzun görünüyor.")
            if chat:
                if verify:
                    token = self.saved_token(user)
                    if not token:
                        raise errors.validation_error(
                            "Chat ID doğrulamak için önce bot token kaydedin."
                        )
                    await self._verify_chat(token, chat)
                integration.chat_id = chat
            else:
                integration.chat_id = None

        integration.last_checked_at = datetime.now(timezone.utc)
        self._refresh_status(integration)
        self.db.flush()
        return self.status(user)

    async def detect_chat(self, user: User, *, bot_token: str | None = None) -> dict:
        token = (bot_token or "").strip() or self.saved_token(user)
        if not token:
            raise errors.validation_error(
                "Önce bot token girin (veya kaydedin), sonra Chat ID algılamayı deneyin."
            )

        client = self.client_for_token(token)
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            me = await client.verify()  # type: ignore[attr-defined]
            updates = await client.get_updates(limit=50)  # type: ignore[attr-defined]
        except TelegramError as exc:
            await self._record_error(user, exc)
            raise errors.validation_error(str(exc)) from exc
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

        candidates: list[dict] = []
        seen: set[str] = set()
        for update in updates:
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            key = str(chat_id)
            if key in seen:
                continue
            seen.add(key)
            sender = message.get("from") or {}
            candidates.append(
                {
                    "chat_id": key,
                    "type": chat.get("type"),
                    "title": chat.get("title")
                    or " ".join(
                        filter(None, [chat.get("first_name"), chat.get("last_name")])
                    )
                    or chat.get("username"),
                    "username": chat.get("username") or sender.get("username"),
                    "last_message_at": message.get("date"),
                }
            )

        return {
            "bot_username": me.get("username"),
            "candidates": candidates,
            "suggested_chat_id": candidates[0]["chat_id"] if len(candidates) == 1 else None,
            "requires_manual_choice": len(candidates) > 1,
            "message": (
                "Uygun sohbet bulundu."
                if len(candidates) == 1
                else (
                    "Birden fazla sohbet bulundu; doğru olanı seçin."
                    if len(candidates) > 1
                    else "Hiç mesaj bulunamadı. Botunuza /start yazdıktan sonra tekrar deneyin."
                )
            ),
        }

    async def send_test(self, user: User) -> dict:
        integration = self.integration(user)
        if integration.status != ConnectionStatus.CONNECTED.value:
            raise errors.validation_error(
                "Telegram bağlı değil. Token ve Chat ID doğrulamasını tamamlayın."
            )
        token = self.saved_token(user)
        if not token or not integration.chat_id:
            raise errors.validation_error("Telegram yapılandırması eksik.")

        from app.services.telegram_message import build_test_message

        client = self.client_for_token(token)
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            result = await client.send_message(  # type: ignore[attr-defined]
                chat_id=integration.chat_id,
                text=build_test_message(username=integration.username),
            )
        except TelegramError as exc:
            await self._record_error(user, exc)
            return {"ok": False, "message": str(exc), "status": integration.status}
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

        integration.last_checked_at = datetime.now(timezone.utc)
        integration.last_notification_at = datetime.now(timezone.utc)
        integration.last_error = None
        integration.last_error_class = None
        self.db.flush()
        return {
            "ok": True,
            "message": "Test mesajı gönderildi.",
            "status": integration.status,
            "message_id": (result or {}).get("message_id"),
        }

    def disconnect(self, user: User) -> dict:
        integration = self.integration(user)
        integration.bot_token_encrypted = None
        integration.chat_id = None
        integration.username = None
        integration.status = ConnectionStatus.DISCONNECTED.value
        integration.linked_at = None
        integration.last_error = None
        integration.last_error_class = None
        self.db.flush()
        return self.status(user)

    # --- helpers --------------------------------------------------------
    async def _verify_token(self, token: str) -> dict:
        client = self.client_for_token(token)
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            return await client.verify()  # type: ignore[attr-defined]
        except TelegramError as exc:
            raise errors.validation_error(str(exc)) from exc
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

    async def _verify_chat(self, token: str, chat_id: str) -> dict:
        client = self.client_for_token(token)
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            return await client.get_chat(chat_id=chat_id)  # type: ignore[attr-defined]
        except TelegramError as exc:
            raise errors.validation_error(str(exc)) from exc
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

    def _refresh_status(self, integration) -> None:
        if integration.bot_token_encrypted and integration.chat_id:
            integration.status = ConnectionStatus.CONNECTED.value
            integration.linked_at = integration.linked_at or datetime.now(timezone.utc)
        elif integration.bot_token_encrypted or integration.chat_id:
            integration.status = ConnectionStatus.PENDING.value
        else:
            integration.status = ConnectionStatus.DISCONNECTED.value

    async def _record_error(self, user: User, exc: TelegramError) -> None:
        integration = self.integration(user)
        integration.last_error = str(exc)[:500]
        integration.last_error_class = (
            exc.error_class.value if hasattr(exc.error_class, "value") else str(exc.error_class)
        )
        integration.last_checked_at = datetime.now(timezone.utc)
        if exc.error_class.value == "auth":
            integration.status = ConnectionStatus.NEEDS_REAUTH.value
        elif integration.status == ConnectionStatus.CONNECTED.value:
            integration.status = ConnectionStatus.ERROR.value
        self.db.flush()


__all__ = ["TelegramConfigService", "default_telegram_factory", "settings"]
