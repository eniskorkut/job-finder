from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

_TEST_DIR = Path(tempfile.mkdtemp(prefix="jobhunter-tests-"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR / 'test.db'}"
os.environ["DATA_DIR"] = str(_TEST_DIR / "data")
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["APP_ENCRYPTION_KEY"] = (
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # noqa: S105 - test key
)
os.environ["COOKIE_SECURE"] = "false"
os.environ["LOGIN_RATE_LIMIT_ATTEMPTS"] = "5"
os.environ["LOGIN_RATE_LIMIT_WINDOW_SECONDS"] = "900"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-google-client-id.apps.googleusercontent.com"
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-google-client-secret"
os.environ["MICROSOFT_OAUTH_CLIENT_ID"] = "test-microsoft-client-id"
os.environ["MICROSOFT_OAUTH_CLIENT_SECRET"] = "test-microsoft-client-secret"
os.environ["MICROSOFT_OAUTH_TENANT"] = "consumers"

import pytest  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.core.config import BACKEND_DIR, settings  # noqa: E402
from app.core.rate_limit import SlidingWindowRateLimiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402,F401,F403
from app.models.enums import (  # noqa: E402
    ErrorClass,
    SyncJobAccountStatus,
)
from app.models.sync_job import SyncJobAccount  # noqa: E402
from app.seed import DEFAULT_DEMO_PASSWORD, seed_demo_data  # noqa: E402
from app.services.auth_service import login_limiter  # noqa: E402
from app.services.user_service import UserService  # noqa: E402

TEST_PASSWORD = DEFAULT_DEMO_PASSWORD
USER1_PASSWORD = "User1-Parola!2026"
USER2_PASSWORD = "User2-Parola!2026"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url or settings.database_url)
    return config


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture(autouse=True)
def clean_database(apply_migrations: None) -> None:
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))
    login_limiter.reset()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def limiter() -> SlidingWindowRateLimiter:
    return login_limiter


@pytest.fixture
def user1(db):
    service = UserService(db)
    user = service.create_user(
        username="testuser1",
        email="user1@example.com",
        password=USER1_PASSWORD,
        full_name="Test User One",
        make_owner=True,
    )
    db.commit()
    return user


@pytest.fixture
def user2(db):
    service = UserService(db)
    user = service.create_user(
        username="testuser2",
        email="user2@example.com",
        password=USER2_PASSWORD,
        full_name="Test User Two",
    )
    db.commit()
    return user


