"""T4: the 9:16 / 4:5 limit is visible before typing and at render time."""

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


def test_the_texts_card_warns_before_any_layer_exists():
    assert _node("t.textShapeNote({aspect:'16:9'})") == (
        "Text overlays and effects render on 9:16 and 4:5. Switch the shape to use them."
    )
    assert _node("t.textShapeNote({aspect:'9:16'})") == ""


def test_the_warning_sits_above_the_text_controls():
    html = PAGE.read_text(encoding="utf-8")
    note = html.index('id="text-shape-note"')
    controls = html.index('id="text-layer-controls"')
    assert note < controls


def test_the_render_note_names_dropped_layers():
    assert _node(
        "t.layerRenderNote({aspect:'16:10',hasLayers:true})"
    ) == "Text layers are left out at this shape."
    assert _node(
        "t.layerRenderNote({aspect:'16:9',hasLayers:false})"
    ) == ""


def test_layers_are_kept_on_supported_shapes():
    assert _node(
        "t.layerRenderNote({aspect:'4:5',hasLayers:true})"
    ) == ""
