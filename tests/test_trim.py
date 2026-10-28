"""Pure trim maths plus the optional Edit schema fields."""

from __future__ import annotations

import copy

import pytest

import compose_render
import edits
import trim


def sentence(index: int, start: float, end: float | None = None) -> dict:
    stop = start + 2.0 if end is None else end
    return {
        "id": index,
        "start": float(start),
        "end": float(stop),
        "dur": round(float(stop) - float(start), 3),
        "text": f"Sentence {index}.",
    }


def clip(start: float, end: float) -> dict:
    return {
        "scene": int(start),
        "start": float(start),
        "end": float(end),
        "dur": round(float(end) - float(start), 3),
        "role": "beat",
    }


def story(story_id: str, start: float, end: float, ids: list[int]) -> dict:
    rows = [sentence(index, start + offset * 2.0) for offset, index in enumerate(ids)]
    return {
        "id": story_id,
        "start": float(start),
        "end": float(end),
        "dur": round(float(end) - float(start), 3),
        "sentences": rows,
        "clips": [clip(start, end)],
    }


# ---------------------------------------------------------------- pool/range


def test_pool_grows_both_directions_between_neighbours():
    source = [sentence(index, index * 2.0) for index in range(20)]
    before = story("before", 0.0, 8.0, [0, 1, 2, 3])
    current = story("current", 12.0, 20.0, [6, 7, 8, 9])
    after = story("after", 30.0, 34.0, [15, 16])
    rows, bounds = trim.build_pool(source, [before, current, after], current)
    ids = [item["id"] for item in rows]
    assert ids[0] == 4
    assert ids[-1] == 14
    assert ids == list(range(4, 15))
    assert bounds["before"]["id"] == "before"
    assert bounds["after"]["id"] == "after"
    assert [item for item in ids if item in {6, 7, 8, 9}]
    # GET exposes only ids, times and text.
    assert set(rows[0]) == {"id", "start", "end", "dur", "text"}


def test_pool_always_keeps_current_story_sentences():
    source = [sentence(index, index * 2.0) for index in range(10)]
    current = story("current", 12.0, 20.0, [6, 7, 8, 9])
    rows, _ = trim.build_pool(source, [current], current)
    assert [item["id"] for item in rows] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_validate_range_shrinks_and_grows():
    rows = [sentence(index, index * 2.0) for index in range(10)]
    shrink = trim.validate_range(rows, 2, 8, min_s=1.0)
    assert shrink["start_sentence"] == 2
    assert shrink["end_sentence"] == 8
    assert shrink["duration"] == 14.0
    grow = trim.validate_range(rows, 0, 9, min_s=1.0)
    assert grow["duration"] == 20.0
    assert [item["id"] for item in grow["sentences"]] == list(range(10))


def test_validate_range_codes():
    rows = [sentence(index, index * 2.0) for index in range(10)]
    with pytest.raises(trim.TrimRangeError) as short:
        trim.validate_range(rows, 0, 1, min_s=15.0)
    assert short.value.code == "too_short"
    with pytest.raises(trim.TrimRangeError) as long:
        trim.validate_range(rows, 0, 9, min_s=1.0, max_s=5.0)
    assert long.value.code == "too_long"
    with pytest.raises(trim.TrimRangeError) as invalid:
        trim.validate_range(rows, 8, 2, min_s=1.0)
    assert invalid.value.code == "range_invalid"
    with pytest.raises(trim.TrimRangeError) as missing:
        trim.validate_range(rows, 0, 99, min_s=1.0)
    assert missing.value.code == "range_invalid"
    with pytest.raises(trim.TrimRangeError) as overlap:
        trim.validate_range(
            rows, 2, 8, min_s=1.0,
            before={"id": "b", "end": 6.0},
        )
    assert overlap.value.code == "overlaps_neighbour"
    with pytest.raises(trim.TrimRangeError) as overlap_after:
        trim.validate_range(
            rows, 2, 8, min_s=1.0,
            after={"id": "a", "start": 14.0},
        )
    assert overlap_after.value.code == "overlaps_neighbour"


