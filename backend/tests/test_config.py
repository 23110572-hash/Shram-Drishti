"""Configuration behaviour, especially the Neon URL handling."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

NEON_POOLED = (
    "postgresql://neondb_owner:secret@ep-x-pooler.c-5.us-east-2.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)
NEON_DIRECT = "postgresql://neondb_owner:secret@ep-x.c-5.us-east-2.aws.neon.tech/neondb"


def _settings(url: str) -> Settings:
    return Settings(database_url=url, _env_file=None)  # type: ignore[call-arg]


class TestDriverNormalisation:
    def test_plain_postgresql_url_gets_psycopg_driver(self) -> None:
        # Neon's dashboard gives postgresql:// which SQLAlchemy maps to psycopg2,
        # a driver we do not install.
        assert _settings(NEON_POOLED).database_url.startswith("postgresql+psycopg://")

    def test_postgres_scheme_alias_is_normalised(self) -> None:
        s = _settings("postgres://u:p@host/db")
        assert s.database_url.startswith("postgresql+psycopg://")

    def test_explicit_driver_is_left_alone(self) -> None:
        url = "postgresql+psycopg://u:p@host/db"
        assert _settings(url).database_url == url

    def test_query_parameters_survive_normalisation(self) -> None:
        # Dropping sslmode would make Neon reject the connection.
        result = _settings(NEON_POOLED).database_url
        assert "sslmode=require" in result
        assert "channel_binding=require" in result


class TestPgBouncerDetection:
    def test_pooled_endpoint_is_detected(self) -> None:
        assert _settings(NEON_POOLED).uses_pgbouncer is True

    def test_direct_endpoint_is_not_flagged(self) -> None:
        assert _settings(NEON_DIRECT).uses_pgbouncer is False


class TestPasswordMasking:
    def test_password_is_masked(self) -> None:
        masked = _settings(NEON_POOLED).safe_database_url()
        assert "secret" not in masked
        assert "***" in masked

    def test_user_and_host_are_preserved(self) -> None:
        masked = _settings(NEON_POOLED).safe_database_url()
        assert "neondb_owner" in masked
        assert "neon.tech" in masked


class TestRequiredSettings:
    def test_missing_database_url_fails_loudly(self, monkeypatch) -> None:
        # A silent fallback to some throwaway database would be worse than a crash.
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_invalid_log_format_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(database_url=NEON_DIRECT, log_format="xml", _env_file=None)  # type: ignore[call-arg]
