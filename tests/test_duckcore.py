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


def test_engine_status_lists_vision_speech_and_lama(tmp_path: Path) -> None:
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        engine = client.get("/api/engine", headers=headers)
        assert engine.status_code == 200
        payload = engine.json()
        assert payload["vision"]["helper"].endswith("vision_probe")
        assert "ocr" in payload["vision"]["features"]
        assert "apple" in payload["speech"]
        assert payload["fill"]["method"] == "lama"
        assert "ready" in payload["fill"]
        assert payload["stories"]["ready"] is True

        models = client.get("/api/models", headers=headers)
        assert models.status_code == 200
        assert models.json()["models"][0]["id"] == "lama"


def test_check_starts_idle(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not a real video")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Idle", "source_path": str(source)},
        ).json()["project"]
        check = client.get(
            f"/api/projects/{project['id']}/check",
            headers=headers,
        )
        assert check.status_code == 200
        assert check.json()["check"]["state"] == "idle"


def _write_fake_check(tmp_path: Path, project_id: str) -> None:
    project_dir = tmp_path / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "duration": 10.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "fingerprint": "source-hash",
        },
        "scenes": [
            {"id": 1, "start": 0.0, "end": 5.0},
            {"id": 2, "start": 5.0, "end": 10.0},
        ],
        "stories": {
            "stories": [
                {
                    "id": "st_test",
                    "start": 0.0,
                    "end": 10.0,
                    "title": "Test story",
                    "clips": [{"scene": 1, "start": 0.0, "end": 5.0}],
                    "sentences": [{"text": "A useful hook"}],
                }
            ]
        },
        "report": {
            "tracklets": [
                {
                    "id": "trk_test",
                    "kind": "subtitle",
                    "box": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.1},
                    "ranges": [{"start": 0.0, "end": 2.0}],
                    "text_sample": "Hello",
                    "confidence": 0.9,
                }
            ]
        },
    }
    (project_dir / "check.json").write_text(__import__("json").dumps(payload), encoding="utf-8")


def test_full_edit_smart_cut_and_clean_layers(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Edit test", "source_path": str(source)},
        ).json()["project"]
        _write_fake_check(tmp_path, project["id"])

        full = client.post(
            f"/api/projects/{project['id']}/edits/full",
            headers=headers,
        )
        assert full.status_code == 200
        full_edit = full.json()["edit"]
        assert full_edit["kind"] == "full"
        assert len(full_edit["clips"]) == 2

        smart = client.post(
            f"/api/projects/{project['id']}/stories/st_test/smart-cut",
            headers=headers,
        )
        assert smart.status_code == 200
        assert smart.json()["edit"]["kind"] == "story"

        cleaned = client.post(
            f"/api/projects/{project['id']}/edits/{full_edit['id']}/clean/from-check",
            headers=headers,
        )
        assert cleaned.status_code == 200
        assert cleaned.json()["layers"] == 1
        layer_id = cleaned.json()["edit"]["clean"][0]["id"]

        patched = client.patch(
            f"/api/projects/{project['id']}/edits/{full_edit['id']}/clean/{layer_id}",
            headers=headers,
            json={"action": "blur"},
        )
        assert patched.status_code == 200
        assert patched.json()["edit"]["clean"][0]["kind"] == "blur"


def test_settings_online_and_model_verify(tmp_path: Path) -> None:
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        settings = client.get("/api/settings", headers=headers)
        assert settings.status_code == 200
        assert settings.json()["language"] == "auto"
        assert settings.json()["online"]["enabled"] is False

        patched = client.patch(
            "/api/settings",
            headers=headers,
            json={"online_enabled": True, "online_endpoint": "https://render.example.com"},
        )
        assert patched.status_code == 200
        assert patched.json()["online"]["enabled"] is True
        assert patched.json()["online"]["endpoint"] == "https://render.example.com"

        bad = client.patch(
            "/api/settings",
            headers=headers,
            json={"online_endpoint": "ftp://example.com"},
        )
        assert bad.status_code == 400

        verified = client.post("/api/models/lama/verify", headers=headers)
        assert verified.status_code == 200
        assert verified.json()["model"] == "lama"
        assert verified.json()["ok"] is False


def test_captions_generate_edit_and_srt(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Caption test", "source_path": str(source)},
        ).json()["project"]
        _write_fake_check(tmp_path, project["id"])
        transcript_dir = tmp_path / "projects" / project["id"] / "transcript"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        (transcript_dir / "transcript_v2_tr_test.json").write_text(
            __import__("json").dumps({
                "id": "tr_test",
                "created": 1.0,
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "First line."},
                    {"start": 2.0, "end": 4.0, "text": "Second line."},
                ],
            }),
            encoding="utf-8",
        )

        edit = client.post(
            f"/api/projects/{project['id']}/edits/full",
            headers=headers,
        ).json()["edit"]
        generated = client.post(
            f"/api/projects/{project['id']}/edits/{edit['id']}/captions/generate",
            headers=headers,
        )
        assert generated.status_code == 200
        track = generated.json()["captions"]
        assert len(track["cues"]) == 2

        cue_id = track["cues"][0]["id"]
        patched = client.patch(
            f"/api/projects/{project['id']}/edits/{edit['id']}/captions/cues/{cue_id}",
            headers=headers,
            json={"text": "Edited line."},
        )
        assert patched.status_code == 200
        assert patched.json()["captions"]["cues"][0]["text"] == "Edited line."

        styled = client.patch(
            f"/api/projects/{project['id']}/edits/{edit['id']}/captions",
            headers=headers,
            json={"style": "bold", "position": "top"},
        )
        assert styled.status_code == 200
        assert styled.json()["captions"]["style"]["id"] == "bold"
        assert styled.json()["captions"]["style"]["position"] == "top"

        srt = client.get(
            f"/api/projects/{project['id']}/edits/{edit['id']}/captions.srt",
            headers=headers,
        )
        assert srt.status_code == 200
        assert "Edited line." in srt.text


def test_caption_burn_helpers() -> None:
    from PIL import Image

    from duckcore.caption_burn import active_cue, draw_caption

    cues = [
        {"start": 0.0, "end": 2.0, "text": "First"},
        {"start": 2.0, "end": 4.0, "text": "Second"},
    ]
    assert active_cue(cues, 1.0)["text"] == "First"
    assert active_cue(cues, 3.0)["text"] == "Second"
    assert active_cue(cues, 5.0) is None

    frame = Image.new("RGB", (1080, 1080), "black")
    drawn = draw_caption(frame, "A readable caption", {"id": "bold", "position": "top"})
    assert drawn.size == (1080, 1080)
    assert drawn.tobytes() != frame.tobytes()


def test_local_voices_list(tmp_path: Path) -> None:
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(app) as client:
        response = client.get("/api/voices", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json()["voices"], list)


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
