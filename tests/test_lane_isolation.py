"""Lane isolation guards: separate pages, ports, data and settings.

Classic, Studio and Voice Room each load their own files on their own port.
A shared page or a shared port is how one lane breaks another during a merge.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _page(monkeypatch, edition: str, path: str = "/") -> str:
    monkeypatch.setenv("VIBECUT_EDITION", edition)
    monkeypatch.delenv("VIBECUT_FEATURES", raising=False)
    import app

    return TestClient(app.app).get(path).text


def test_classic_and_studio_pages_load_only_their_own_files(monkeypatch):
    classic = _page(monkeypatch, "classic")
    assert "/static/classic/app.js" in classic
    assert "/static/classic/creator.js" in classic
    assert "/static/studio/" not in classic
    assert 'id="studio-root"' not in classic

    studio = _page(monkeypatch, "studio")
    assert "/static/studio/shell.js" in studio
    assert "/static/classic/" not in studio
    assert 'id="studio-root"' in studio


def test_voice_page_loads_only_voice_files(monkeypatch):
    voice = _page(monkeypatch, "voice")
    assert "/static/voice/next.js" in voice
    assert "/static/classic/" not in voice
    assert "/static/studio/" not in voice
    assert "VibeCut Voice" in voice
    app_js = (ROOT / "static" / "voice" / "next.js").read_text(encoding="utf-8")
    assert "Old UI" not in app_js
    assert "Back to VibeCut" not in app_js
    assert "VibeCut Voice" in app_js


def test_classic_page_route_follows_the_edition(monkeypatch):
    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    import app

    api = TestClient(app.app)
    assert "/static/classic/app.js" in api.get("/classic").text

    monkeypatch.setenv("VIBECUT_EDITION", "studio")
    assert api.get("/classic").status_code == 404


def test_lane_assets_live_in_their_own_folder():
    for name in ("app.js", "creator.js", "style.css", "creator.css", "index.html"):
        assert (ROOT / "static" / "classic" / name).is_file(), name
    for old in ("app.js", "creator.js", "style.css", "creator.css"):
        assert not (ROOT / "static" / old).exists(), old


def test_lane_env_ports_and_data_are_distinct():
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "classic"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "VIBECUT_PORT=8796" in result.stdout
    assert "VIBECUT_EDITION=classic" in result.stdout
    assert "/vibecut-lanes/classic" in result.stdout

    out = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "studio"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "VIBECUT_PORT=8795" in out
    assert "/vibecut-lanes/studio" in out
    voice = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "voice"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "VIBECUT_PORT=8797" in voice
    assert f"VIBECUT_DATA={ROOT}/data" in voice
    assert "VIBECUT_EDITION=voice" in voice
    assert "VIBECUT_FEATURES=voice_room" in voice

    assert "8787" not in subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "classic"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_ship_lane_never_moves_main():
    script = (ROOT / "scripts" / "ship-lane.sh").read_text(encoding="utf-8")
    assert "refs/heads/main" not in script
    assert "merge --ff-only" not in script


def test_settings_and_secrets_stay_inside_the_test_folder():
    import settings_store

    assert settings_store.SETTINGS_PATH.parent != settings_store.DATA
    assert settings_store.SECRETS_PATH.parent != settings_store.DATA
    settings_store.save_settings({"rights": {"lock": True}})
    assert settings_store.SETTINGS_PATH.is_file()
    assert settings_store.load_settings()["rights"]["lock"] is True
