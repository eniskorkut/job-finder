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

    # --- Phase 2: mailbox scan -------------------------------------------
    # First scan window. Historical full-mailbox scans must be requested
    # explicitly; these bound the default work per run.
    sync_initial_window_days: int = 7
    sync_initial_max_messages: int = 100
    sync_max_results_per_run: int = 200
    sync_batch_size: int = 25

    # Concurrency: total mailboxes worked in parallel and outbound requests
    # per mailbox. Keep these conservative because provider quotas are real.
    sync_max_active_mailboxes: int = 4
    sync_mailbox_concurrency: int = 2

    # Durable job queue
    sync_lease_seconds: int = 180
    sync_heartbeat_seconds: int = 15
    sync_job_timeout_seconds: int = 900
    sync_max_attempts: int = 3
    worker_poll_seconds: float = 2.0
    worker_id: str = ""

    # Testing & simulation hooks (never active in production unless explicitly set)
    enable_acceptance_test_hooks: bool = False
    test_job_delay_seconds: float = 0.0
    test_barrier_file: str | None = None

    def is_test_hook_allowed(self) -> bool:
        """Testing hooks (e.g. test_delay_seconds, test_barrier) are strictly forbidden
        in production and only active in test/development when explicitly enabled.
        """
        if (self.environment or "").lower() not in {"test", "development"}:
            return False
        return bool(self.enable_acceptance_test_hooks)

    # Outbound HTTP
    sync_http_timeout_seconds: float = 30.0
    sync_http_max_connections: int = 10
    sync_retry_max_attempts: int = 4
    sync_retry_base_delay_seconds: float = 1.0
    sync_retry_max_delay_seconds: float = 30.0

    # Hosts we are willing to follow provider continuation links to. Used to
    # reject attacker controlled URLs before attaching an access token.
    graph_allowed_hosts: str = "graph.microsoft.com"
    google_allowed_hosts: str = (
        "www.googleapis.com,gmail.googleapis.com,oauth2.googleapis.com,accounts.google.com"
    )
    microsoft_allowed_hosts: str = (
        "login.microsoftonline.com,login.live.com,graph.microsoft.com"
    )

    # --- Phase 3: shared LLM (OpenAI-compatible, deployment wide) ---------
    # The endpoint may be an official DeepSeek API or any OpenAI-compatible
    # gateway; key/base/model always come from configuration.
    llm_max_concurrency: int = 3
    llm_timeout_seconds: float = 60.0
    llm_retry_max_attempts: int = 3
    llm_json_mode: bool = True
    llm_max_tokens: int = 2000
    llm_temperature: float = 0.1
    llm_prompt_version: str = "phase3-v1"
    # Bounded context: the CV profile is always sent, this caps the raw excerpt.
    llm_cv_context_chars: int = 3000
    llm_job_description_chars: int = 6000
    # Attempts per (user, job, cv version) before a match is parked as failed.
    llm_max_analysis_attempts: int = 3
    # Some OpenAI-compatible gateways need extra routing headers. OpenCode Go,
    # for example, asks for a stable session id per conversation.
    llm_session_header: str = "x-opencode-session"
    llm_session_id: str = ""  # empty -> derived once per installation
    llm_user_agent: str = "job-finder/1.0"
    # JSON object of additional headers, e.g. '{"X-Org": "team"}'
    llm_extra_headers: str = ""

    # --- Phase 3: Telegram (per user, token stored encrypted) -------------
    telegram_api_base: str = "https://api.telegram.org"
    telegram_timeout_seconds: float = 20.0
    telegram_max_message_chars: int = 3500
    telegram_retry_max_attempts: int = 3
    telegram_max_notification_attempts: int = 3

    # --- Phase 3: scheduler (runs inside the worker process) --------------
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = 60
    scheduler_min_interval_hours: int = 1
    scheduler_max_interval_hours: int = 168
    scheduler_jitter_seconds: int = 30

    # --- Phase 4: Job Discovery, Enrichment & Freshness -------------------
    web_search_provider: str = "searxng"  # searxng | mock | none
    web_search_searxng_url: str = "http://localhost:8080"
    web_search_searxng_secret_key: str | None = None
    web_search_max_concurrency: int = 2
    web_search_max_queries_per_job: int = 4
    web_search_max_results_per_query: int = 5
    web_search_timeout_seconds: float = 10.0
    web_search_retry_max_attempts: int = 3

    web_fetch_max_concurrency: int = 4
    web_fetch_timeout_seconds: float = 15.0
    web_fetch_max_bytes: int = 2 * 1024 * 1024  # 2MB
    web_fetch_max_redirects: int = 5
    web_fetch_allowed_ports: str = "80,443"
    web_fetch_retry_max_attempts: int = 3
    web_fetch_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (JobHunter/1.0)"
    )

    job_fresh_days: int = 3
    job_aging_days: int = 7
    job_stale_days: int = 14
    job_max_age_days: int = 14  # Cut-off for automatic LLM scoring
    job_enrichment_min_words: int = 40  # Description < 40 words considered short/inadequate
    job_enrichment_ttl_hours: int = 24  # Re-enrichment TTL policy

    @property
    def allowed_fetch_ports(self) -> set[int]:
        ports: set[int] = set()
        for p in (self.web_fetch_allowed_ports or "80,443").split(","):
            p = p.strip()
            if p.isdigit():
                ports.add(int(p))
        return ports or {80, 443}

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
    def graph_hosts(self) -> list[str]:
        return _split_hosts(self.graph_allowed_hosts)

    @property
    def google_hosts(self) -> list[str]:
        return _split_hosts(self.google_allowed_hosts)

    @property
    def microsoft_hosts(self) -> list[str]:
        return _split_hosts(self.microsoft_allowed_hosts)

    @property
    def gmail_redirect_uri(self) -> str:
        return f"{self.backend_url.rstrip('/')}/api/v1/integrations/gmail/callback"

    @property
    def outlook_redirect_uri(self) -> str:
        return f"{self.backend_url.rstrip('/')}/api/v1/integrations/outlook/callback"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_configured(self) -> bool:
        return bool(self.deepseek_api_key and self.deepseek_model and self.deepseek_base_url)


def _split_hosts(value: str) -> list[str]:
    return [host.strip().lower() for host in value.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