# ---------------------------------------------------------------- time map


def test_time_mapping_goes_through_the_clips_not_an_offset():
    old = [clip(0.0, 4.0), clip(10.0, 14.0)]
    new = [clip(2.0, 6.0), clip(10.0, 14.0)]
    # Old output 2 s is source 2 s, which is new output 0 s.
    assert trim.map_time(2.0, old, new) == pytest.approx(0.0)
    assert trim.map_time(4.0, old, new) == pytest.approx(2.0)
    # Old output 5 s is source 11 s; the second clip keeps its offset.
    assert trim.map_time(5.0, old, new) == pytest.approx(5.0)
    assert trim.map_time(8.0, old, new) == pytest.approx(8.0)
    # A start trim later moves every layer left by the source delta.
    later = [clip(10.0, 14.0)]
    assert trim.map_time(5.0, old, later) == pytest.approx(1.0)
    assert trim.map_time(8.0, old, later) == pytest.approx(4.0)


def test_ripple_moves_clips_hides_outside_and_keeps_pins():
    old = [clip(0.0, 10.0)]
    new = [clip(5.0, 10.0)]
    layers = [
        {"id": "inside", "start": 6.0, "end": 8.0},
        {"id": "outside", "start": 0.0, "end": 4.0},
        {"id": "clipped", "start": 3.0, "end": 7.0},
        {"id": "hook", "start": 0.0, "end": 2.0, "pin": "story_start"},
        {"id": "cta", "start": 8.0, "end": 10.0, "pin": "story_end"},
    ]
    values, counts = trim.ripple_graphics(layers, old, new)
    by_id = {item["id"]: item for item in values}
    assert by_id["inside"]["start"] == 1.0
    assert by_id["inside"]["end"] == 3.0
    assert by_id["outside"]["hidden"] is True
    assert by_id["outside"]["start"] == 0.0
    assert by_id["outside"]["end"] == 4.0
    assert by_id["clipped"]["start"] == 0.0
    assert by_id["clipped"]["end"] == 2.0
    assert by_id["hook"]["start"] == 0.0
    assert by_id["hook"]["end"] == 2.0
    assert by_id["cta"]["start"] == 3.0
    assert by_id["cta"]["end"] == 5.0
    assert counts == {
        "moved": ["inside"],
        "clipped": ["clipped"],
        "outside": ["outside"],
        "pinned": ["hook", "cta"],
    }
    assert len(values) == len(layers)  # never deleted


def test_ripple_accepts_the_plan_anchor_alias():
    values, counts = trim.ripple_graphics(
        [{"id": "hook", "start": 0.0, "end": 2.0, "anchor": "story_start"}],
        [clip(0.0, 10.0)],
        [clip(5.0, 10.0)],
    )
    assert counts["pinned"] == ["hook"]
    assert values[0]["start"] == 0.0


def test_ripple_keeps_an_already_hidden_layer():
    values, counts = trim.ripple_graphics(
        [{"id": "old", "start": 1.0, "end": 2.0, "hidden": True}],
        [clip(0.0, 10.0)],
        [clip(5.0, 10.0)],
    )
    assert values[0]["hidden"] is True
    assert values[0]["start"] == 1.0
    assert counts["outside"] == ["old"]


# ---------------------------------------------------------------- revisions


def test_story_revision_and_range_signature():
    value = {"id": "st", "start": 0.0, "end": 10.0, "dur": 10.0, "sentences": [{"id": 1}]}
    assert trim.story_revision(value) == 0
    assert trim.story_revision({**value, "revision": 4}) == 4
    assert trim.range_signature(value) == (0.0, 10.0, 10.0, (1,))
    bumped = trim.bump_revision({**value, "end": 8.0}, value)
    assert bumped["revision"] == 1
    unchanged = trim.bump_revision(value, value)
    assert unchanged["revision"] == 0


# ---------------------------------------------------------------- Edit schema


