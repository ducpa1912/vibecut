"""Studio auto-subtitles UI: one batch payload, then one Edit patch per track.

The API payload is exercised under Node with a stubbed ``fetch``. The panel
and editor contracts are source checks, matching the shipped no-build UI.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_studio_js import NO_PAGE, needs_node, run_module

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
        text: async () => JSON.stringify({ tracks: [], failed: [] }),
      };
    };
"""


def source(module: str) -> str:
    return (STUDIO / module).read_text(encoding="utf-8")


@needs_node
def test_auto_subtitles_posts_one_batch_payload():
    out = run_module("edit/api.js", FETCH_STUB + """
        const result = await m.autoSubtitles("job 1", {
          setId: "cs 1",
          aspect: "4:5",
          styleId: "bold",
          storyIds: ["st_a", "st_b"],
        });
        return { calls, result };
    """, prelude=NO_PAGE)

    assert out["result"] == {"tracks": [], "failed": []}
    assert len(out["calls"]) == 1
    call = out["calls"][0]
    assert call["url"] == "/api/jobs/job%201/auto-subtitles"
    assert call["method"] == "POST"
    assert json.loads(call["body"]) == {
        "set_id": "cs 1",
        "aspect": "4:5",
        "style_id": "bold",
        "story_ids": ["st_a", "st_b"],
    }


@needs_node
def test_auto_subtitles_defaults_to_clean_vertical_and_every_story():
    out = run_module("edit/api.js", FETCH_STUB + """
        await m.autoSubtitles("j1", { setId: "cs1" });
        return JSON.parse(calls[0].body);
    """, prelude=NO_PAGE)

    assert out == {
        "set_id": "cs1",
        "aspect": "9:16",
        "style_id": "clean",
        "story_ids": [],
    }


def test_captions_panel_has_one_quiet_scoped_auto_subtitles_action():
    captions = source("edit/layers/captions.js")

    assert "Auto subtitles" in captions
    assert "st-btn st-btn-quiet st-btn-small st-auto-subs-run" in captions
    assert "This moment" in captions
    assert "Every moment" in captions
    assert "ctx.setAutoSubtitlesScope" in captions
    assert "await ctx.autoSubtitles(scope.value)" in captions
    # Disabled while running and when the editor has no story.
    assert "disabled: running || !available" in captions
    assert "getAutoSubtitles" in captions
    assert "canAutoSubtitles" in captions
    # No second primary action next to the quiet button.
    assert "st-btn-primary" not in captions[
        captions.index("st-auto-subs-run") - 120:captions.index("st-auto-subs-run") + 120
    ]


def test_edit_attaches_every_returned_track_to_its_story():
    index = source("edit/index.js")

    # One batch call, then read-or-create and patch per returned track.
    assert "autoSubtitles(jobId, {" in index
    assert "getCurrentEdit(jobId, setId, storyId, aspect)" in index
    assert "createEdit(jobId, {" in index
    assert "defaultLayers(null, jobTrack)" in index
    assert "patchEdit(jobId, edit.id, { captions })" in index

    # Only the caption reference (and enable flag) changes.
    assert "track_id: trackId" in index
    assert "style_id: resolvedStyle" in index
    assert "enabled: true" in index
    assert "const resolvedStyle = hadStyle ? previous.style_id : returnedStyle" in index

    # The open Edit, caption panel and track refresh after the run.
    assert "adoptAutoCaptions" in index
    assert "state.captions = track" in index
    assert "renderAutoSubs()" in index
    assert "return { attached: true, keptStyle: hadTrack && hadStyle }" in index


def test_auto_subtitles_scope_guard_and_progress_summary():
    index = source("edit/index.js")
    captions = source("edit/layers/captions.js")

    # Current moment or every moment in the set.
    assert 'if (scope === "set") return ids;' in index
    assert "storyIds," in index
    # Running guard and no-story disable.
    assert "if (state.autoSubs.running) return false;" in index
    assert (
        "canAutoSubtitles: () => Boolean(state.job?.id && state.set?.id && state.story?.id)"
        in index
    )

    # Progress and a summary with track/failure counts and the first error.
    assert "Building captions…" in index
    assert "Attaching caption tracks…" in captions
    assert 'formatCount(attached, "track")' in index
    assert 'formatCount(failures, "failure")' in index
    assert "First error:" in index
