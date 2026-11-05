"""Phase 3: Source Clean layers copied onto a cut, mapped and seeded once.

The mapping is source time -> cut time; the copy is source space, like every
Classic Clean box. These tests work on one temp job and never touch media: the
source record is the existing Clean row saved with the full-source clip.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app
import routes_classic


SOURCE_DURATION = 20.0
SOURCE_CLIP = {
    "scene": 0, "start": 0.0, "end": SOURCE_DURATION,
    "dur": SOURCE_DURATION, "role": "source",
}
CUT_CLIPS = [
    {"scene": 0, "role": "hook", "start": 2.0, "end": 5.0, "dur": 3.0},
    {"scene": 1, "role": "beat", "start": 10.0, "end": 13.0, "dur": 3.0},
]


def _job() -> dict:
    return {
        "id": "classic-carry", "created": 1.0, "updated": 1.0,
        "status": "source_ready", "progress": 1.0,
        "message": "Source ready", "error": None, "mode": "clean",
        "source": {
            "path": "", "name": "source.mp4", "duration": SOURCE_DURATION,
            "width": 1920, "height": 1080, "fps": 30.0, "size": 16,
            "has_audio": True, "fingerprint": "classic-carry",
        },
        "options": {},
        "analysis": None,
        "renders": {},
    }


@pytest.fixture
def classic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    (data / "sources").mkdir(parents=True)
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    job = _job()
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return TestClient(app.app), tmp_path


def _box(**overrides) -> dict:
    box = {
        "id": "cl01",
        "method": "blur",
        "box": {"x": 0.08, "y": 0.72, "w": 0.84, "h": 0.18},
        "label": "Burned-in subtitle",
        "kind": "subtitle",
        "source": "scan",
        "tracklet_id": "t1",
        "text_key": "same words",
        "ranges": [{"start": 1.0, "end": 3.0}],
    }
    box.update(overrides)
    return box


def _save(client, clips, clean, deleted=None, restore=False):
    body = {"clips": clips, "overlays": [], "effects": [], "clean": clean}
    if deleted is not None:
        body["source_clean_deleted"] = deleted
    if restore:
        body["source_clean_restore"] = True
    return client.put(
        "/api/classic/jobs/classic-carry/text", json=body,
    )


def _cut_row() -> dict:
    job = app.load_job("classic-carry")
    return routes_classic._classic_cuts(job)[
        routes_classic.edits.clip_snapshot_hash(
            routes_classic._classic_clips(CUT_CLIPS)
        )
    ]


def _lookup(client, clips):
    return client.post(
        "/api/classic/jobs/classic-carry/text", json={"clips": clips},
    )


def _source_row() -> dict:
    job = app.load_job("classic-carry")
    key = routes_classic._source_clean_key(job)
    return routes_classic._classic_cuts(job)[key]


# ------------------------------------------------------------------ mapping


def test_source_ranges_map_into_cut_time_and_merge_at_the_seam():
    layers = [
        _box(ranges=[
            {"start": 1.0, "end": 3.0},
            {"start": 4.0, "end": 11.0},
        ]),
    ]
    carried = routes_classic._carried_clean_layers(
        layers, routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    # [1,3] only touches the first clip, at cut 0-1. [4,11] touches the end of
    # the first clip (cut 2-3) and the start of the second (cut 3-4).
    assert carried[0]["ranges"] == [
        {"start": 0.0, "end": 1.0},
        {"start": 2.0, "end": 4.0},
    ]
    assert carried[0]["box"] == {"x": 0.08, "y": 0.72, "w": 0.84, "h": 0.18}


def test_a_range_between_two_clips_is_dropped():
    layers = [_box(ranges=[{"start": 6.0, "end": 9.0}])]
    assert routes_classic._carried_clean_layers(
        layers, routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    ) == []


def test_a_whole_source_layer_covers_the_whole_cut():
    layers = [_box(ranges=[])]
    carried = routes_classic._carried_clean_layers(
        layers, routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    assert carried[0]["ranges"] == [{"start": 0.0, "end": 6.0}]


def test_a_range_across_two_clips_is_clamped_to_each_clip():
    # 4.5–10.5 crosses the end of clip 1 (source 5) and the start of clip 2
    # (source 10). The gap never plays; each overlap lands at its cut offset.
    layers = [_box(ranges=[{"start": 4.5, "end": 10.5}])]
    carried = routes_classic._carried_clean_layers(
        layers, routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    assert carried[0]["ranges"] == [{"start": 2.5, "end": 3.5}]


# ------------------------------------------------------------------ merge


def test_duplicate_identity_unions_ranges_and_keeps_the_first_box():
    box = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}
    carried = routes_classic._carried_clean_layers(
        [
            _box(id="a", tracklet_id="t1", box=box,
                 ranges=[{"start": 1.0, "end": 3.0}]),
            _box(id="b", tracklet_id="t1",
                 box={"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.1},
                 ranges=[{"start": 10.5, "end": 12.0}]),
        ],
        routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    merged, added = routes_classic._merge_carried_layers([], carried)
    assert added == 1
    assert [layer["id"] for layer in merged] == ["a"]
    assert merged[0]["box"] == box
    assert merged[0]["ranges"] == [
        {"start": 0.0, "end": 1.0},
        {"start": 3.5, "end": 5.0},
    ]


def test_the_tracklet_id_wins_without_making_a_second_copy():
    carried = routes_classic._carried_clean_layers(
        [
            _box(id="a", tracklet_id="t1", box={"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}),
            _box(id="b", tracklet_id="t1", box={"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.1}),
        ],
        routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    merged, added = routes_classic._merge_carried_layers([], carried)
    assert added == 1
    assert [layer["id"] for layer in merged] == ["a"]


def test_a_drawn_row_is_deduped_by_text_and_box():
    box = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1}
    carried = routes_classic._carried_clean_layers(
        [
            _box(id="a", tracklet_id=None, text_key="hello", box=box),
            _box(id="b", tracklet_id=None, text_key="hello", box=dict(box)),
            _box(id="c", tracklet_id=None, text_key="other", box=dict(box)),
        ],
        routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    merged, added = routes_classic._merge_carried_layers([], carried)
    assert added == 2
    assert [layer["id"] for layer in merged] == ["a", "c"]


def test_an_existing_cut_row_is_not_duplicated_and_ids_stay_unique():
    existing = [_box(id="cl01", tracklet_id="t1")]
    carried = routes_classic._carried_clean_layers(
        [_box(id="cl01", tracklet_id="t1")],  # same row
        routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    merged, added = routes_classic._merge_carried_layers(existing, carried)
    assert added == 0 and len(merged) == 1

    other = routes_classic._carried_clean_layers(
        [_box(id="cl01", tracklet_id="t2")],
        routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    merged, added = routes_classic._merge_carried_layers(existing, other)
    assert added == 1
    assert [layer["id"] for layer in merged] == ["cl01", "cl01-s2"]


def test_a_long_layer_id_is_truncated_before_the_unique_suffix():
    long_id = "y" * 64 + "z" * 16
    carried = routes_classic._carried_clean_layers(
        [_box(id=long_id, tracklet_id=None, text_key="one")],
        routes_classic._classic_clips(CUT_CLIPS), SOURCE_DURATION,
    )
    existing = [_box(id="y" * 64, tracklet_id=None, text_key="other")]
    merged, added = routes_classic._merge_carried_layers(existing, carried)
    assert added == 1
    assert len(merged[0]["id"]) == 64
    assert len(merged[1]["id"]) <= 64
    assert merged[1]["id"].endswith("-s2")


# ------------------------------------------------------------------ routes


def test_lookup_seeds_source_layers_once_and_marks_the_cut(classic):
    client, _ = classic
    assert _save(client, [SOURCE_CLIP], [_box()]).status_code == 200

    first = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert first.status_code == 200, first.text
    assert first.json()["source_clean_added"] == 1
    cut = first.json()["cut"]
    assert cut["source_clean_seeded"] is True
    assert cut["clean"][0]["tracklet_id"] == "t1"
    assert cut["clean"][0]["ranges"] == [{"start": 0.0, "end": 1.0}]

    second = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert second.json()["source_clean_added"] == 0
    assert len(second.json()["cut"]["clean"]) == 1


def test_a_stale_empty_put_gets_the_seeded_rows_back(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])
    seeded = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    assert len(seeded["clean"]) == 1

    # A tab that loaded before the seed saves its empty pre-carry list.
    stale = _save(client, routes_classic._classic_clips(CUT_CLIPS), [])
    assert stale.status_code == 200, stale.text
    assert len(stale.json()["cut"]["clean"]) == 1
    assert stale.json()["cut"]["clean"][0]["tracklet_id"] == "t1"
    assert stale.json()["cut"]["source_clean_seeded"] is True

    again = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert again.json()["source_clean_added"] == 0
    assert len(again.json()["cut"]["clean"]) == 1


def test_a_deleted_carried_row_is_not_restored_by_a_stale_tab(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])
    seeded = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    row = seeded["clean"][0]
    row_id = row["id"]

    deleted = _save(
        client, routes_classic._classic_clips(CUT_CLIPS), [], [row_id],
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["cut"]["clean"] == []

    # A stale tab still holds the old row and saves it back without the delete
    # flag. The durable delete must win and must still be recorded.
    stale = _save(client, routes_classic._classic_clips(CUT_CLIPS), [row])
    assert stale.status_code == 200, stale.text
    assert stale.json()["cut"]["clean"] == []
    assert _cut_row()["source_clean_deleted"], "the delete record was erased"
    looked_up = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    assert looked_up["source_clean_deleted"] == _cut_row()["source_clean_deleted"]

    # A genuinely new row has a new identity and is not filtered.
    fresh = _box(
        id="manual-new", tracklet_id=None, text_key="new words",
        box={"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.1},
    )
    added = _save(client, routes_classic._classic_clips(CUT_CLIPS), [fresh])
    assert added.status_code == 200, added.text
    assert [layer["id"] for layer in added.json()["cut"]["clean"]] == ["manual-new"]


def test_an_explicit_restore_flag_brings_a_deleted_row_back(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])
    seeded = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    row = seeded["clean"][0]

    _save(client, routes_classic._classic_clips(CUT_CLIPS), [], [row["id"]])
    restored = _save(
        client, routes_classic._classic_clips(CUT_CLIPS), [row],
        [row["id"]], restore=True,
    )
    assert restored.status_code == 200, restored.text
    assert [layer["id"] for layer in restored.json()["cut"]["clean"]] == [row["id"]]
    assert _cut_row()["source_clean_deleted"] == []


def test_restore_with_a_new_id_for_the_same_text_clears_the_delete(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])
    seeded = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    row = seeded["clean"][0]

    _save(client, routes_classic._classic_clips(CUT_CLIPS), [], [row["id"]])
    readded = dict(row)
    readded["id"] = "cl01-new"
    restored = _save(
        client, routes_classic._classic_clips(CUT_CLIPS), [readded],
        [row["id"]], restore=True,
    )
    assert restored.status_code == 200, restored.text
    assert [layer["id"] for layer in restored.json()["cut"]["clean"]] == ["cl01-new"]
    assert _cut_row()["source_clean_deleted"] == []


def test_an_edited_carried_row_stays_one_row(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])
    seeded = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    edited = dict(seeded["clean"][0])
    edited.update(hidden=True, box={"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.1})

    saved = _save(
        client, routes_classic._classic_clips(CUT_CLIPS), [edited],
    )
    assert saved.status_code == 200, saved.text
    rows = saved.json()["cut"]["clean"]
    assert len(rows) == 1
    assert rows[0]["id"] == edited["id"]
    assert rows[0]["hidden"] is True
    assert rows[0]["box"] == edited["box"]


def test_editing_a_cut_layer_leaves_the_source_record_untouched(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])
    before = _source_row()["clean"]
    assert before[0]["ranges"] == [{"start": 1.0, "end": 3.0}]

    seeded = _lookup(client, routes_classic._classic_clips(CUT_CLIPS)).json()["cut"]
    edited = dict(seeded["clean"][0])
    edited.update(hidden=True, box={"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.1})
    saved = _save(
        client, routes_classic._classic_clips(CUT_CLIPS), [edited],
    )
    assert saved.status_code == 200, saved.text

    after = _source_row()["clean"]
    assert after == before
    source_lookup = _lookup(client, [SOURCE_CLIP]).json()["cut"]
    assert source_lookup["clean"] == before


def test_a_source_layer_with_no_overlap_seeds_nothing_but_stays_once(classic):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box(ranges=[{"start": 6.0, "end": 9.0}])])
    first = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert first.json()["source_clean_added"] == 0
    assert first.json()["cut"]["clean"] == []
    assert first.json()["cut"]["source_clean_seeded"] is True

    second = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert second.json()["source_clean_added"] == 0
    assert second.json()["cut"]["clean"] == []


def test_a_broken_source_lookup_keeps_the_cut_and_clears_on_success(
    classic, monkeypatch,
):
    client, _ = classic
    manual = _box(
        id="manual-keep", tracklet_id=None, text_key="keep",
        box={"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.1},
        ranges=[{"start": 0.0, "end": 6.0}],
    )
    _save(client, routes_classic._classic_clips(CUT_CLIPS), [manual])
    _save(client, [SOURCE_CLIP], [_box()])
    calls = {"n": 0}

    def broken(_job):
        calls["n"] += 1
        raise ValueError("unreadable")

    monkeypatch.setattr(routes_classic, "_source_clean_key", broken)
    first = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert first.status_code == 200, first.text
    assert first.json()["source_clean_note"] == routes_classic.SOURCE_CARRY_NOTE
    assert [layer["id"] for layer in first.json()["cut"]["clean"]] == ["manual-keep"]
    assert _cut_row()["source_clean_seed_error"] == routes_classic.SOURCE_CARRY_NOTE
    assert calls["n"] == 1

    monkeypatch.setattr(
        routes_classic,
        "_source_clean_key",
        lambda job: routes_classic.edits.clip_snapshot_hash(
            [routes_classic.clean_source.source_clip(job["source"]["duration"])]
        ),
    )
    second = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert second.status_code == 200, second.text
    assert second.json()["source_clean_note"] == ""
    assert {layer["id"] for layer in second.json()["cut"]["clean"]} == {
        "manual-keep", "cl01",
    }
    assert _cut_row()["source_clean_seed_error"] == ""


def test_an_invalid_carry_keeps_the_stored_cut_and_clears_on_success(
    classic, monkeypatch,
):
    client, _ = classic
    manual = _box(
        id="manual-keep", tracklet_id=None, text_key="keep",
        box={"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.1},
        ranges=[{"start": 0.0, "end": 6.0}],
    )
    _save(client, routes_classic._classic_clips(CUT_CLIPS), [manual])
    _save(client, [SOURCE_CLIP], [_box()])
    original = routes_classic.normalize_classic_clean

    def invalid(*_args, **_kwargs):
        raise routes_classic.ClassicTextError("bad carried box")

    monkeypatch.setattr(routes_classic, "normalize_classic_clean", invalid)
    first = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert first.status_code == 200, first.text
    assert first.json()["source_clean_note"] == routes_classic.SOURCE_CARRY_INVALID_NOTE
    assert [layer["id"] for layer in first.json()["cut"]["clean"]] == ["manual-keep"]
    assert _cut_row()["source_clean_seed_error"] == routes_classic.SOURCE_CARRY_INVALID_NOTE

    monkeypatch.setattr(routes_classic, "normalize_classic_clean", original)
    second = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert second.json()["source_clean_note"] == ""
    assert {layer["id"] for layer in second.json()["cut"]["clean"]} == {
        "manual-keep", "cl01",
    }
    assert _cut_row()["source_clean_seed_error"] == ""


def test_a_failed_lookup_never_creates_a_cut_row(classic, monkeypatch):
    client, _ = classic
    _save(client, [SOURCE_CLIP], [_box()])

    def broken(_job):
        raise ValueError("unreadable")

    monkeypatch.setattr(routes_classic, "_source_clean_key", broken)
    response = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert response.status_code == 200, response.text
    assert response.json()["cut"] is None
    job = app.load_job("classic-carry")
    cut_key = routes_classic.edits.clip_snapshot_hash(
        routes_classic._classic_clips(CUT_CLIPS)
    )
    assert cut_key not in routes_classic._classic_cuts(job)


def test_a_mapping_bug_keeps_the_stored_cut_instead_of_a_500(classic, monkeypatch):
    client, _ = classic
    manual = _box(
        id="manual-keep", tracklet_id=None, text_key="keep",
        box={"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.1},
        ranges=[{"start": 0.0, "end": 6.0}],
    )
    _save(client, routes_classic._classic_clips(CUT_CLIPS), [manual])
    _save(client, [SOURCE_CLIP], [_box()])
    original = routes_classic._carried_clean_layers

    def broken(*_args, **_kwargs):
        raise RuntimeError("mapping bug")

    monkeypatch.setattr(routes_classic, "_carried_clean_layers", broken)
    response = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert response.status_code == 200, response.text
    assert response.json()["source_clean_note"] == routes_classic.SOURCE_CARRY_INVALID_NOTE
    assert [layer["id"] for layer in response.json()["cut"]["clean"]] == ["manual-keep"]
    assert _cut_row()["source_clean_seed_error"] == routes_classic.SOURCE_CARRY_INVALID_NOTE

    monkeypatch.setattr(routes_classic, "_carried_clean_layers", original)
    again = _lookup(client, routes_classic._classic_clips(CUT_CLIPS))
    assert again.json()["source_clean_note"] == ""
    assert {layer["id"] for layer in again.json()["cut"]["clean"]} == {
        "manual-keep", "cl01",
    }
