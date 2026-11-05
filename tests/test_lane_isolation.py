"""Lane isolation guards: separate pages, ports, data and settings.

Classic, Studio and Voice Room each load their own files on their own port.
A shared page or a shared port is how one lane breaks another during a merge.
"""

from __future__ import annotations

import os
import subprocess
import sys
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

    for lane, port in (("studio", "8795"), ("voice", "8797")):
        out = subprocess.run(
            ["bash", str(ROOT / "scripts" / "lane-env.sh"), lane],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert f"VIBECUT_PORT={port}" in out, lane
        assert f"/vibecut-lanes/{lane}" in out, lane

    assert "8787" not in subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "classic"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_classic_keeps_its_packs_and_its_own_launcher():
    out = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "classic"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "VIBECUT_PACKS_DIR=" in out
    assert "/vibecut-lanes/classic/packs" in out
    other = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "studio"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "VIBECUT_PACKS_DIR" not in other

    launcher = ROOT / "scripts" / "serve-classic.sh"
    subprocess.run(["bash", "-n", str(launcher)], check=True)
    text = launcher.read_text(encoding="utf-8")
    assert "lane-env.sh classic" in text
    assert "app.py" in text
    assert "classic_app" not in text
    assert "vibecut-studio" not in text
    # A venv here lacks the shared packages, and AI fill then says it is not ready.
    assert ".venv" not in text
    assert "exec python3 app.py" in text


def _classic_env() -> dict[str, str]:
    out = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "classic"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = [line.removeprefix("export ").split("=", 1) for line in out.splitlines()]
    return {name: value for name, value in rows}


def test_classic_keeps_its_own_files_in_the_gitignored_data_folder():
    env = _classic_env()
    assert env["VIBECUT_LANE_MEDIA"] == str(ROOT / "data" / "media")
    assert env["VIBECUT_LANE_RECORDINGS"] == str(ROOT / "data" / "recordings")
    assert env["VIBECUT_VOICES_DIR"] == str(ROOT / "data" / "voices")
    assert env["VIBECUT_MUSIC_DIR"] == str(ROOT / "data" / "music")
    tracked = subprocess.run(
        ["git", "ls-files", "data"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert tracked == ""
    assert "data/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_other_lanes_get_no_paths_from_classics_checkout():
    out = subprocess.run(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "studio"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert str(ROOT) not in out
    assert "VIBECUT_LANE_MEDIA" not in out


def test_classic_loads_fill_models_from_the_shared_cache_only():
    fill = Path(_classic_env()["VIBECUT_FILL_MODELS"])
    assert fill == Path.home() / ".cache" / "vibecut" / "models" / "fill"
    assert "vibecut-lanes" not in str(fill)


def test_the_app_really_uses_the_voices_and_music_folders(tmp_path, monkeypatch):
    import voice_clone

    monkeypatch.setenv("VIBECUT_VOICES_DIR", str(tmp_path / "voices"))
    assert voice_clone.voices_dir() == tmp_path / "voices"
    assert voice_clone.store_path() == tmp_path / "voices" / "clones.json"
    monkeypatch.delenv("VIBECUT_VOICES_DIR")
    assert voice_clone.voices_dir() == voice_clone.settings_store.DATA / "voices"

    code = "import audio; print(audio.MUSIC_DIRS['library'])"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True,
        env={**os.environ, "VIBECUT_MUSIC_DIR": str(tmp_path / "music")},
    ).stdout
    assert out.strip().splitlines()[-1] == str(tmp_path / "music")


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
