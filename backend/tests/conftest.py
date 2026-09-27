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

import pytest  # noqa: E402
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