def text_layer(**extra) -> dict:
    value = {
        "type": "text",
        "kind": "hook",
        "text": "Stop scrolling",
        "start": 0.0,
        "end": 2.0,
    }
    value.update(extra)
    return value


def test_missing_pin_and_hidden_keep_the_old_layer_shape():
    layer = text_layer()
    normalized = edits.normalize_graphics([layer])
    assert normalized == edits.normalize_graphics(normalized)
    assert "pin" not in normalized[0]
    assert "hidden" not in normalized[0]
    first = edits.build_edit(
        story_ref={
            "set_id": "cs_1", "story_id": "st_1", "clip_hash": "a" * 16,
            "title": "T", "duration": 10.0, "clip_count": 1,
        },
        aspect="9:16",
        graphics=[layer],
    )
    second = edits.build_edit(
        story_ref=first["story_ref"],
        aspect="9:16",
        graphics=normalized,
    )
    assert first["hash"] == second["hash"]
    assert first["id"] == second["id"]
    assert "pin" not in first["graphics"][0]
    assert "hidden" not in first["graphics"][0]


def test_pin_and_hidden_are_optional_and_normalized():
    normalized = edits.normalize_graphics([
        text_layer(anchor="story_start"),
        text_layer(text="End card", kind="cta", start=8.0, end=10.0, pin="story_end", hidden=True),
    ])
    assert normalized[0]["pin"] == "story_start"
    assert normalized[0]["anchor"] == "top-center"
    assert normalized[1]["pin"] == "story_end"
    assert normalized[1]["hidden"] is True
    assert normalized[1]["anchor"] == "center"


def test_positional_anchor_keeps_its_meaning():
    normalized = edits.normalize_graphics([
        text_layer(anchor="bottom-left"),
    ])
    assert normalized[0]["anchor"] == "bottom-left"
    assert "pin" not in normalized[0]


def test_invalid_pin_is_rejected():
    with pytest.raises(edits.EditError):
        edits.normalize_graphics([text_layer(pin="scene")])


def test_hidden_layer_is_skipped_by_the_render_compiler():
    edit = edits.build_edit(
        story_ref={
            "set_id": "cs_1", "story_id": "st_1", "clip_hash": "a" * 16,
            "title": "T", "duration": 10.0, "clip_count": 1,
        },
        aspect="9:16",
        graphics=[
            text_layer(),
            text_layer(text="Hidden", start=4.0, end=6.0, hidden=True),
        ],
    )
    compiled = compose_render.compile_edit(
        edit,
        clips=[{
            "scene": 0, "start": 0.0, "end": 10.0, "dur": 10.0, "role": "beat",
        }],
        source={"width": 1920, "height": 1080, "duration": 10.0},
        include_captions=False,
    )
    assert [item["id"] for item in compiled["overlays"]] == ["tx01"]


def test_receipt_holds_the_full_before_state():
    old = story("st", 10.0, 20.0, [5, 6, 7, 8, 9])
    new = copy.deepcopy(old)
    new["start"] = 12.0
    new["revision"] = 3
    receipt = trim.make_receipt(
        receipt_id="tr_" + "a" * 24,
        at=1.0,
        kind="trim",
        job_id="j1",
        set_id="cs_1",
        story_id="st",
        old_story=old,
        new_story=new,
        old_revision=2,
        new_revision=3,
        layers={"moved": ["tx01"]},
        captions={"kept": 2},
        before_edits={"9:16": {"id": "ed_" + "b" * 32}},
        after_edits={"9:16": "ed_" + "c" * 32},
        before_caption="cap_old",
        after_caption="cap_new",
        invalidated_artifacts=["art_x", "art_x"],
    )
    assert receipt["old"]["start"] == 10.0
    assert receipt["new"]["start"] == 12.0
    assert receipt["before"]["story"]["sentences"][0]["id"] == 5
    assert receipt["before"]["edits"]["9:16"]["id"].startswith("ed_")
    assert receipt["invalidated_artifacts"] == ["art_x"]
    assert trim.undo_token(receipt["id"]) == receipt["id"]
