"""T2: a click that can reach a paid provider carries a visible notice."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "static" / "classic" / "index.html"
APP = ROOT / "static" / "classic" / "app.js"
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


def test_a_provider_notice_names_the_provider_and_the_data():
    text = _node(
        "t.costNotice({provider:'MiniMax Music',what:'a music prompt'})"
    )
    assert text == "MiniMax Music · sends a music prompt · may cost credits."


def test_a_cache_hit_says_no_new_call():
    assert _node("t.costNotice({cached:true})") == "Cached · no new call"


def test_local_only_translation_never_reports_cloud_use():
    assert _node(
        "t.translationMayUseCloud({mode:'local_only',providers:[{id:'openrouter',available:true}]})"
    ) == "false"


def test_auto_translation_reports_cloud_when_a_key_is_ready():
    assert _node(
        "t.translationMayUseCloud({mode:'auto',providers:[{id:'apple_fm',available:true},{id:'openrouter',available:true}]})"
    ) == "true"
    assert _node(
        "t.translationMayUseCloud({mode:'auto',providers:[{id:'apple_fm',available:true}]})"
    ) == "false"


def test_rewrite_reports_cloud_only_when_a_cloud_model_is_ready():
    assert _node(
        "t.rewriteMayUseCloud({models:[{id:'apple',available:true},{id:'opencode',available:true}]})"
    ) == "true"
    assert _node(
        "t.rewriteMayUseCloud({models:[{id:'apple',available:true}]})"
    ) == "false"


def test_the_three_cards_have_their_own_cost_line():
    html = PAGE.read_text(encoding="utf-8")
    for element in ("audio-copy-cost", "audio-voice-cost", "audio-music-cost"):
        assert f'id="{element}"' in html


def test_the_music_preview_reads_the_cache_header():
    source = APP.read_text(encoding="utf-8")
    assert 'headers.get("X-VibeCut-Preview")' in source
    assert "Cached · no new call" in source


def test_the_render_names_the_providers_it_will_call():
    assert _node(
        "t.renderCostNote({voiceProvider:'MiniMax Speech',musicProvider:'OpenRouter (Lyria 3)'})"
    ) == "Render calls MiniMax Speech and OpenRouter (Lyria 3) · may cost credits."
    assert _node("t.renderCostNote({})") == ""
    script = APP.read_text(encoding="utf-8")
    # Every render note goes through the cost line, not only the cards.
    assert "dom.renderNote.textContent = withLayerNote(" not in script
    assert script.count("dom.renderNote.textContent = withRenderNotes(") == 5


def test_an_opencode_login_without_a_key_turns_the_pill_online():
    assert _node(
        "t.privacyLabel({secrets:{},onlineTranslation:true})"
    ) == "Online features on"
    script = APP.read_text(encoding="utf-8")
    pill = script[script.index("function updatePrivacyPill"):]
    pill = pill[:pill.index("\n  }\n")]
    assert "rewriteMayUseCloudNow()" in pill
    assert "translationMayUseCloudNow()" in pill
