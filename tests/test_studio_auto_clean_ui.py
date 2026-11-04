"""Studio auto-clean UI: one POST, a guarded merge, then a status summary.

The route call, merge guard and error copy run under Node with a stubbed
``fetch``. The panel wiring is a source check, matching the shipped no-build UI.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"

FETCH_STUB = """
    const calls = [];
    globalThis.document = { cookie: "" };
    globalThis.fetch = async (url, options = {}) => {
      calls.push({
        url,
        method: options.method || "GET",
        body: options.body || null,
      });
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({
          layers: [], added: 0, skipped: [], warnings: [],
        }),
      };
    };
"""


def source(module: str) -> str:
    return (STUDIO / module).read_text(encoding="utf-8")


@needs_node
def test_auto_clean_posts_an_empty_body_to_the_edit_route():
    out = run_module("edit/layers/clean.js", FETCH_STUB + """
        const result = await m.autoCleanRequest("job 1", "edit/2");
        return { calls, result };
    """)

    assert out["result"] == {"layers": [], "added": 0, "skipped": [], "warnings": []}
    assert len(out["calls"]) == 1
    call = out["calls"][0]
    assert call["url"] == "/api/jobs/job%201/edits/edit%2F2/auto-clean"
    assert call["method"] == "POST"
    assert json.loads(call["body"]) == {}
    # Handles stay off unless the server is asked explicitly.
    assert "include_handles" not in call["body"]


@needs_node
def test_auto_clean_merge_keeps_layers_and_guards_by_tracklet_id():
    out = run_module("edit/layers/clean.js", """
        const existing = [
          { id: "cl_trk_a", tracklet_id: "trk_a", kind: "delogo" },
          { id: "cl_manual_1", kind: "delogo" },
        ];
        const generated = [
          { id: "cl_trk_a_2", tracklet_id: "trk_a", kind: "delogo" },
          { id: "cl_manual_1", tracklet_id: "trk_b", kind: "delogo" },
          { id: "cl_trk_c", tracklet_id: "trk_c", kind: "delogo" },
        ];
        const merged = m.mergeAutoCleanLayers(existing, generated);
        return {
          ids: merged.layers.map((layer) => layer.id),
          added: merged.added.map((layer) => layer.id),
          skipped: merged.skipped,
          existing: existing.map((layer) => layer.id),
        };
    """)

    assert out["ids"] == ["cl_trk_a", "cl_manual_1", "cl_trk_c"]
    assert out["added"] == ["cl_trk_c"]
    assert out["existing"] == ["cl_trk_a", "cl_manual_1"]
    assert len(out["skipped"]) == 2
    assert out["skipped"][0]["tracklet_id"] == "trk_a"
    assert "tracklet" in out["skipped"][0]["reason"].lower()
    assert "identical" in out["skipped"][1]["reason"].lower()


@needs_node
def test_auto_clean_merge_stops_at_the_clean_layer_cap():
    out = run_module("edit/layers/clean.js", """
        const full = Array.from({ length: 32 }, (_, index) => ({
          id: `cl_${index}`, tracklet_id: `trk_${index}`,
        }));
        const merged = m.mergeAutoCleanLayers(full, [
          { id: "cl_new", tracklet_id: "trk_new" },
        ]);
        return {
          count: merged.layers.length,
          added: merged.added.length,
          skipped: merged.skipped,
        };
    """)

    assert out["count"] == 32
    assert out["added"] == 0
    assert len(out["skipped"]) == 1
    assert "did not fit" in out["skipped"][0]["reason"]


@needs_node
def test_auto_clean_summary_reports_counts_first_reason_and_warnings():
    out = run_module("edit/layers/clean.js", """
        return [
          m.autoCleanSummary({
            added: 2,
            skipped: [
              { reason: "This tracklet already has a Clean layer in the Edit." },
              { reason: "A platform watermark is never removed." },
            ],
            warnings: ["Only the first 32 Clean layers were built."],
          }),
          m.autoCleanSummary({ added: 0, skipped: [], warnings: [] }),
        ];
    """)

    summary = out[0]
    assert summary["added"] == 2
    assert summary["skipped"] == 2
    assert "Added 2 Clean layers." in summary["text"]
    assert "Skipped 2 regions" in summary["text"]
    assert "This tracklet already has a Clean layer in the Edit." in summary["text"]
    assert summary["warnings"] == ["Only the first 32 Clean layers were built."]
    assert "Only the first 32 Clean layers were built." in summary["text"]

    empty = out[1]
    assert empty["added"] == 0
    assert empty["text"].startswith("No new text was found.")
    assert "unchanged" in empty["text"]


@needs_node
def test_auto_clean_404_asks_for_a_scan_and_keeps_other_errors_readable():
    out = run_module("edit/layers/clean.js", """
        return [
          m.autoCleanFailure({ status: 404, message: "Run Scan footage first." }),
          m.autoCleanFailure({ status: 500, message: "Boom" }),
        ];
    """)

    assert out[0] == {
        "text": "Run Scan footage first.",
        "tone": "bad",
        "scan": True,
    }
    assert out[1] == {"text": "Boom", "tone": "bad", "scan": False}


def test_clean_panel_has_one_quiet_remove_all_action():
    clean = source("edit/layers/clean.js")

    assert "Remove all found text" in clean
    assert "st-btn st-btn-ghost st-btn-small st-auto-clean-run" in clean
    assert "disabled: running || !editId" in clean
    # The header action stays secondary.
    index = clean.index("st-auto-clean-run")
    assert "st-btn-primary" not in clean[index - 160:index + 160]


def test_clean_panel_merges_through_set_clean_and_selects_the_first_new_layer():
    clean = source("edit/layers/clean.js")

    assert "mergeAutoCleanLayers(ctx.getEdit()?.clean || [], result?.layers)" in clean
    assert "if (merged.added.length) ctx.setClean(merged.layers)" in clean
    assert 'if (first) ctx.select("clean", first)' in clean
    # The client-side guard mirrors the server's tracklet identity.
    assert "tracklets.has(trackletId)" in clean
    assert "This tracklet already has a Clean layer in the Edit." in clean


def test_clean_panel_shows_scan_guidance_with_an_open_check_action():
    clean = source("edit/layers/clean.js")

    assert 'const SCAN_REQUIRED = "Run Scan footage first."' in clean
    assert "autoCleanFailure(error)" in clean
    assert "st-auto-clean-status" in clean
    assert "Check this scene" in clean
    assert "Scan video" in clean
    assert "startTextScan({ scene = false }" in clean
    assert "start: Number(range.start)" in clean
    assert "reportMatchesScene" in clean


def test_clean_panel_keeps_the_rights_gate_and_manual_add_box():
    clean = source("edit/layers/clean.js")

    assert "I own this footage or have the rights to it." in clean
    assert "Record rights in Check" in clean
    assert "Adding is locked by the server rights policy." in clean
    assert 'text: "Add box"' in clean
    assert "manualLayer" in clean


def test_clean_panel_can_start_and_cancel_a_text_scan_in_edit():
    clean = source("edit/layers/clean.js")

    assert "Find text on screen" in clean
    assert "startTextScan" in clean
    assert "cancelTextScan" in clean
    assert 'method: "POST"' in clean
    assert "/api/jobs/${encodeURIComponent(jobId)}/check" in clean
    assert "/check/cancel" in clean
    assert '"queued"' in clean and '"running"' in clean
    assert "st-clean-scan" in clean
    # A cancelled or missing pass is now a task, not a dead end.
    assert 'cancelled: "The last text scan was cancelled' in clean
    assert "Nothing invents missing pixels" not in clean


@needs_node
def test_auto_clean_sends_the_ticked_ids_and_chosen_method():
    out = run_module("edit/layers/clean.js", FETCH_STUB + """
        await m.autoCleanRequest("job 1", "edit/2", {
          include_handles: false,
          tracklet_ids: ["trk_a", "trk_b"],
          method: "ai",
          fill_method: "lama",
        });
        return calls;
    """)

    assert len(out) == 1
    call = out[0]
    assert call["method"] == "POST"
    assert json.loads(call["body"]) == {
        "include_handles": False,
        "tracklet_ids": ["trk_a", "trk_b"],
        "method": "ai",
        "fill_method": "lama",
    }