class ApiClient:
    """TestClient wrapper that always sends the CSRF header like the SPA does."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    @property
    def cookies(self):
        return self._client.cookies

    def _csrf(self) -> str | None:
        return self._client.cookies.get(settings.csrf_cookie_name)

    def request(self, method: str, url: str, **kwargs):
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            token = self._csrf()
            headers = dict(kwargs.pop("headers", {}) or {})
            if token:
                headers.setdefault(settings.csrf_header_name, token)
            kwargs["headers"] = headers
        return self._client.request(method, url, **kwargs)

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def login(self, identifier: str, password: str):
        response = self.post(
            "/api/v1/auth/login",
            json={"identifier": identifier, "password": password},
        )
        return response

    def ensure_csrf(self) -> None:
        self.get("/api/v1/auth/csrf")


@contextmanager
def api_client():
    with TestClient(app) as client:
        wrapper = ApiClient(client)
        wrapper.ensure_csrf()
        yield wrapper


@pytest.fixture
def api() -> ApiClient:
    """Anonymous browser (no session)."""
    with api_client() as wrapper:
        yield wrapper


@pytest.fixture
def api_user1(user1) -> ApiClient:
    """Independent browser logged in as user1."""
    with api_client() as wrapper:
        response = wrapper.login("testuser1", USER1_PASSWORD)
        assert response.status_code == 200, response.text
        yield wrapper


@pytest.fixture
def api_user2(user2) -> ApiClient:
    """Independent browser logged in as user2 (own cookie jar)."""
    with api_client() as wrapper:
        response = wrapper.login("testuser2", USER2_PASSWORD)
        assert response.status_code == 200, response.text
        yield wrapper


@pytest.fixture
def seeded(db):
    result = seed_demo_data(db)
    db.commit()
    return result


# ----------------------------------------------------------------------
# Phase 2 helpers: mailbox fixtures built on the fake provider client.
# ----------------------------------------------------------------------
def add_oauth_client(
    db,
    user,
    provider: str = "gmail",
    *,
    client_id: str = "test-client-id.apps.googleusercontent.com",
    client_secret: str = "test-client-secret",
):
    from app.services.oauth_service import OAuthClientService

    config = OAuthClientService(db).save(
        user,
        provider,
        client_id=client_id,
        client_secret=client_secret,
        tenant="consumers" if provider == "outlook" else None,
    )
    db.commit()
    return config


def add_mail_account(
    db,
    user,
    provider: str = "gmail",
    *,
    email_address: str = "ai.hunter.gmail@example.com",
    status: str = "connected",
    filters: dict | None = None,
):
    from app.core.crypto import encrypt_secret
    from app.models.enums import CursorKind
    from app.models.mail_account import MailAccount
    from app.repositories.sync_jobs import CheckpointRepository

    account = MailAccount(
        user_id=user.id,
        provider=provider,
        email_address=email_address,
        display_name="Test Hesabı",
        status=status,
        provider_account_id=f"{provider}-account-1",
        access_token_encrypted=encrypt_secret("access-token-1"),
        refresh_token_encrypted=(
            encrypt_secret("refresh-token-1") if provider == "gmail" else None
        ),
        token_cache_encrypted=(
            encrypt_secret("msal-cache-1") if provider == "outlook" else None
        ),
        scopes=[],
        filters=filters or {},
    )
    db.add(account)
    db.flush()
    CheckpointRepository(db).get_or_create(user.id, account.id)
    db.commit()
    return account


@pytest.fixture
def mailbox(db, user1):
    """A connected Gmail account whose OAuth app belongs to user1."""

    def _factory(
        provider: str = "gmail",
        *,
        email_address: str | None = None,
        user=None,
        filters: dict | None = None,
    ):
        owner = user or user1
        add_oauth_client(db, owner, provider)
        return add_mail_account(
            db,
            owner,
            provider,
            email_address=email_address
            or ("alerts@gmail.example.com" if provider == "gmail" else "alerts@outlook.example.com"),
            filters=filters,
        )

    return _factory


@pytest.fixture
def fake_providers():
    """Build fake provider clients and the factory that returns them."""
    from tests.fakes import FakeClientFactory, FakeMailProviderClient, FakeProviderState

    def _factory(**clients):
        built: dict[str, FakeMailProviderClient] = {}
        for provider, state in clients.items():
            built[provider] = FakeMailProviderClient(provider=provider, state=state)
        return FakeClientFactory(built), built

    return _factory


@pytest.fixture
def telegram_ready(db, user1):
    """user1 with a verified (fake) Telegram bot + chat, token encrypted."""
    import asyncio

    from app.services.telegram_service import TelegramConfigService
    from tests.fakes_phase3 import FakeTelegramState, fake_telegram_factory

    state = FakeTelegramState()
    state.register_chat("424242")
    service = TelegramConfigService(db, client_factory=fake_telegram_factory(state))
    asyncio.run(service.save_config(user1, bot_token=state.token, chat_id="424242"))
    db.commit()
    return state


@dataclass
class ScanResult:
    """Per-mailbox result of a scan run (mirrors SyncJobAccount)."""

    status: object
    messages_scanned: int
    jobs_found: int
    jobs_new: int
    jobs_duplicate: int
    messages_skipped: int
    error_message: str | None
    error_class: object


def run_scan(db, user, account, factory, *, job_id=None, now=None):
    """Run one mailbox scan through the real runner (no worker process)."""
    import asyncio
    import uuid
    from datetime import timedelta

    from app.models.enums import SyncJobStatus
    from app.models.sync_job import SyncJob
    from app.repositories.sync_jobs import SyncJobAccountRepository
    from app.services.sync_job_service import SyncRunner
    from tests.fixtures.emails import RECEIVED_AT

    job = SyncJob(
        id=job_id or uuid.uuid4(),
        user_id=user.id,
        status=SyncJobStatus.QUEUED.value,
        accounts_total=1,
    )
    db.add(job)
    db.flush()
    SyncJobAccountRepository(db).ensure_accounts(job, [account.id])
    db.commit()

    runner = SyncRunner(
        worker_id="test-runner",
        client_factory=factory,
        # Deterministic clock so the first-scan window is stable.
        now=now or (RECEIVED_AT + timedelta(days=1)),
    )
    asyncio.run(runner.execute(job.id))

    db.expire_all()
    row = (
        db.query(SyncJobAccount)
        .filter(SyncJobAccount.sync_job_id == job.id, SyncJobAccount.mail_account_id == account.id)
        .one()
    )
    outcome = ScanResult(
        status=SyncJobAccountStatus(row.status),
        messages_scanned=row.messages_scanned,
        jobs_found=row.jobs_found,
        jobs_new=row.jobs_new,
        jobs_duplicate=row.jobs_duplicate,
        messages_skipped=row.messages_skipped,
        error_message=row.error_message,
        error_class=ErrorClass(row.error_class),
    )
    return job, outcome

