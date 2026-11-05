"""Compact Edit shell: Elements, Preview, Layers and the contextual timeline."""

from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio" / "edit"
INDEX = (STUDIO / "index.js").read_text(encoding="utf-8")
ELEMENTS = (STUDIO / "elements-panel.js").read_text(encoding="utf-8")
LAYERS = (STUDIO / "layers-panel.js").read_text(encoding="utf-8")
PREVIEW = (STUDIO / "preview.js").read_text(encoding="utf-8")
CLEAN = (STUDIO / "layers" / "clean.js").read_text(encoding="utf-8")
TIMELINE = (STUDIO / "timeline.js").read_text(encoding="utf-8")
CSS = (STUDIO / "edit.css").read_text(encoding="utf-8")


def test_elements_panel_owns_moments_effects_text_and_audio():
    assert "mountElementsPanel" in INDEX
    assert '["moments", "Moments"' in ELEMENTS
    assert '["elements", "Element"' in ELEMENTS
    assert '["text", "Text"' in ELEMENTS
    assert '["audio", "Audio"' in ELEMENTS
    assert "Gallery" not in ELEMENTS
    assert "appendBlank" in ELEMENTS
    assert "openImport" in ELEMENTS and "openScenePicker" in ELEMENTS
    assert ".st-el-tab svg { display: block" in CSS
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


def test_painter_mask_is_on_the_clean_layer():
    clean = (STUDIO / "layers" / "clean.js").read_text(encoding="utf-8")
    preview = (STUDIO / "preview.js").read_text(encoding="utf-8")
    assert "ctx.addPaint?.()" in clean
    assert "mask" in clean and "Clear paint" in clean
    assert "startPaint(layerId" in preview
    assert "onPaint" in preview
    assert "paintPoints" in preview
    assert "appendPaintPoints" in INDEX
    assert "startPaint: (layerId" in INDEX


def test_found_text_marks_share_the_existing_clean_lane():
    timeline = (STUDIO / "timeline.js").read_text(encoding="utf-8")
    assert 'ranges: Array.isArray(tracklet?.ranges)' in CLEAN
    assert 'seekMissFound' in CLEAN
    assert 'ctx.setFoundText([])' not in CLEAN
    assert 'cleanRow.items.push' in timeline
    assert 'found: true' in timeline
    assert 'handlers.onFound(item.trackletId)' in timeline
    assert 'foundText: foundForTimeline()' in INDEX
    assert 'is-found' in (STUDIO / "edit.css").read_text(encoding="utf-8")


@needs_node
def test_scene_bounds_step_between_scene_starts():
    rows = run_module(
        "edit/model.js",
        """return m.sceneBounds(
          {sequence: [
            {start: 10, end: 14, role: "hook"},
            {start: 20, end: 25, role: "beat"},
            {start: 30, end: 33, role: "payoff"},
          ]},
          null,
        );""",
    )
    assert [row["start"] for row in rows] == [0, 4, 9]
    assert [row["end"] for row in rows] == [4, 9, 12]
    assert rows[0]["role"] == "hook"


def test_preview_has_story_selector_scene_steps_zoom_and_span():
    assert "st-preview-story-btn" in PREVIEW
    assert "onSceneStep" in PREVIEW and "onSceneStep(-1)" in PREVIEW
    assert "onSpan" in PREVIEW and "st-preview-span-in" in PREVIEW
    assert "st-preview-zoom-in" in PREVIEW and "applyViewZoom" in PREVIEW
    assert "viewPan" in PREVIEW and "translate(${state.viewPan.x}px" in PREVIEW
    assert "st-preview-stage { border:" in CSS


def test_moments_import_and_scene_picker_modals_exist():
    assert "openImportModal" in INDEX and "st-import-mini" in INDEX
    assert "openScenePicker" in INDEX and "st-scene-picker" in INDEX
    assert '"This Project"' in INDEX and '"Library"' in INDEX
    assert "Cut another video" in INDEX
    assert "st-scene-video" in INDEX and "is-selected" in INDEX
    assert "assets/video" in INDEX
    assert "video-url" in INDEX and "video-path" in INDEX
    assert "const linked = /^https?" in INDEX


def test_audio_is_split_music_hub_and_narrative_voice_only():
    audio = (STUDIO / "layers" / "audio.js").read_text(encoding="utf-8")
    assert "musicOnly" in audio and "musicHub" in audio
    assert '"Library"' in audio and '"Upload"' in audio and '"GenAI"' in audio
    assert "narrativeOnly" in audio
    assert "st-audio-mode-tab" in audio
    assert '["original", "Original"], ["voice_over", "Voice-Over"], ["dub", "Dub"]' in audio
    assert "narrativeOnly: true" in LAYERS


def test_captions_and_look_start_folded_and_look_has_note():
    captions = (STUDIO / "layers" / "captions.js").read_text(encoding="utf-8")
    assert '"Style"' in captions and '`Lines · ${cueDraft.length}`' in captions
    assert "st-cue-time-fold" in captions
    color = (STUDIO / "layers" / "color.js").read_text(encoding="utf-8")
    assert "full grading and filter revamp" in color
    assert "Fine tune" in color
