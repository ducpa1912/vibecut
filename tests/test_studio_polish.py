"""P3 polish: shared layer colours, icons, keywords, tokens and empty states."""

from __future__ import annotations

import json
from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
INDEX = (STUDIO / "edit" / "index.js").read_text(encoding="utf-8")
PREVIEW = (STUDIO / "edit" / "preview.js").read_text(encoding="utf-8")
TIMELINE = (STUDIO / "edit" / "timeline.js").read_text(encoding="utf-8")
PANEL = (STUDIO / "edit" / "layers-panel.js").read_text(encoding="utf-8")
MODEL = (STUDIO / "edit" / "model.js").read_text(encoding="utf-8")
API = (STUDIO / "edit" / "api.js").read_text(encoding="utf-8")
ICONS = (STUDIO / "edit" / "icons.js").read_text(encoding="utf-8")
CSS = (STUDIO / "edit" / "edit.css").read_text(encoding="utf-8")
TEXT = (STUDIO / "edit" / "layers" / "text.js").read_text(encoding="utf-8")


@needs_node
def test_the_layer_palette_is_shared_by_layers_preview_and_timeline():
    palette = run_module("edit/model.js", "return m.LAYER_COLOURS;")
    assert palette == {
        "clean": "#e8a266",
        "text": "#7b9bb8",
        "captions": "#8ec9a3",
        "effects": "#c5a0d9",
        "color": "#f4c169",
        "audio": "#5fb7b0",
    }
    assert "LAYER_COLOURS" in PANEL and "LAYER_COLOURS" in PREVIEW
    assert "rgba(232, 162, 102, 0.42)" in CSS  # Remove text
    assert "rgba(123, 155, 184, 0.42)" in CSS  # Text
    assert "rgba(142, 201, 163, 0.38)" in CSS  # Captions
    assert "rgba(197, 160, 217, 0.38)" in CSS  # Effects
    assert "rgba(95, 183, 176, 0.38)" in CSS   # Audio


def test_icons_are_one_inline_lucide_set_and_used_across_edit():
    assert "Lucide" in ICONS and "createElementNS" in ICONS
    assert "https://" not in ICONS
    assert "from \"./icons.js\"" in PANEL
    assert "from \"./icons.js\"" in PREVIEW
    assert "from \"./icons.js\"" in INDEX
    for name in ("eraser", "type", "captions", "sparkles", "palette", "audio-lines",
                 "cursor", "square", "undo", "redo", "keyboard"):
        assert f"{name}:" in ICONS or f'"{name}"' in ICONS


def test_spacing_and_type_tokens_are_used_across_the_editor():
    for token in (
        "--edit-space-1: 4px", "--edit-space-2: 8px", "--edit-space-3: 12px",
        "--edit-space-4: 16px", "--edit-space-5: 24px", "--edit-space-6: 32px",
        "--edit-text-small: 12px", "--edit-text-body: 13px", "--edit-title: 15px",
        "--edit-control: 32px",
    ):
        assert token in CSS
    assert "var(--edit-space-3)" in CSS
    assert "font-size: var(--edit-title)" in CSS
    assert "padding: var(--edit-space-3) var(--edit-space-4)" in CSS


def test_keyboard_shortcuts_cover_navigation_tools_undo_and_help():
    assert "onEditorKeydown" in INDEX
    assert "togglePlay" in INDEX and "togglePlay" in PREVIEW
    assert "ArrowLeft" in INDEX and "event.shiftKey" in INDEX
    assert "key === \"j\" || event.key === \"J\"" in INDEX
    assert "key === \"k\" || event.key === \"K\"" in INDEX
    assert "key === \"l\" || event.key === \"L\"" in INDEX
    assert "preview?.setTool(\"select\")" in INDEX
    assert "preview?.setTool(\"box\")" in INDEX
    assert "event.key === \"?\"" in INDEX
    assert "redoLastChange" in INDEX
    assert "metaKey" in INDEX and "ctrlKey" in INDEX
    assert "event.stopPropagation()" in TIMELINE  # timeline arrows do not double-step


def test_the_shortcut_sheet_is_a_real_dialog_with_the_plan_keys():
    assert 'id="st-edit-shortcuts"' in INDEX
    assert "<dialog" in INDEX
    assert "Keyboard shortcuts" in INDEX
    for key in ("Space", "J", "K", "L", "Shift", "V", "B", "Delete", "⌘Z", "⇧⌘Z", "?"):
        assert f"<kbd>{key}</kbd>" in INDEX
    assert "showModal" in INDEX
    assert "st-shortcuts" in CSS


@needs_node
def test_redo_posts_the_version_to_the_restore_route():
    return_value = json.dumps({"edit": {"id": "ed_new"}})
    out = run_module("edit/api.js", f"""
        const calls = [];
        globalThis.document = {{ cookie: "" }};
        globalThis.fetch = async (url, options = {{}}) => {{
          calls.push({{ url, method: options.method || "GET", body: options.body || null }});
          return {{ ok: true, status: 200, text: async () => {json.dumps(return_value)} }};
        }};
        const result = await m.restoreEdit("job 1", "edit/2", "ed_old");
        return {{ calls, result }};
    """)
    assert out["result"] == {"edit": {"id": "ed_new"}}
    call = out["calls"][0]
    assert call["url"] == "/api/jobs/job%201/edits/edit%2F2/restore"
    assert call["method"] == "POST"
    assert json.loads(call["body"]) == {"version": "ed_old"}


def test_layers_have_one_add_menu_and_collapsible_groups():
    assert "st-layers-add" in PANEL
    assert "st-layers-add-item" in PANEL
    assert "ctx.add(group.kind)" in PANEL
    assert "readCollapsed" in PANEL and "saveCollapsed" in PANEL
    assert 'class: `st-layer-group${isCollapsed ? " is-collapsed" : ""}`' in PANEL
    assert "st-layer-empty-copy" in PANEL
    assert "st-layer-group-add" not in PANEL
    assert "st-layer-empty-action" not in PANEL
    assert ".st-layer-group.is-collapsed" in CSS
    assert "st-tl-empty" not in TIMELINE
    assert "handlers.onAdd(row.kind)" not in TIMELINE


def test_text_panel_does_not_repeat_the_add_action():
    assert "Add text" not in TEXT
    assert "New text kind" not in TEXT
    assert "TEXT_KINDS" in TEXT
