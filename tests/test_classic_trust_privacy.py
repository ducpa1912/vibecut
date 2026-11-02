"""T1: Classic privacy copy must match what the app can actually do."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "static" / "classic" / "index.html"
TRUST = ROOT / "static" / "classic" / "trust.js"


def _node(expression: str) -> str:
    script = (
        "const t = require(process.argv[1]);"
        f"process.stdout.write(String({expression}));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(TRUST)],
        check=True, capture_output=True, text=True,
    )
    return result.stdout


def test_the_local_promise_is_qualified_on_the_page():
    html = PAGE.read_text(encoding="utf-8")
    assert (
        "On-device AI on supported Macs; cloud AI where native engines are "
        "not available." in html
    )
    assert "No cloud. No account. No watermark." not in html
    assert "> local only<" not in html
    assert ">Local by default<" not in html
    assert 'id="privacy-label"' in html
    assert 'id="setup-platform-badge"' in html
    assert 'id="setup-platform-rows"' in html
    app = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "renderPlatformCapabilities" in app
    assert "STT / transcript" in app


def test_the_pill_waits_for_platform_data_before_claiming_on_device():
    assert _node("t.privacyLabel({})") == "AI"


def test_the_pill_reports_on_device_ai_when_all_native_engines_exist():
    assert _node(
        "t.privacyLabel({platform:{native_stt:true,native_tts:true,native_vision:true}})"
    ) == "On-device AI"


def test_a_saved_cloud_key_turns_the_pill_cloud_or_mixed():
    assert _node(
        "t.privacyLabel({secrets:{openrouter:true},platform:{native_stt:false,native_tts:false,native_vision:false}})"
    ) == "Cloud AI"
    assert _node(
        "t.privacyLabel({secrets:{openrouter:true},platform:{native_stt:true,native_tts:true,native_vision:true}})"
    ) == "Mixed AI"


def test_a_cloud_voice_or_music_engine_turns_the_pill_cloud_or_mixed():
    platform = "{native_stt:false,native_tts:false,native_vision:false}"
    assert _node(f"t.privacyLabel({{voiceEngine:'elevenlabs',platform:{platform}}})") == "Cloud AI"
    assert _node(f"t.privacyLabel({{musicSource:'generate',platform:{platform}}})") == "Cloud AI"
    assert _node(f"t.privacyLabel({{musicEngine:'lyria-clip',platform:{platform}}})") == "Cloud AI"


def test_a_machine_with_only_some_native_engines_is_mixed():
    assert _node(
        "t.privacyLabel({platform:{native_stt:true,native_tts:false,native_vision:true}})"
    ) == "Mixed AI"
    assert _node(
        "t.privacyLabel({platform:{native_stt:false,native_tts:false,native_vision:false}})"
    ) == "AI off"


def test_local_engines_keep_the_pill_on_device():
    assert _node(
        "t.privacyLabel({secrets:{},voiceEngine:'say',musicEngine:'library',musicSource:'own',platform:{native_stt:true,native_tts:true,native_vision:true}})"
    ) == "On-device AI"


def test_health_reports_platform_capabilities():
    import app

    platform = app.health()["platform"]
    assert platform["system"]
    assert platform["machine"]
    assert isinstance(platform["native_stt"], bool)
    assert isinstance(platform["native_tts"], bool)
    assert isinstance(platform["native_vision"], bool)
    assert isinstance(platform["native_ai"], bool)
