"""T3: preview buttons and the final-render promise are distinct."""

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


def test_the_buttons_name_the_sample_not_the_final():
    html = PAGE.read_text(encoding="utf-8")
    assert ">Generate voice sample<" in html
    assert ">Generate music preview<" in html


def test_the_voice_note_says_the_render_uses_the_settings():
    assert _node("t.soundUseNote({kind:'voice',source:'generate'})") == (
        "The render uses the voice and settings above; this sample is only a preview."
    )


def test_an_uploaded_recording_replaces_the_voice_list():
    assert _node("t.soundUseNote({kind:'voice',source:'upload'})") == (
        "The render uses your recording; the voice list and sample are not used."
    )


def test_the_music_note_matches_the_render_path():
    assert _node("t.soundUseNote({kind:'music',source:'generate'})") == (
        "The render generates its own music bed from this prompt."
    )
    assert _node("t.soundUseNote({kind:'music',source:'own'})") == (
        "The render uses the BGM file you choose; this preview is only a listen."
    )


def test_the_buttons_return_to_their_full_labels_after_generating():
    source = APP.read_text(encoding="utf-8")
    assert 'dom.audioGenerateVoice.textContent = "Generate voice sample"' in source
    assert 'dom.audioGenerateMusic.textContent = "Generate music preview"' in source
