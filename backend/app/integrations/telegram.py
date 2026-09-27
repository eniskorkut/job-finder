from __future__ import annotations

from app.integrations.base import IntegrationNotImplemented, NotificationClient


class TelegramClient(NotificationClient):
    """Telegram Bot API notifier - phase 3. Bot token is provided by the user."""

    provider = "telegram"
    phase = "phase-3"

    def __init__(self, bot_token: str | None = None) -> None:
        self.bot_token = bot_token

    def send_message(self, *, destination: str, text: str) -> dict:
        raise IntegrationNotImplemented(self.provider, self.phase, "send_message")

    def verify_destination(self, *, destination: str) -> bool:
        raise IntegrationNotImplemented(self.provider, self.phase, "verify_destination")

    @property
    def configured(self) -> bool:
        return bool(self.bot_token)
