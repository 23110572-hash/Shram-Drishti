"""Database engine, session factory and the declarative base.

Target is Neon Postgres. Two Neon characteristics shape this module:

1. The ``-pooler`` endpoint is PgBouncer in transaction mode, which does not
   support server-side prepared statements. psycopg3 prepares statements
   automatically after a few executions, so it must be disabled or queries
   start failing once the threshold is crossed.
2. The free tier suspends the compute when idle. The first connection after a
   pause has to wake it, so timeouts are generous and connections are recycled
   rather than held open indefinitely.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

# Explicit naming convention so Alembic autogenerate produces stable, readable
# constraint names instead of database-specific defaults.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _engine_kwargs() -> dict[str, Any]:
    settings = get_settings()

    connect_args: dict[str, Any] = {
        "connect_timeout": settings.database_connect_timeout,
        # Identifies our connections in Neon's monitoring.
        "application_name": "shram_drishti",
    }

    if settings.uses_pgbouncer:
        # None disables psycopg's automatic prepared statements entirely.
        # Required for PgBouncer transaction pooling.
        connect_args["prepare_threshold"] = None

    return {
        "echo": settings.database_echo,
        "future": True,
        "connect_args": connect_args,
        # Neon closes idle connections and may suspend the compute, so verify a
        # connection is alive before handing it out.
        "pool_pre_ping": True,
        # Recycle well inside Neon's idle timeout.
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 5,
    }


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, **_engine_kwargs())
        logger.info(
            "database engine created",
            extra={
                "url": settings.safe_database_url(),
                "pgbouncer": settings.uses_pgbouncer,
            },
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that always closes."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_connection() -> bool:
    """True if the database answers a trivial query. Used by ``/readyz``."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("database connection check failed", extra={"error": str(exc)})
        return False


def server_version() -> str | None:
    """Postgres version string, or None if unreachable. Diagnostics only."""
    try:
        with get_engine().connect() as conn:
            return conn.execute(text("SHOW server_version")).scalar_one()
    except Exception:
        return None


def reset_engine() -> None:
    """Drop cached engine and session factory. For tests only."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
