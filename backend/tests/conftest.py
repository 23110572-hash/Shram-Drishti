from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import check_connection
from app.main import create_app


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture(scope="session")
def live_db() -> bool:
    """Whether the configured database is actually reachable.

    Tests that need a real connection skip rather than fail when it is not,
    so the suite stays useful offline.
    """
    return check_connection()
