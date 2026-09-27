"""OAuth application credentials and the authorization-code flow.

Every user registers their own Google / Microsoft Entra application. The
client secret is encrypted with ``APP_ENCRYPTION_KEY`` before it touches the
database and only ever leaves the server masked.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.security import OAUTH_STATE_BYTES, generate_token
from app.core.security import hash_token
from app.integrations.base import MailProviderClient, ProviderIdentity
from app.integrations.errors import ProviderError
from app.integrations.gmail import GmailClient
from app.integrations.http import ProviderHttpClient
from app.integrations.outlook import OutlookClient
from app.models.enums import ConnectionStatus, ErrorClass, Provider
from app.models.mail_account import MailAccount
from app.models.oauth import OAuthState
from app.models.oauth_client import OAuthClientConfig
from app.models.user import User, UserSession
from app.repositories.integrations import SyncHistoryRepository
from app.repositories.jobs import MailAccountRepository
from app.repositories.oauth import OAuthStateRepository
from app.repositories.oauth_clients import OAuthClientRepository
from app.repositories.sync_jobs import CheckpointRepository

STATE_TTL = timedelta(minutes=10)
SUPPORTED_PROVIDERS = (Provider.GMAIL.value, Provider.OUTLOOK.value)
MAX_CLIENT_ID_LENGTH = 255
MAX_SECRET_LENGTH = 400

PROVIDER_GUIDES: dict[str, dict[str, object]] = {
    Provider.GMAIL.value: {
        "title": "Google Cloud - OAuth Web uygulaması",
        "redirect_uri": lambda: settings.gmail_redirect_uri,
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly", "openid", "email"],
        "steps": [
            "console.cloud.google.com üzerinde bir proje oluşturun.",
            "APIs & Services > Library bölümünden Gmail API'yi etkinleştirin.",
            "OAuth consent screen'i dış (External) türde yayınlayın ve test kullanıcılarına kendi Gmail adresinizi ekleyin.",
            "Credentials > Create credentials > OAuth client ID > Web application seçin.",
            "Authorized redirect URIs alanına aşağıdaki adresi birebir ekleyin.",
            "Client ID ve Client Secret değerlerini bu ekrandaki forma yapıştırın.",
        ],
        "notes": [
            "Uygulama 'Testing' modundayken Google yenileme token'ı 7 gün sonra geçersiz olur; yeniden bağlanmanız gerekir.",
            "Yalnızca okuma izni (gmail.readonly) istenir; parolanız hiçbir zaman istenmez ve saklanmaz.",
        ],
    },
    Provider.OUTLOOK.value: {
        "title": "Microsoft Entra - Web uygulaması",
        "redirect_uri": lambda: settings.outlook_redirect_uri,
        "scopes": ["Mail.Read", "User.Read", "offline_access"],
        "steps": [
            "entra.microsoft.com > Entra ID > App registrations > New registration.",
            "Supported account types: kişisel Microsoft hesapları dahil seçeneği (personal Microsoft accounts).",
            "Platform olarak Web ekleyin ve aşağıdaki redirect URI'yi birebir yazın.",
            "Certificates & secrets > New client secret oluşturup değeri forma yapıştırın.",
            "API permissions: Microsoft Graph > Delegated > Mail.Read, User.Read (+ offline_access zaten otomatiktir).",
        ],
        "notes": [
            "Kişisel Hotmail/Outlook/Live hesapları 'consumers' kiracısı ile yetkilendirilir.",
            "Client secret süresi dolduğunda yeni secret ile bu formu güncelleyip yeniden bağlanın.",
        ],
    },
}


@dataclass(slots=True)
class LinkedAccountResult:
    account: MailAccount
    created: bool


@dataclass(slots=True)
class ClientFactory:
    """Builds provider clients. Tests inject fakes here instead of patching HTTP."""

    http_factory: object = ProviderHttpClient
    gmail_cls: type[MailProviderClient] = GmailClient
    outlook_cls: type[MailProviderClient] = OutlookClient

    def build(
        self,
        *,
        provider: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str | None,
        tenant: str | None = None,
    ) -> MailProviderClient:
        if provider == Provider.GMAIL.value:
            return self.gmail_cls(  # type: ignore[call-arg]
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        if provider == Provider.OUTLOOK.value:
            return self.outlook_cls(  # type: ignore[call-arg]
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                tenant=tenant,
            )
        raise errors.validation_error(f"Desteklenmeyen sağlayıcı: {provider}")


# ----------------------------------------------------------------------
class OAuthClientService:
    """CRUD for the user's own OAuth application credentials."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.clients = OAuthClientRepository(db)
        self.accounts = MailAccountRepository(db)

    def get_or_raise(self, user_id: uuid.UUID, provider: str) -> OAuthClientConfig:
        config = self.clients.get_for_user_provider(user_id, provider)
        if config is None:
            raise errors.validation_error(
                f"{self._label(provider)} istemci bilgileri kayıtlı değil. "
                "Önce Client ID ve Client Secret bilgilerini kaydedin."
            )
        return config

    def save(
        self,
        user: User,
        provider: str,
        *,
        client_id: str,
        client_secret: str | None,
        tenant: str | None = None,
    ) -> OAuthClientConfig:
        self._validate_provider(provider)
        client_id = (client_id or "").strip()
        if not 8 <= len(client_id) <= MAX_CLIENT_ID_LENGTH:
            raise errors.validation_error("Client ID geçersiz görünüyor.")
        if client_secret is not None:
            client_secret = client_secret.strip() or None
            if client_secret and len(client_secret) > MAX_SECRET_LENGTH:
                raise errors.validation_error("Client Secret çok uzun.")

        existing = self.clients.get_for_user_provider(user.id, provider)
        if existing is None and not client_secret:
            raise errors.validation_error(
                "İlk kayıtta Client Secret zorunludur (gizli istemci akışı kullanılıyor)."
            )

        redirect_uri = (
            settings.gmail_redirect_uri
            if provider == Provider.GMAIL.value
            else settings.outlook_redirect_uri
        )
        client_secret_encrypted = (
            encrypt_secret(client_secret) if client_secret else None
        )
        return self.clients.upsert(
            user.id,
            provider,
            client_id=client_id,
            client_secret_encrypted=client_secret_encrypted,
            tenant=(tenant or "").strip() or None if provider == Provider.OUTLOOK.value else None,
            redirect_uri=redirect_uri,
        )

    def delete(self, user: User, provider: str) -> None:
        self._validate_provider(provider)
        config = self.clients.get_for_user_provider(user.id, provider)
        if config is None:
            raise errors.not_found("Kayıtlı istemci bilgisi bulunamadı.")
        for account in self.accounts.list_for_user(user.id):
            if account.provider != provider:
                continue
            if account.status == ConnectionStatus.CONNECTED.value:
                account.status = ConnectionStatus.NEEDS_REAUTH.value
                account.last_error = (
                    "OAuth istemci bilgileri silindi; yeniden yapılandırıp bağlanın."
                )
        self.clients.delete_for_user_provider(user.id, provider)

    def public_view(self, user: User, provider: str) -> dict:
        config = self.clients.get_for_user_provider(user.id, provider)
        guide = PROVIDER_GUIDES[provider]
        return {
            "provider": provider,
            "configured": config is not None,
            "client_id": config.client_id if config else None,
            "client_secret_hint": (
                mask_secret(decrypt_secret(config.client_secret_encrypted))
                if config and config.client_secret_encrypted
                else None
            ),
            "tenant": config.tenant if config else None,
            "redirect_uri": guide["redirect_uri"](),  # type: ignore[operator]
            "scopes": guide["scopes"],
            "title": guide["title"],
            "steps": guide["steps"],
            "notes": guide["notes"],
            "updated_at": config.updated_at.isoformat() if config else None,
        }

    def client_for_account(self, account: MailAccount, user_id: uuid.UUID):
        config = self.get_or_raise(user_id, account.provider)
        return ClientFactory().build(
            provider=account.provider,
            client_id=config.client_id,
            client_secret=(
                decrypt_secret(config.client_secret_encrypted)
                if config.client_secret_encrypted
                else None
            ),
            redirect_uri=config.redirect_uri,
            tenant=config.tenant,
        )

    @staticmethod
    def _validate_provider(provider: str) -> None:
        if provider not in SUPPORTED_PROVIDERS:
            raise errors.validation_error(f"Desteklenmeyen sağlayıcı: {provider}")

    @staticmethod
    def _label(provider: str) -> str:
        return "Gmail" if provider == Provider.GMAIL.value else "Microsoft"


