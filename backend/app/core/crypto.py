"""Symmetric encryption helpers for third party credentials.

Phase 1 only wires the plumbing: OAuth refresh tokens, bot tokens and code
verifiers are stored encrypted so the schema does not change in phase 2.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class EncryptionNotConfigured(RuntimeError):
    pass


def _build_fernet() -> Fernet:
    key = settings.app_encryption_key.strip()
    if key:
        try:
            return Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:  # pragma: no cover - config guard
            raise EncryptionNotConfigured(
                "APP_ENCRYPTION_KEY geçerli bir Fernet anahtarı değil."
            ) from exc

    if settings.environment in {"development", "test"}:
        # Deterministic development fallback derived from SESSION_SECRET so the
        # app runs before the operator fills .env.local in.
        digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    raise EncryptionNotConfigured("APP_ENCRYPTION_KEY tanımlanmamış.")


def encrypt_secret(value: str) -> str:
    return _build_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _build_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionNotConfigured("Şifreli veri çözülemedi.") from exc


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"
