"""Compact Edit shell: Elements, Preview, Layers and the contextual timeline."""

from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio" / "edit"
INDEX = (STUDIO / "index.js").read_text(encoding="utf-8")
ELEMENTS = (STUDIO / "elements-panel.js").read_text(encoding="utf-8")
LAYERS = (STUDIO / "layers-panel.js").read_text(encoding="utf-8")
PREVIEW = (STUDIO / "preview.js").read_text(encoding="utf-8")
TIMELINE = (STUDIO / "timeline.js").read_text(encoding="utf-8")
CSS = (STUDIO / "edit.css").read_text(encoding="utf-8")


def test_elements_panel_owns_moments_effects_text_and_audio():
    assert "mountElementsPanel" in INDEX
    assert '["moments", "Moments"' in ELEMENTS
    assert '["elements", "Elements"' in ELEMENTS
    assert '["text", "Text"' in ELEMENTS
    assert '["audio", "Audio"' in ELEMENTS
    assert "Gallery" in ELEMENTS
    assert "appendScene" in ELEMENTS and "appendBlank" in ELEMENTS
    assert "openImport" in ELEMENTS and "openDissect" in ELEMENTS
    assert 'id="st-edit-moments"' not in INDEX


def test_layers_panel_has_the_six_compact_layers():
    assert "mountLayersPanel" in INDEX
    for label in (
        "Clean", "Filter & LUTs", "Transcript & Translation",
        "Narrative", "Zoom", "Border",
    ):
        assert label in LAYERS
    assert "st-layer-rail" in LAYERS
    assert "mountTranscriptPanel" in LAYERS
    assert "mountAudioPanel" in LAYERS
    assert "setAudioFade" in LAYERS
    assert "setBorder" in LAYERS
    assert 'id="st-edit-transcript"' not in INDEX
    assert 'id="st-edit-inspector"' not in INDEX


def test_preview_has_scene_tag_focus_aspect_and_output_controls():
    assert 'id="st-preview-scene-num"' in PREVIEW
    assert 'id="st-preview-scene-role"' in PREVIEW
    assert 'id="st-preview-focus"' in PREVIEW
    assert 'id="st-preview-aspect-menu"' in PREVIEW
    assert 'id="st-preview-resolution"' in PREVIEW
    assert 'id="st-preview-platform"' in PREVIEW
    assert "requestFullscreen" in PREVIEW
    assert "captureFrame" in PREVIEW
    assert 'id="st-preview-scrub"' in PREVIEW  # hidden compatibility value


def test_saving_a_new_edit_version_keeps_the_proxy_alive():
    assert "sameCut" in PREVIEW
    assert "clip_hash" in PREVIEW
    assert "resetProxy()" in PREVIEW
    assert "previousId !== nextId && !sameCut" in PREVIEW


def test_timeline_has_global_and_contextual_toolbars():
    assert "st-tl-global" in TIMELINE
    assert "st-tl-context" in TIMELINE
    assert 'id="st-timeline-undo-trim"' in TIMELINE
    assert 'id="st-timeline-undo"' in TIMELINE
    assert 'id="st-timeline-redo"' in TIMELINE
    assert 'id="st-timeline-record"' in TIMELINE
    assert 'id="st-timeline-subtitle"' in TIMELINE
    assert 'data-tl-action="duplicate"' in TIMELINE
    assert 'data-tl-action="reverse"' in TIMELINE
    assert 'data-tl-action="freeze"' in TIMELINE
    assert 'data-tl-action="mosaic"' in TIMELINE
    assert 'id="st-timeline-title"' not in TIMELINE


def test_timeline_keeps_locks_hides_and_audio_buses():
    assert "laneLocked" in TIMELINE and "laneHidden" in TIMELINE
    assert "st-tl-lane-btn" in TIMELINE
    assert "st-tl-modes" in TIMELINE
    assert "No voice" in TIMELINE and "No BGM" in TIMELINE


def test_three_panel_grid_and_compact_rows():
    assert "288px minmax(0, 1fr) 344px" in CSS
    assert '"elements preview layers"' in CSS
    assert '"timeline timeline timeline"' in CSS
    assert ".st-tl-label-text" in CSS
    assert ".st-tl-label-audio_original" in CSS
    assert "grid-template-columns: minmax(0, 1fr);" in CSS


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
    labels = {row["id"]: row["label"] for row in rows}
    assert labels["text"] == "TextFX"
    assert labels["captions"] == "Caption · cues"
