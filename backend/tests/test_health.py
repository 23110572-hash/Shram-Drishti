"""Health and readiness endpoint behaviour."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import __version__


class TestLiveness:
    def test_returns_ok(self, client: TestClient) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reports_version_and_environment(self, client: TestClient) -> None:
        body = client.get("/healthz").json()
        assert body["version"] == __version__
        assert body["environment"] in {"local", "staging", "production"}

    def test_does_not_depend_on_the_database(self, client: TestClient) -> None:
        # Liveness must stay green during a database outage, otherwise an
        # orchestrator restarts a perfectly healthy process.
        with patch("app.db.check_connection", return_value=False):
            assert client.get("/healthz").status_code == 200


class TestReadiness:
    def test_reports_not_ready_and_503_when_database_is_down(
        self, client: TestClient
    ) -> None:
        with patch("app.api.health.check_connection", return_value=False):
            response = client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["database"] is False

    def test_reports_ready_when_database_is_up(self, client: TestClient) -> None:
        with patch("app.api.health.check_connection", return_value=True):
            response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"database": True}}

    @pytest.mark.db
    def test_ready_against_the_real_database(
        self, client: TestClient, live_db: bool
    ) -> None:
        if not live_db:
            pytest.skip("configured database is not reachable")
        assert client.get("/readyz").status_code == 200


class TestRequestCorrelation:
    def test_response_carries_a_request_id(self, client: TestClient) -> None:
        assert client.get("/healthz").headers.get("X-Request-ID")

    def test_inbound_request_id_is_honoured(self, client: TestClient) -> None:
        # A gateway-assigned correlation id must survive into our logs and out
        # again, otherwise traces break at our boundary.
        supplied = "11111111-2222-3333-4444-555555555555"
        response = client.get("/healthz", headers={"X-Request-ID": supplied})
        assert response.headers["X-Request-ID"] == supplied

    def test_ids_differ_between_requests(self, client: TestClient) -> None:
        first = client.get("/healthz").headers["X-Request-ID"]
        second = client.get("/healthz").headers["X-Request-ID"]
        assert first != second
