from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings.

    Values are read from (in order of precedence) environment variables,
    ``backend/.env.local`` and ``backend/.env``.
    """

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Job Hunter"
    environment: str = "development"
    debug: bool = True

    database_url: str = "sqlite:///./jobhunter.db"

    session_secret: str = "dev-session-secret-change-me"
    app_encryption_key: str = ""

    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4.1-flash"

    session_cookie_name: str = "jh_session"
    session_ttl_days: int = 14
    csrf_cookie_name: str = "jh_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False
    cookie_domain: str | None = None

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 900

    invitation_ttl_hours: int = 48

    data_dir: str = "./data"

    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path

    @property
    def cv_storage_path(self) -> Path:
        return self.data_path / "cvs"

    @property
    def allowed_origins(self) -> list[str]:
        origins = {self.frontend_url, self.backend_url}
        origins.update(self.cors_origins)
        return sorted(origins)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
