"""Pinned core profiles: Studio and Classic compose their own routers."""

from __future__ import annotations

from pathlib import Path

from core.profiles import CLASSIC, LEGACY, PROFILE_VERSION, STUDIO, active_profile
from core.version import CONTRACT_VERSION, CORE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_core_contract_is_pinned_and_profiles_are_explicit():
    assert CORE_VERSION == "1.0.0"
    assert CONTRACT_VERSION == 1
    assert PROFILE_VERSION == 1
    assert active_profile("studio") is STUDIO
    assert active_profile("classic") is CLASSIC
    assert active_profile("") is LEGACY
    assert active_profile("unknown") is LEGACY


def test_studio_and_classic_pin_only_their_page_routers():
    assert STUDIO.feature("studio_page")
    assert not STUDIO.feature("classic_page")
    assert STUDIO.router("studio_edit")
    assert not STUDIO.router("classic_page")
    assert CLASSIC.feature("classic_page")
    assert not CLASSIC.feature("studio_page")
    assert CLASSIC.router("classic_page")
    assert not CLASSIC.router("studio_edit")
    assert LEGACY.router("classic_page") and LEGACY.router("studio_edit")


def test_entrypoints_use_the_core_configure_contract():
    studio = (ROOT / "studio_app.py").read_text(encoding="utf-8")
    classic = (ROOT / "classic_app.py").read_text(encoding="utf-8")
    assert "configure(STUDIO)" in studio
    assert "configure(CLASSIC)" in classic
    assert "os.environ[" not in studio
    assert "os.environ[" not in classic


def test_app_page_uses_the_profile_not_a_second_edition_branch():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "PROFILE = active_profile()" in source
    assert 'if PROFILE.page == "studio"' in source
    assert 'if PROFILE.page == "classic"' in source
    assert 'if PROFILE.router("studio_edit")' in source
    assert 'if PROFILE.router("classic_page")' in source


def test_classic_entrypoint_boots_its_page_and_excludes_studio_routes(tmp_path):
    import os
    import subprocess
    import sys

    script = """
from fastapi.testclient import TestClient
import classic_app
api = TestClient(classic_app.app)
page = api.get("/")
assert page.status_code == 200, page.text
assert "/static/classic/app.js" in page.text
assert 'id="studio-root"' not in page.text
assert api.get("/voices").status_code == 404
health = api.get("/api/health").json()
assert health["app"] == "classic"
assert api.get("/api/jobs/not-a-job/edits").status_code == 404
print("classic-ok")
"""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "VIBECUT_DATA": str(tmp_path / "data"),
        "VIBECUT_FEATURES": "voice_room",
    }
    env.pop("VIBECUT_TOKEN", None)
    env.pop("VIBECUT_APP", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "classic-ok" in result.stdout
