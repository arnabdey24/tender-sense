"""Settings parsing, especially values that arrive as environment strings."""

from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-0123456789abcdef")


def test_cors_origins_accept_a_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker Compose passes this as `a,b` — not as JSON."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com,https://admin.example.com")

    settings = Settings(_env_file=None)

    assert settings.backend_cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_cors_origins_tolerate_whitespace_and_blanks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", " https://a.example.com , , https://b.example.com ")

    settings = Settings(_env_file=None)

    assert settings.backend_cors_origins == ["https://a.example.com", "https://b.example.com"]


def test_single_origin_is_still_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://only.example.com")

    settings = Settings(_env_file=None)

    assert settings.backend_cors_origins == ["https://only.example.com"]


def test_database_url_is_built_from_the_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "someone")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_DB", "tenders")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://someone:secret@db.internal:5433/tenders"


def test_database_url_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL_OVERRIDE", "postgresql+asyncpg://x:y@elsewhere:5432/other")

    settings = Settings(_env_file=None)

    assert settings.database_url.endswith("@elsewhere:5432/other")


def test_redis_url_is_built_from_the_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_HOST", "cache.internal")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "3")

    settings = Settings(_env_file=None)

    assert settings.redis_url == "redis://cache.internal:6380/3"


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("local", False), ("test", False), ("staging", True), ("production", True)],
)
def test_is_production_covers_deployed_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str, expected: bool
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)

    assert Settings(_env_file=None).is_production is expected


def test_secrets_are_not_exposed_by_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "super-secret-value")

    settings = Settings(_env_file=None)

    assert "super-secret-value" not in repr(settings)


class TestSecretKeyPolicy:
    def test_production_rejects_a_short_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "too-short")

        with pytest.raises(ValueError, match="at least 32 characters"):
            Settings(_env_file=None)

    def test_production_rejects_the_placeholder_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "change-me-in-production-please-32-bytes-min")

        with pytest.raises(ValueError, match="placeholder"):
            Settings(_env_file=None)

    def test_production_accepts_a_strong_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "a" * 64)

        assert Settings(_env_file=None).is_production is True

    def test_local_development_tolerates_a_weak_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Developers should not need to generate a key to run the tests."""
        monkeypatch.setenv("ENVIRONMENT", "local")
        monkeypatch.setenv("SECRET_KEY", "short")

        assert Settings(_env_file=None).environment == "local"
