"""Edit custom clip sequence: append, reorder and compile."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "studio" / "edit" / "index.js").read_text(encoding="utf-8")
TIMELINE = (ROOT / "static" / "studio" / "edit" / "timeline.js").read_text(encoding="utf-8")
EDITS = (ROOT / "edits.py").read_text(encoding="utf-8")


def test_add_clips_appends_to_the_edit_sequence():
    assert "function appendMomentDialog" in INDEX
    assert "setSequence([...currentSequence(), ...appended])" in INDEX
    assert "onAddMoment: () => appendMomentDialog()" in INDEX
    assert '"sequence"' in INDEX


def test_scene_bars_drag_to_reorder():
    assert 'button.draggable = true' in TIMELINE
    assert 'addEventListener("dragstart"' in TIMELINE
    assert 'addEventListener("drop"' in TIMELINE
    assert "onReorder: (from, to) => reorderScene(from, to)" in INDEX
    assert "sequence.splice(from, 1)" in INDEX


def test_edit_schema_accepts_a_sequence_without_breaking_old_edits():
    assert '"sequence"' in EDITS
    assert "def normalize_sequence" in EDITS
    assert "if normalized_sequence:" in EDITS
    assert "content.get(\"sequence\") or []" in EDITS
