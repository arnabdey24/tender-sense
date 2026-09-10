"""Application settings, loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import (
    PostgresDsn,
    RedisDsn,
    SecretStr,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    environment: Environment = "local"
    debug: bool = False
    project_name: str = "TenderSense"
    api_v1_prefix: str = "/api/v1"
    app_url: str = "http://localhost:5173"
    """Public URL of the SPA; used to build links in emails."""
    backend_cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    secret_key: SecretStr = SecretStr("change-me-in-production-please-32-bytes-min")

    # --- database ---
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "tendersense"
    postgres_password: SecretStr = SecretStr("tendersense")
    postgres_db: str = "tendersense"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    database_url_override: str | None = None

    # --- redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url_override: str | None = None

    # --- auth ---
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    email_verify_token_ttl_hours: int = 24
    password_reset_token_ttl_minutes: int = 60
    invitation_ttl_days: int = 7
    password_min_length: int = 10
    refresh_cookie_name: str = "ts_refresh"
    refresh_cookie_secure: bool = False
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None

    # --- email ---
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    email_from: str = "TenderSense <no-reply@tendersense.local>"
    email_reply_to: str | None = None
    email_max_attempts: int = 6

    # --- AI ---
    ai_provider: Literal["gemini", "fake"] = "gemini"
    gemini_api_key: SecretStr | None = None
    embedding_model: str = "gemini-embedding-2"
    embedding_fallback_model: str = "gemini-embedding-001"
    embedding_dims: int = 768
    generation_model: str = "gemini-3.1-flash-lite"
    ai_max_concurrency: int = 5
    ai_requests_per_minute: int = 12
    ai_daily_token_budget: int = 2_000_000

    # --- matching defaults (overridable per-deployment via matching_config table) ---
    grade_s_threshold: float = 0.78
    grade_a_threshold: float = 0.70
    grade_b_threshold: float = 0.62

    # --- ingestion ---
    blob_storage_dir: str = "/var/lib/tendersense/blobs"
    scraper_user_agent: str = "TenderSenseBot/1.0 (+https://tendersense.local/bot)"
    scraper_request_delay_seconds: float = 2.0
    scraper_max_pages_per_run: int = 20

    # --- retention & housekeeping ---
    job_run_retention_days: int = 30
    """How long ``job_runs`` and ``scraper_runs`` are kept before the nightly purge."""
    source_stale_hours: int = 36
    """No successful scrape in this long marks a source degraded."""
    fx_rates_url: str = "https://open.er-api.com/v6/latest"
    """Base URL of a free rates endpoint; ``/{base}`` is appended. Blank disables the refresh."""
    fx_base_currency: str = "USD"

    # --- observability ---
    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def _require_a_strong_secret_in_production(self) -> Settings:
        """A short or default signing key would make access tokens forgeable."""
        if not self.is_production:
            return self
        secret = self.secret_key.get_secret_value()
        if len(secret) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        if secret.startswith("change-me"):
            raise ValueError("SECRET_KEY still holds its placeholder value")
        return self

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept a comma-separated string from the environment.

        ``NoDecode`` stops pydantic-settings from JSON-parsing the raw value
        first, which would reject ``a,b`` before this validator ever runs.
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Includes the password, so it is excluded from ``repr``."""
        if self.database_url_override:
            return self.database_url_override
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password.get_secret_value(),
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        if self.redis_url_override:
            return self.redis_url_override
        return str(
            RedisDsn.build(
                scheme="redis",
                host=self.redis_host,
                port=self.redis_port,
                path=str(self.redis_db),
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
