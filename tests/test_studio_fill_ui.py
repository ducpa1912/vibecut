"""P2: found-text list, method picker, and the single-frame AI-fill preview."""

from __future__ import annotations

from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
CLEAN = (STUDIO / "edit" / "layers" / "clean.js").read_text(encoding="utf-8")
INDEX = (STUDIO / "edit" / "index.js").read_text(encoding="utf-8")
PREVIEW = (STUDIO / "edit" / "preview.js").read_text(encoding="utf-8")
CSS = (STUDIO / "edit" / "edit.css").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes_studio.py").read_text(encoding="utf-8")
TEXTFILL = (ROOT / "textfill" / "__init__.py").read_text(encoding="utf-8")


def test_found_list_has_ticks_select_all_and_no_refused_rows():
    assert "Found on screen" in CLEAN
    assert "st-found-row" in CLEAN
    assert "st-found-thumb" not in CLEAN
    assert "st-found-tick" in CLEAN
    assert "FOUND_TICKS" in CLEAN
    assert "FOUND_TICKS.get(jobId)" in CLEAN
    assert '"Select all"' in CLEAN and '"Clear"' in CLEAN
    assert "not removed" not in CLEAN
    assert "not cleaned" not in CLEAN
    assert "Already added to this moment." in CLEAN


def test_remove_all_sends_the_ticks_and_the_one_method_choice():
    assert "ticked.flatMap((row) => row.tracklet.ids)" in CLEAN
    assert "tracklet_ids:" in CLEAN
    assert 'method: drawKind() === "fill" ? "ai" : "blur"' in CLEAN
    assert "fill_method: drawEngine()" in CLEAN
    assert "function methodBar()" in CLEAN
    assert "/api/fill/status" in CLEAN
    assert "st-found-engine" in CLEAN


@needs_node
def test_new_layers_use_the_chosen_engine():
    out = run_module("edit/layers/clean.js", """
        const first = m.setLayerKind({id: "a"}, "fill").method;
        m.rememberEngine("sttn");
        const second = m.setLayerKind({id: "b"}, "fill").method;
        m.rememberEngine("lama");
        return {first, second, third: m.setLayerKind({id: "c"}, "blur").method ?? null};
    """)

    assert out == {"first": "lama", "second": "sttn", "third": None}


def test_engine_preview_is_scoped_and_never_saves_first():
    assert "Preview this frame" not in CLEAN
    assert "st-fill-preview-run" not in CLEAN
    assert "compareLayer" in CLEAN
    assert "st-clean-compare" in CLEAN
    assert "compareCleanLayer" in INDEX
    assert 'layer_ids: [String(layerId)]' in INDEX
    assert "clean: clone(state.edit.clean || [])" in INDEX
    assert "showCompare" in PREVIEW and "hideCompare" in PREVIEW
    assert "st-preview-compare" in PREVIEW
    assert "clipPath" in PREVIEW
    assert "st-preview-compare" in CSS


def test_found_boxes_reach_the_preview_before_they_become_layers():
    assert "setFoundText" in INDEX and "foundText" in INDEX
    assert "preview?.setFoundText(state.foundText)" in INDEX
    assert "foundText: state.foundText" in INDEX
    assert "drawFoundBoxes" in PREVIEW
    assert "setFoundText(found)" in PREVIEW
    assert "added.has(String(row.id" in PREVIEW


def test_server_status_thumbnail_auto_clean_and_fill_preview_routes_exist():
    assert '"/api/fill/status"' in ROUTES
    assert "/check/tracklets/{tracklet_id}/thumb" in ROUTES
    assert "/fill-preview" in ROUTES
    assert "_apply_clean_method" in ROUTES
    assert 'method="ai"' not in ROUTES  # method is a request value, not a hard-coded path
    assert "def fill_frame" in TEXTFILL
    assert "The single-frame fill preview uses the LaMa model." in TEXTFILL


def test_fill_preview_route_shares_the_crop_colour_and_overlays():
    assert "_preview_filter_chain" in ROUTES
    assert "pre_filters" in ROUTES and "post_filters" in ROUTES
    assert "render._burn_frame" in ROUTES
    assert "_data_url" in ROUTES
    assert "cache_dir" in ROUTES
