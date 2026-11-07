from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from duckcore.main import create_app


def test_health_requires_launch_token(tmp_path: Path) -> None:
    app = create_app("test-token", tmp_path)

    with TestClient(app) as client:
        denied = client.get("/api/health")
        assert denied.status_code == 401

        allowed = client.get(
            "/api/health",
            headers={"Authorization": "Bearer test-token"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["app"] == "DuckSuite"
        assert allowed.json()["ok"] is True


def test_shell_serves_duck_page(tmp_path: Path) -> None:
    app = create_app("test-token", tmp_path)

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "DuckSuite" in page.text
        assert "Your video stays on this Mac." in page.text
