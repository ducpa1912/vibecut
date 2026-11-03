"""Compact Edit shell: moments, four tools, grouped timeline, lock and hide."""

from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio" / "edit"
INDEX = (STUDIO / "index.js").read_text(encoding="utf-8")
BOARD = (STUDIO / "moment-board.js").read_text(encoding="utf-8")
PANEL = (STUDIO / "layers-panel.js").read_text(encoding="utf-8")
TIMELINE = (STUDIO / "timeline.js").read_text(encoding="utf-8")
INSPECTOR = (STUDIO / "inspector.js").read_text(encoding="utf-8")
CSS = (STUDIO / "edit.css").read_text(encoding="utf-8")


def test_moment_board_is_selected_scenes_only_and_numbered():
    assert "Only selected scenes" in BOARD
    assert "st-mb-num" in BOARD
    assert "roleLabel" in BOARD
    assert "Add scene" in BOARD
    assert "getExpanded" in BOARD
    assert 'id="st-edit-moments"' in INDEX


def test_four_tools_are_the_only_creation_navigation():
    assert '["clean", "Clean"]' in PANEL
    assert '["visual", "TextFX"]' in PANEL
    assert '["audio", "Audio"]' in PANEL
    assert '["captions", "Caption"]' in PANEL
    assert 'id: "captions", label: "Caption"' in INSPECTOR
    assert "mountCaptionsPanel(body, panelCtx)" in INSPECTOR


def test_timeline_has_locks_hides_and_three_audio_buses():
    assert "laneLocked" in TIMELINE and "laneHidden" in TIMELINE
    assert "st-tl-lane-btn" in TIMELINE
    assert "is-lane-locked" in TIMELINE and "is-lane-hidden" in TIMELINE


@needs_node
def test_audio_rows_split_into_original_voice_and_bgm():
    rows = run_module(
        "edit/model.js",
        """return m.layerSpans(
          {audio: {mode: "original_bed", music: {name: "Bed"}}},
          {cues: []},
          10,
        ).map((row) => ({id: row.id, label: row.label}));""",
    )
    ids = [row["id"] for row in rows]
    assert "audio_original" in ids
    assert "audio_voice" in ids
    assert "audio_bgm" in ids
    assert "effects" not in ids and "color" not in ids
    labels = {row["id"]: row["label"] for row in rows}
    assert labels["text"] == "TextFX"
    assert labels["captions"] == "Caption"


def test_compact_rows_have_explicit_heights():
    assert ".st-tl-label-text" in CSS
    assert ".st-tl-label-audio_original" in CSS
    assert "clamp(260px, 31vh, 300px)" in CSS
    assert "grid-template-columns: minmax(0, 1fr);" in CSS


def test_transcript_is_the_permanent_right_panel():
    assert 'id="st-edit-transcript"' in INDEX
    assert "mountTranscriptPanel" in INDEX
    assert "renderTranscriptPanel" in INDEX
    assert "grid-template-areas:" in CSS
    assert '"tools preview transcript"' in CSS
    assert '"timeline timeline timeline"' in CSS
