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


def test_project_create_list_and_delete(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not a real video")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Client interview", "source_path": str(source)},
        )
        assert created.status_code == 200
        project = created.json()["project"]
        assert project["name"] == "Client interview"
        assert project["source_bytes"] == len(b"not a real video")

        listed = client.get("/api/projects", headers=headers)
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()["projects"]] == [project["id"]]

        deleted = client.delete(f"/api/projects/{project['id']}", headers=headers)
        assert deleted.status_code == 200
        assert not source.exists()
        assert client.get("/api/projects", headers=headers).json()["projects"] == []


def test_project_rejects_source_outside_data_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"outside")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        response = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Outside", "source_path": str(outside)},
        )
        assert response.status_code == 400
    outside.unlink(missing_ok=True)