# ----------------------------------------------------------------------
class OAuthFlowService:
    """Authorization-code flow with single-use state bound to the session."""

    def __init__(
        self,
        db: Session,
        *,
        client_factory: ClientFactory | None = None,
        state_ttl: timedelta = STATE_TTL,
    ) -> None:
        self.db = db
        self.clients = OAuthClientService(db)
        self.states = OAuthStateRepository(db)
        self.accounts = MailAccountRepository(db)
        self.checkpoints = CheckpointRepository(db)
        self.sync_history = SyncHistoryRepository(db)
        self.factory = client_factory or ClientFactory()
        self.state_ttl = state_ttl

    # --- start ---------------------------------------------------------
    def start(
        self,
        user: User,
        session: UserSession,
        provider: str,
        *,
        account_id: uuid.UUID | None = None,
        login_hint: str | None = None,
    ) -> dict:
        OAuthClientService._validate_provider(provider)
        config = self.clients.get_or_raise(user.id, provider)
        client_secret = (
            decrypt_secret(config.client_secret_encrypted)
            if config.client_secret_encrypted
            else None
        )

        target_account = None
        if account_id is not None:
            target_account = self.accounts.get_by_provider(user.id, provider, account_id)
            if target_account is None:
                raise errors.not_found("Yeniden bağlanacak hesap bulunamadı.")

        raw_state = generate_token(OAUTH_STATE_BYTES)
        code_verifier = generate_token(64)
        challenge = _pkce_challenge(code_verifier)

        # Invalidate older pending states for the same session/provider so a
        # stale browser tab cannot complete a newer flow.
        for stale in self.states.list_pending_for_session(session.id, provider):
            self.states.consume(stale)

        state = OAuthState(
            user_id=user.id,
            provider=provider,
            state_hash=hash_token(raw_state),
            code_verifier_encrypted=encrypt_secret(code_verifier),
            redirect_uri=config.redirect_uri,
            session_id=session.id,
            mail_account_id=target_account.id if target_account else None,
            expires_at=datetime.now(timezone.utc) + self.state_ttl,
        )
        self.db.add(state)
        self.db.flush()

        client = self.factory.build(
            provider=provider,
            client_id=config.client_id,
            client_secret=client_secret,
            redirect_uri=config.redirect_uri,
            tenant=config.tenant,
        )
        authorization_url = client.authorization_url(
            state=raw_state,
            code_challenge=challenge if provider == Provider.GMAIL.value else None,
            login_hint=login_hint or (target_account.email_address if target_account else None),
        )
        return {
            "authorization_url": authorization_url,
            "provider": provider,
            "expires_at": state.expires_at,
            "redirect_uri": config.redirect_uri,
            "account_id": str(target_account.id) if target_account else None,
        }

    # --- callback ------------------------------------------------------
    async def complete(
        self,
        *,
        state_token: str,
        provider: str,
        code: str | None,
        error: str | None,
        session: UserSession | None,
    ) -> LinkedAccountResult:
        state = self.states.get_valid(state_token)
        if state is None:
            raise errors.forbidden(
                "OAuth state geçersiz, süresi dolmuş veya daha önce kullanılmış."
            )
        if state.provider != provider:
            raise errors.forbidden("OAuth state sağlayıcı ile eşleşmiyor.")
        if session is None or state.session_id != session.id:
            raise errors.forbidden(
                "OAuth akışı farklı bir oturumda başlatılmış; işlem reddedildi."
            )
        if state.user_id != session.user_id:
            raise errors.forbidden("OAuth akışı farklı bir kullanıcıya ait.")

        # Single use: burn the state before talking to the provider.
        self.states.consume(state)
        self.db.flush()

        if error:
            raise errors.validation_error(f"Sağlayıcı yetkilendirmeyi reddetti: {error}")
        if not code:
            raise errors.validation_error("Yetkilendirme kodu gelmedi.")

        config = self.clients.get_or_raise(state.user_id, provider)
        client_secret = (
            decrypt_secret(config.client_secret_encrypted)
            if config.client_secret_encrypted
            else None
        )
        verifier = (
            decrypt_secret(state.code_verifier_encrypted)
            if state.code_verifier_encrypted
            else None
        )

        client = self.factory.build(
            provider=provider,
            client_id=config.client_id,
            client_secret=client_secret,
            redirect_uri=config.redirect_uri,
            tenant=config.tenant,
        )

        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            tokens = await client.exchange_code(
                code=code,
                code_verifier=verifier if provider == Provider.GMAIL.value else None,
                cache=None,
            )
            identity = await client.verify_identity(access_token=tokens.access_token)
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

        return self.upsert_account(
            user_id=state.user_id,
            provider=provider,
            identity=identity,
            tokens=tokens,
            target_account_id=state.mail_account_id,
        )

    def upsert_account(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        identity: ProviderIdentity,
        tokens,
        target_account_id: uuid.UUID | None = None,
    ) -> LinkedAccountResult:
        account = None
        if target_account_id is not None:
            account = self.accounts.get_for_user(user_id, target_account_id)
        if account is None:
            account = self.accounts.get_by_address(user_id, provider, identity.email_address)

        created = account is None
        if account is None:
            account = MailAccount(
                user_id=user_id,
                provider=provider,
                email_address=identity.email_address,
                filters={},
            )
            self.db.add(account)
            self.db.flush()

        account.email_address = identity.email_address
        account.provider_account_id = identity.provider_account_id
        account.display_name = identity.display_name or account.display_name
        account.status = ConnectionStatus.CONNECTED.value
        account.last_error = None
        account.access_token_encrypted = encrypt_secret(tokens.access_token)
        if tokens.refresh_token:
            account.refresh_token_encrypted = encrypt_secret(tokens.refresh_token)
        if tokens.cache_serialized:
            account.token_cache_encrypted = encrypt_secret(tokens.cache_serialized)
        account.token_expires_at = tokens.expires_at
        account.scopes = list(tokens.scopes)

        checkpoint = self.checkpoints.get_or_create(user_id, account.id)
        if account.initial_sync_completed is False and checkpoint.initial_sync_completed:
            account.initial_sync_completed = True
        if account.provider_account_id != identity.provider_account_id:
            # Different backing account: start from a clean cursor.
            self.checkpoints.reset_cursor(checkpoint, reason="Hesap yeniden bağlandı.")
        self.db.flush()
        return LinkedAccountResult(account=account, created=created)

    # --- maintenance ---------------------------------------------------
    async def test_connection(self, user: User, account: MailAccount) -> dict:
        config = self.clients.get_or_raise(user.id, account.provider)
        client_secret = (
            decrypt_secret(config.client_secret_encrypted)
            if config.client_secret_encrypted
            else None
        )
        client = self.factory.build(
            provider=account.provider,
            client_id=config.client_id,
            client_secret=client_secret,
            redirect_uri=config.redirect_uri,
            tenant=config.tenant,
        )
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            tokens = await client.refresh(
                refresh_token=(
                    decrypt_secret(account.refresh_token_encrypted)
                    if account.refresh_token_encrypted
                    else None
                ),
                cache=(
                    decrypt_secret(account.token_cache_encrypted)
                    if account.token_cache_encrypted
                    else None
                ),
                account_id=account.provider_account_id,
            )
            identity = await client.verify_identity(access_token=tokens.access_token)
        except ProviderError as exc:
            account.status = (
                ConnectionStatus.NEEDS_REAUTH.value
                if exc.error_class == ErrorClass.AUTH
                else ConnectionStatus.ERROR.value
            )
            account.last_error = str(exc)[:500]
            self.db.flush()
            return {"ok": False, "message": str(exc), "status": account.status}
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

        note = None
        if identity.email_address != account.email_address:
            note = (
                f"Sağlayıcı bu hesap için {identity.email_address} adresini bildirdi; "
                "kayıt güncellendi."
            )
            account.email_address = identity.email_address
        account.provider_account_id = identity.provider_account_id
        account.status = ConnectionStatus.CONNECTED.value
        account.last_error = None
        account.access_token_encrypted = encrypt_secret(tokens.access_token)
        if tokens.refresh_token:
            account.refresh_token_encrypted = encrypt_secret(tokens.refresh_token)
        if tokens.cache_serialized:
            account.token_cache_encrypted = encrypt_secret(tokens.cache_serialized)
        account.token_expires_at = tokens.expires_at
        self.db.flush()
        return {"ok": True, "message": note or "Bağlantı çalışıyor.", "status": account.status}

    def disconnect(self, user: User, account: MailAccount) -> None:
        """Drop tokens/cache and scan state. Past jobs are intentionally kept."""
        account.access_token_encrypted = None
        account.refresh_token_encrypted = None
        account.token_cache_encrypted = None
        account.token_expires_at = None
        account.status = ConnectionStatus.DISCONNECTED.value
        account.last_error = None
        self.db.flush()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


__all__ = [
    "ClientFactory",
    "LinkedAccountResult",
    "OAuthClientService",
    "OAuthFlowService",
    "PROVIDER_GUIDES",
]
