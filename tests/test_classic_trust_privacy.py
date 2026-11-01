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
        "Local processing by default. Optional AI features may send data "
        "to external providers." in html
    )
    assert "No cloud. No account. No watermark." not in html
    assert "> local only<" not in html
    assert ">Local by default<" in html
    assert 'id="privacy-label"' in html


def test_the_pill_says_local_by_default_without_cloud_use():
    assert _node("t.privacyLabel({})") == "Local by default"


def test_a_saved_cloud_key_turns_the_pill_online():
    assert _node("t.privacyLabel({secrets:{openrouter:true}})") == "Online features on"


def test_a_cloud_voice_or_music_engine_turns_the_pill_online():
    assert _node("t.privacyLabel({voiceEngine:'elevenlabs'})") == "Online features on"
    assert _node("t.privacyLabel({musicSource:'generate'})") == "Online features on"
    assert _node("t.privacyLabel({musicEngine:'lyria-clip'})") == "Online features on"


def test_local_engines_keep_the_pill_local():
    assert _node(
        "t.privacyLabel({secrets:{},voiceEngine:'say',musicEngine:'library',musicSource:'own'})"
    ) == "Local by default"
