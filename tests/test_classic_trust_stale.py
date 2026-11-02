"""T5: an old render must not look like the current edit."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


BASE = (
    "{target:30,quality:'final',aspect:'9:16',captions:false,"
    "hook_scene:2,order:'source',clips:[{scene:2,start:1,end:3}],"
    "audio:{mode:'keep'},edit:null}"
)


def test_the_signature_is_stable_across_key_order():
    assert _node(
        "t.renderSignature({b:1,a:2}) === t.renderSignature({a:2,b:1})"
    ) == "true"


def test_a_changed_moment_changes_the_signature():
    assert _node(
        "t.renderSignature(" + BASE + ") !== t.renderSignature("
        "{target:30,quality:'final',aspect:'9:16',captions:false,"
        "hook_scene:2,order:'source',clips:[{scene:2,start:1,end:4}],"
        "audio:{mode:'keep'},edit:null})"
    ) == "true"


def test_changed_sound_or_text_changes_the_signature():
    assert _node(
        "t.renderSignature(" + BASE + ") !== t.renderSignature("
        "{target:30,quality:'final',aspect:'9:16',captions:false,"
        "hook_scene:2,order:'source',clips:[{scene:2,start:1,end:3}],"
        "audio:{mode:'music'},edit:null})"
    ) == "true"
    assert _node(
        "t.renderSignature(" + BASE + ") !== t.renderSignature("
        "{target:30,quality:'final',aspect:'9:16',captions:false,"
        "hook_scene:2,order:'source',clips:[{scene:2,start:1,end:3}],"
        "audio:{mode:'keep'},edit:{overlays:[{text:'new'}]}})"
    ) == "true"


def test_the_exact_founder_visible_line_is_fixed():
    assert _node("t.STALE_RENDER_TEXT") == (
        "Changed since this render — render again to see it."
    )


def test_the_page_wires_the_signature_into_the_shown_render():
    source = APP.read_text(encoding="utf-8")
    assert "rememberRenderSignature(result.render, body)" in source
    assert "updateRenderStale(record)" in source
    assert "classic-render-sig:" in source
    assert "record?.request_sig" in source
    assert "No render baseline on this browser." in source
