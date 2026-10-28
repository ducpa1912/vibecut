"""Trim a story from the Edit timeline (QA #14).

The timeline saves a sentence range through the existing clip-set `stories`
PATCH. The story Edit follows the new bounds through the existing create
route, and layers outside the bounds are flagged, never deleted.
"""

from __future__ import annotations

from test_clipset import api, write_job  # noqa: F401
from test_studio_js import needs_node, run_module


def test_story_patch_trims_start_and_end_on_sentence_bounds(api):  # noqa: F811
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    story = record["stories"][1]
    sentences = story["sentences"]
    wanted = [item["id"] for item in sentences[1:-1]]
    response = api.patch(
        f"/api/jobs/j1/clip-sets/{record['id']}",
        json={"stories": [{"id": story["id"], "sentences": wanted}]},
    )
    assert response.status_code == 200, response.text
    updated = next(
        item for item in response.json()["clip_set"]["stories"]
        if item["id"] == story["id"]
    )
    assert [item["id"] for item in updated["sentences"]] == wanted
    assert updated["start"] == sentences[1]["start"]
    assert updated["end"] == sentences[-2]["end"]
    assert updated["dur"] == round(sum(item["dur"] for item in sentences[1:-1]), 3)
    assert updated["edited"] is True
    assert isinstance(updated["payoff_closing"], bool)


def test_edit_follows_trimmed_bounds_without_losing_layers(api):  # noqa: F811
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    story = record["stories"][0]
    layer = {
        "type": "text", "kind": "hook", "text": "Stop scrolling",
        "start": 0.0, "end": 2.0,
    }
    created = api.post("/api/jobs/j1/edits", json={
        "set_id": record["id"],
        "story_id": story["id"],
        "aspect": "9:16",
        "graphics": [layer],
    })
    assert created.status_code == 200, created.text
    first = created.json()["edit"]
    assert first["story_ref"]["duration"] == story["dur"]

    wanted = [item["id"] for item in story["sentences"][:-1]]
    trimmed = api.patch(
        f"/api/jobs/j1/clip-sets/{record['id']}",
        json={"stories": [{"id": story["id"], "sentences": wanted}]},
    )
    assert trimmed.status_code == 200, trimmed.text
    shortened = next(
        item for item in trimmed.json()["clip_set"]["stories"]
        if item["id"] == story["id"]
    )
    assert shortened["dur"] < story["dur"]

    # The timeline rebinds through the existing create route, not a new one.
    rebound = api.post("/api/jobs/j1/edits", json={
        "set_id": record["id"],
        "story_id": story["id"],
        "aspect": "9:16",
    })
    assert rebound.status_code == 200, rebound.text
    edit = rebound.json()["edit"]
    assert edit["id"] != first["id"]
    assert edit["version"] == first["version"] + 1
    assert edit["story_ref"]["duration"] == shortened["dur"]
    assert edit["story_ref"]["clip_hash"] != first["story_ref"]["clip_hash"]
    assert edit["graphics"] == first["graphics"]

    current = api.get(
        "/api/jobs/j1/edits/current",
        params={
            "set_id": record["id"],
            "story_id": story["id"],
            "aspect": "9:16",
        },
    )
    assert current.status_code == 200
    assert current.json()["edit"]["id"] == edit["id"]


@needs_node
def test_timeline_module_imports_without_a_dom():
    out = run_module("edit/timeline.js", "return typeof m.mountTimeline;")
    assert out == "function"


@needs_node
def test_story_trim_helpers_snap_to_sentence_bounds():
    out = run_module("stories.js", """
        const story = {
          sentences: [
            {id: 10, text: "One.", start: 0, end: 2},
            {id: 11, text: "Two.", start: 2, end: 4},
            {id: 12, text: "Three.", start: 4, end: 6},
          ],
          clips: [
            {scene: 0, start: 0, end: 2, dur: 2, why: "Sentence 10: One."},
            {scene: 1, start: 2, end: 4, dur: 2, why: "Sentence 11: Two."},
            {scene: 2, start: 4, end: 6, dur: 2, why: "Sentence 12: Three."},
          ],
        };
        const spans = m.sentenceSpans(story);
        return {
          spans,
          startNear: m.nearestSentenceBoundary(spans, "start", 1.9),
          endNear: m.nearestSentenceBoundary(spans, "end", 3.1),
          range: m.trimStoryRange(story, 0, 1),
          lastOnly: m.trimStoryRange(story, 2, 2),
          outside: m.outsideLayerIds([
            {id: "inside", start: 0, end: 2},
            {id: "past", start: 5, end: 7},
            {id: "edge", start: 3, end: 4},
            {id: "crosses", start: 3, end: 5},
          ], 0, 4),
        };
    """)
    assert [row["id"] for row in out["spans"]] == [10, 11, 12]
    assert out["startNear"] == 1
    assert out["endNear"] == 1
    assert out["range"] == {
        "sentences": [10, 11],
        "startIndex": 0,
        "endIndex": 1,
        "start": 0,
        "end": 4,
        "duration": 4,
    }
    assert out["lastOnly"]["sentences"] == [12]
    assert out["outside"] == ["past", "crosses"]


@needs_node
def test_a_sentence_split_across_scenes_is_one_trim_unit():
    out = run_module("stories.js", """
        const story = {
          sentences: [
            {id: 4, text: "Across scenes.", start: 0, end: 5},
            {id: 5, text: "After.", start: 5, end: 7},
          ],
          clips: [
            {scene: 0, start: 0, end: 2.5, dur: 2.5, why: "Sentence 4: Across scenes."},
            {scene: 1, start: 2.5, end: 5, dur: 2.5, why: "Sentence 4: Across scenes."},
            {scene: 2, start: 5, end: 7, dur: 2, why: "Sentence 5: After."},
          ],
        };
        return {
          spans: m.sentenceSpans(story),
          firstOnly: m.trimStoryRange(story, 0, 0),
        };
    """)
    assert len(out["spans"]) == 2
    assert out["spans"][0] == {
        "id": 4, "index": 0, "start": 0, "end": 5, "text": "Across scenes.",
    }
    assert out["firstOnly"]["sentences"] == [4]
    assert out["firstOnly"]["duration"] == 5
