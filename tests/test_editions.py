"""Edition and feature switches: one codebase, builds differ by configuration."""

import json
import re

import pytest
from fastapi.testclient import TestClient

import editions


@pytest.fixture
def switches(monkeypatch):
    def set_switches(edition=None, features=None):
        for name, value in (("VIBECUT_EDITION", edition), ("VIBECUT_FEATURES", features)):
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
    set_switches()
    return set_switches


def _boot(html: str) -> dict:
    match = re.search(r"window\.VIBECUT_EDITION=(\{.*?\});</script>", html)
    assert match, "the index page must carry the edition before the boot block"
    return json.loads(match.group(1))


def test_default_build_keeps_both_views_and_every_feature(switches):
    assert editions.edition() == "all"
    assert editions.public() == {
        "edition": "all", "views": ["studio", "classic"],
        "default_view": "studio", "features": ["voice_room"],
    }


def test_classic_beta_build_shows_classic_only_and_no_hidden_features(switches):
    switches(edition="classic")
    assert editions.views() == ("classic",)
    assert editions.public()["default_view"] == "classic"
    assert not editions.feature_on("voice_room")
    switches(edition="classic", features="voice_room")
    assert editions.feature_on("voice_room")


def test_unknown_values_fall_back_safely(switches):
    switches(edition="nightly", features="voice_room, teleport")
    assert editions.edition() == "all"
    assert editions.features() == frozenset({"voice_room"})
    switches(edition="studio", features="")
    assert editions.views() == ("studio",)
    assert editions.features() == frozenset()


def test_index_page_carries_the_edition_before_the_boot_block(switches):
    import app

    switches(edition="classic")
    html = TestClient(app.app).get("/").text
    assert _boot(html)["views"] == ["classic"]
    assert html.index("window.VIBECUT_EDITION") < html.index("Choose the workspace before first paint")
    assert "<!-- vibecut:edition -->" not in html


def test_voice_room_is_404_when_the_feature_is_off(switches):
    import app

    api = TestClient(app.app)
    assert api.get("/voices").status_code == 200
    assert api.get("/api/voices/clones").status_code == 200
    switches(edition="classic")
    assert api.get("/voices").status_code == 404
    assert api.get("/api/voices/clones").status_code == 404
    assert api.get("/api/voices/catalog").status_code == 404
    assert api.post("/api/jobs/x/voices/candidates").status_code == 404
    switches(edition="classic", features="voice_room")
    assert api.get("/voices").status_code == 200


def test_settings_report_the_edition_and_heygen_clone_follows_the_feature(switches, monkeypatch):
    import app
    import audio
    import tts

    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    assert tts.voice_engine_status()["heygen"]["clone"] is True
    switches(edition="classic")
    assert TestClient(app.app).get("/api/settings").json()["edition"]["views"] == ["classic"]
    assert tts.voice_engine_status()["heygen"]["clone"] is False


def test_boot_block_hides_links_for_views_and_features_the_build_lacks():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
    for rule in (
        'html:not([data-views~="studio"]) #classic-studio-return',
        'html:not([data-views~="classic"]) #st-use-classic',
        'html:not([data-features~="voice_room"]) #classic-voice-room',
        'html:not([data-features~="voice_room"]) #st-voice-room',
    ):
        assert rule in html
    assert "allowed(requested)" in html and "allowed(stored)" in html
