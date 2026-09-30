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
        "title": "Google Cloud - OAuth 2.0 Web Uygulaması",
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
            "Uygulama 'Testing' modundayken Google yenileme token'ı 7 gün sonra geçersiz olur; 'Yeniden yetkilendir' ile yenileyebilirsiniz.",
            "Yalnızca okuma izni (gmail.readonly) istenir; parolanız hiçbir zaman istenmez ve saklanmaz.",
        ],
        "estimated_minutes": 5,
        "prerequisites": [
            "Aktif bir Google / Gmail hesabı",
            "Google Cloud Console erişimi (ücretsizdir, kredi kartı gerekmez)",
        ],
        "official_links": [
            {"label": "Google Cloud Console", "url": "https://console.cloud.google.com"},
            {"label": "Gmail API Dokümantasyonu", "url": "https://developers.google.com/gmail/api"},
        ],
        "structured_steps": [
            {
                "step_number": 1,
                "title": "Google Cloud'da Yeni Proje Oluşturun",
                "description": "Google Cloud Console'a gidin. Üst menüdeki proje seçiciye tıklayıp 'New Project' butonuna basarak 'Job Finder' adında bir proje oluşturun.",
                "action_url": "https://console.cloud.google.com/projectcreate",
                "action_label": "Proje Oluştur",
                "warning": None,
            },
            {
                "step_number": 2,
                "title": "Gmail API'yi Etkinleştirin",
                "description": "Sol menüden 'APIs & Services' > 'Library' (Kütüphane) bölümüne gidin. Arama kutusuna 'Gmail API' yazın ve 'Enable' (Etkinleştir) butonuna basın.",
                "action_url": "https://console.cloud.google.com/apis/library/gmail.googleapis.com",
                "action_label": "Gmail API Kütüphanesi",
                "warning": None,
            },
            {
                "step_number": 3,
                "title": "OAuth Onay Ekranını (Consent Screen) Yapılandırın",
                "description": "'APIs & Services' > 'OAuth consent screen' sayfasına gelin. User Type olarak 'External' (Harici) seçin. Uygulama adını girip ilerleyin. 'Test users' adımında kendi Gmail adresinizi mutlaka ekleyin.",
                "action_url": "https://console.cloud.google.com/apis/credentials/consent",
                "action_label": "OAuth Consent Screen",
                "warning": "Önemli: Uygulama 'Testing' modunda olduğundan yalnızca 'Test users' listesine eklediğiniz Gmail hesapları yetkilendirilebilir!",
            },
            {
                "step_number": 4,
                "title": "OAuth Client ID (Web Application) Oluşturun",
                "description": "'APIs & Services' > 'Credentials' sayfasına gidin. '+ CREATE CREDENTIALS' > 'OAuth client ID' seçin. Application type olarak 'Web application' seçin.",
                "action_url": "https://console.cloud.google.com/apis/credentials",
                "action_label": "Credentials Sayfası",
                "warning": "DİKKAT: 'API Key' oluşturmayın! Job Finder güvenli kullanıcı adına okuma yapabilmek için OAuth 2.0 Web Application Client ID ve Secret kullanır.",
            },
            {
                "step_number": 5,
                "title": "Authorized Redirect URI (Yönlendirme Adresi) Ekleyin",
                "description": "'Authorized redirect URIs' bölümüne aşağıdaki adresi eksiksiz ve birebir ekleyin. Ardından 'Create' butonuna basın.",
                "copyable_text": None,
                "warning": "Adresin sonundaki eğik çizgiye (/), http/https protokolüne ve port numarasına dikkat edin.",
            },
            {
                "step_number": 6,
                "title": "Client ID ve Client Secret'ı Kaydedip Bağlanın",
                "description": "Ekrana gelen Client ID ve Client Secret değerlerini aşağıdaki forma yapıştırın ve 'Kaydet' butonuna basın. Ardından 'Gmail ile bağlan' düğmesine tıklayarak hesabınızı yetkilendirin.",
                "warning": None,
            },
        ],
        "faq": [
            {
                "question": "API Key mi yoksa OAuth Client mı oluşturmam gerekiyor?",
                "answer": "Kesinlikle OAuth Client oluşturulmalıdır. API Key sadece proje kotasını izler, posta kutusu okuyamaz. Job Finder LinkedIn iş ilanlarını posta kutunuzdan okuyabilmek için OAuth 2.0 Web Application kullanır.",
            },
            {
                "question": "Neden 7 gün sonra bağlantı kopuyor ve 'Yeniden yetkilendir' gerekiyor?",
                "answer": "Google Cloud Console'da OAuth Consent Screen 'Testing' (Test) durumundayken verilen Refresh Token'lar Google güvenlik politikası gereği 7 gün geçerlidir. 7 gün sonunda karttaki 'Yeniden yetkilendir' düğmesine basarak tek tıkla yenileyebilirsiniz. Kalıcı kılmak için Google Console'da uygulamayı 'In production' moduna alabilirsiniz.",
            },
            {
                "question": "Google parolam Job Finder ile paylaşılıyor mu?",
                "answer": "Hayır. Yetkilendirme tamamen Google'ın kendi resmi oturum açma sayfasında gerçekleşir. Parolanız asla istenmez veya saklanmaz. Yalnızca okuma izni olan bir erişim belirteci kullanılır.",
            },
            {
                "question": "Hangi izinleri (scopes) vermem gerekiyor?",
                "answer": "Yalnızca 'https://www.googleapis.com/auth/gmail.readonly' (sadece okuma). Job Finder e-posta silme, gönderme veya değiştirme izni kesinlikle istemez.",
            },
        ],
        "troubleshooting": [
            {
                "error_code": "redirect_uri_mismatch",
                "title": "Hata: redirect_uri_mismatch (400)",
                "cause": "Google Cloud Console'a eklenen Authorized redirect URI ile Job Finder'ın yönlendirdiği callback adresi uyuşmuyor.",
                "solution": "Google Cloud > Credentials > Web Client ayarlarındaki 'Authorized redirect URIs' alanına bu ekranda verilen Redirect URI'yi birebir kopyalayıp kaydedin.",
            },
            {
                "error_code": "access_denied",
                "title": "Hata: access_denied",
                "cause": "Google onay ekranında 'İptal'e basıldı veya Gmail adresiniz 'Test users' listesine eklenmemiş.",
                "solution": "Google Cloud Console > OAuth consent screen > 'Test users' bölümüne kendi Gmail adresinizin eklendiğinden emin olup tekrar bağlanın.",
            },
            {
                "error_code": "invalid_client",
                "title": "Hata: invalid_client",
                "cause": "Client ID veya Client Secret yanlış girildi ya da Google Console'dan silindi.",
                "solution": "Google Cloud Console'daki Web Client bilgilerini kontrol edip aşağıdaki formda 'Güncelle' diyerek yeniden kaydedin.",
            },
        ],
    },
    Provider.OUTLOOK.value: {
        "title": "Microsoft Entra - OAuth 2.0 Web Uygulaması",
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
        "estimated_minutes": 5,
        "prerequisites": [
            "Aktif bir Microsoft hesabı (Hotmail, Outlook, Live veya kurumsal Office365)",
            "Microsoft Entra admin center erişimi (entra.microsoft.com - ücretsizdir)",
        ],
        "official_links": [
            {"label": "Microsoft Entra Admin Center", "url": "https://entra.microsoft.com"},
            {"label": "Microsoft Graph Dokümantasyonu", "url": "https://learn.microsoft.com/en-us/graph"},
        ],
        "structured_steps": [
            {
                "step_number": 1,
                "title": "Microsoft Entra'da Uygulama Kaydı Başlatın",
                "description": "entra.microsoft.com adresine gidin. 'Identity' (veya Entra ID) > 'Applications' > 'App registrations' bölümüne gidin ve '+ New registration' butonuna tıklayın.",
                "action_url": "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
                "action_label": "App Registrations",
                "warning": None,
            },
            {
                "step_number": 2,
                "title": "Hesap Türünü Doğru Seçin",
                "description": "Name alanına 'Job Finder' yazın. 'Supported account types' bölümünde MUTLAKA 'Accounts in any organizational directory and personal Microsoft accounts' veya 'Personal Microsoft accounts only' seçeneğini işaretleyin.",
                "warning": "Kişisel Hotmail/Outlook hesabı için 'Single tenant' seçmeyin! Kişisel hesapları destekleyen seçeneği seçmelisiniz.",
            },
            {
                "step_number": 3,
                "title": "Web Platformu ve Redirect URI Ekleyin",
                "description": "Redirect URI bölümünde platform olarak 'Web' seçin ve aşağıdaki adresi yapıştırın. Ardından 'Register' butonuna tıklayın.",
                "copyable_text": None,
                "warning": None,
            },
            {
                "step_number": 4,
                "title": "Client Secret Oluşturun — KRİTİK VALUE UYARISI!",
                "description": "Sol menüden 'Certificates & secrets' sayfasına geçin. '+ New client secret' butonuna tıklayın. Açıklama yazıp 'Add' deyin. DİKKAT: Oluşan tabloda 'Secret ID' kolonu DEĞİL, 'Value' (Değer) kolonundaki metni kopyalayın!",
                "warning": "SIK YAPILAN HATA: 'Secret ID' şifre değildir! Mutlaka 'Value' (Değer) kolonundaki gizli metni kopyalamalısınız. Sayfadan ayrılırsanız Value bir daha görünmez.",
            },
            {
                "step_number": 5,
                "title": "API İzinlerini Kontrol Edin",
                "description": "Sol menüden 'API permissions' sayfasına bakın. Microsoft Graph > Delegated permissions altında 'Mail.Read' ve 'User.Read' izinlerinin eklendiğinden emin olun.",
                "warning": None,
            },
            {
                "step_number": 6,
                "title": "Client ID ve Secret'ı Kaydedip Bağlanın",
                "description": "Overview sayfasındaki 'Application (client) ID' ve oluşturduğunuz Secret 'Value' değerini forma yapıştırın. Kişisel hesaplar için Kiracı olarak 'consumers' seçip 'Kaydet'e basın. Ardından 'Hotmail / Outlook ile bağlan' düğmesine tıklayın.",
                "warning": None,
            },
        ],
        "faq": [
            {
                "question": "Microsoft'ta 'Secret ID' ile 'Value' arasındaki fark nedir?",
                "answer": "'Secret ID', anahtarın Entra sistemindeki kimlik numarasıdır (GUID). 'Value' ise gerçek gizli şifredir (Client Secret). Job Finder'a mutlaka 'Value' değeri girilmelidir. 'Secret ID' girilirse invalid_client hatası oluşur.",
            },
            {
                "question": "Kiracı (Tenant) olarak ne seçmeliyim?",
                "answer": "Kişisel bir @outlook.com, @hotmail.com veya @live.com adresi kullanıyorsanız 'consumers' seçmelisiniz. Şirket/okul Office365 hesabı için 'common' veya firmanıza özel kiracı ID'si kullanılır.",
            },
            {
                "question": "Admin consent (Yönetici Onayı) uyarısı alıyorum?",
                "answer": "Kurumsal bir hesap kullanıyorsanız Azure Active Directory yöneticinizin onayı gerekebilir. Kişisel hesaplar 'consumers' seçtiğinde yönetici onayı gerekmez.",
            },
            {
                "question": "Microsoft şifrem güvende mi?",
                "answer": "Job Finder parolanızı asla istemez veya görmez. Giriş işlemi doğrudan Microsoft sunucularında yapılır ve yalnızca okuma yetkili token sunucumuzda şifreli saklanır.",
            },
        ],
        "troubleshooting": [
            {
                "error_code": "AADSTS50011",
                "title": "Hata: AADSTS50011 (Redirect URI Mismatch)",
                "cause": "Microsoft Entra'da kayıtlı Web Redirect URI ile Job Finder'ın yönlendirdiği adres birebir uyuşmuyor.",
                "solution": "Entra Portal > Authentication > Web bölümünde Redirect URI'nin bu ekranda verilen adresle harfiyen aynı olduğundan emin olun.",
            },
            {
                "error_code": "AADSTS7000215",
                "title": "Hata: AADSTS7000215 (Invalid Client Secret)",
                "cause": "Secret Value yerine 'Secret ID' kopyalanmış veya secret süresi dolmuş.",
                "solution": "Certificates & secrets sekmesine gidin, yeni bir Client Secret oluşturun ve 'Value' kolonundaki değeri kopyalayıp forma kaydedin.",
            },
            {
                "error_code": "access_denied",
                "title": "Hata: access_denied",
                "cause": "İzin ekranında 'İptal'e basıldı veya kuruluşunuz kişisel hesap izinlerini engelliyor.",
                "solution": "Yetkilendirme akışını yeniden başlatıp 'Kabul et' butonuna basın.",
            },
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
        redirect_uri = str(guide["redirect_uri"]())  # type: ignore[operator]
        structured_steps = []
        for step in guide.get("structured_steps", []):  # type: ignore[union-attr]
            s = dict(step)
            if "Redirect URI" in s.get("title", "") and not s.get("copyable_text"):
                s["copyable_text"] = redirect_uri
            structured_steps.append(s)

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
            "redirect_uri": redirect_uri,
            "scopes": guide["scopes"],
            "title": guide["title"],
            "steps": guide["steps"],
            "notes": guide["notes"],
            "estimated_minutes": guide.get("estimated_minutes", 5),
            "prerequisites": guide.get("prerequisites", []),
            "structured_steps": structured_steps,
            "faq": guide.get("faq", []),
            "troubleshooting": guide.get("troubleshooting", []),
            "official_links": guide.get("official_links", []),
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
