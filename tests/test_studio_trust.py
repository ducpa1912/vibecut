"""Studio trust helpers: capability, paid-action and stale-render clarity."""

from __future__ import annotations

from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
SETUP = (STUDIO / "setup.js").read_text(encoding="utf-8")
AUDIO = (STUDIO / "edit" / "layers" / "audio.js").read_text(encoding="utf-8")
FINISH = (STUDIO / "finish.js").read_text(encoding="utf-8")
TEXT = (STUDIO / "edit" / "layers" / "text.js").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


@needs_node
def test_capability_label_reads_native_and_cloud_state():
    out = run_module("trust.js", """
        const all = {native_stt: true, native_tts: true, native_vision: true};
        const some = {native_stt: true, native_tts: false, native_vision: true};
        const none = {native_stt: false, native_tts: false, native_vision: false};
        return [
          m.capabilityLabel({platform: all, cloud: false}),
          m.capabilityLabel({platform: all, cloud: true}),
          m.capabilityLabel({platform: some, cloud: false}),
          m.capabilityLabel({platform: none, cloud: true}),
          m.capabilityLabel({platform: none, cloud: false}),
        ];
    """)
    assert out == ["On-device AI", "Mixed AI", "Mixed AI", "Cloud AI", "AI off"]


@needs_node
def test_cost_and_stale_helpers_are_explicit():
    out = run_module("trust.js", """
        return {
          cost: m.costNotice({provider: "ElevenLabs", what: "the sample line"}),
          cached: m.costNotice({provider: "ElevenLabs", what: "x", cached: true}),
          stale: m.artifactIsStale({edit_hash: "edh_a"}, "edh_b"),
          fresh: m.artifactIsStale({edit_hash: "edh_a"}, "edh_a"),
          legacy: m.artifactIsStale({}, "edh_a"),
          full: m.graphicsCapNotice({count: 32}),
          near: m.graphicsCapNotice({count: 30}),
          room: m.graphicsCapNotice({count: 10}),
        };
    """)
    assert "ElevenLabs" in out["cost"] and "may cost credits" in out["cost"]
    assert out["cached"] == "Cached · no new provider call."
    assert out["stale"] is True and out["fresh"] is False and out["legacy"] is False
    assert "All 32" in out["full"]
    assert "2 text/effect slots left" in out["near"]
    assert out["room"] == ""


def test_setup_shows_capability_and_paid_action_notes():
    assert "capabilityCard" in SETUP
    assert "capabilityLabel" in SETUP
    assert "Saving this key does not call the provider" in SETUP
    assert "Cloud call · sends the selected script sample · may cost credits." in SETUP
    assert "platform_capabilities" in APP
    assert '"platform": platform_caps' in APP


def test_audio_and_finish_show_cost_and_stale_notices():
    assert "costNotice" in AUDIO
    assert "Cleaning is local. Cloning sends the chosen clip" in AUDIO
    assert "Cloud generation sends the brief" in AUDIO
    assert "artifactIsStale" in FINISH
    assert "STALE_RENDER_TEXT" in FINISH and "artifactStale" in FINISH
    assert "Render calls it and may cost credits" in FINISH


def test_text_panel_warns_before_the_graphics_cap():
    assert "graphicsCapNotice" in TEXT
    assert "st-warning" in TEXT


def test_health_exposes_platform_capabilities():
    import app

    caps = app._platform_capabilities()
    assert isinstance(caps["native_stt"], bool)
    assert isinstance(caps["native_tts"], bool)
    assert isinstance(caps["native_vision"], bool)
    assert isinstance(caps["apple_silicon"], bool)
    assert caps["native_transcript"] == caps["native_stt"]
    from fastapi.testclient import TestClient
    health = TestClient(app.app).get("/api/health").json()
    assert health["core_version"] == "1.0.0"
    assert health["profile_version"] == 1
    assert health["app"] in {"legacy", "studio", "classic"}
