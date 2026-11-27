import copy

import pytest

from duckcore import edits, render


def make_edit(root):
    edit = edits.create_full("prj_pd", {"meta": {"duration": 10}, "scenes": [
        {"id": 1, "start": 2, "end": 6}, {"id": 2, "start": 8, "end": 10},
    ]}, root)
    edit["clips"][0].update(volume=.5, fade_in=2, crop={"x": .1})
    edit["captions"] = {"cues": [{"id": "cq_x", "start": 3, "end": 5, "text": "A"}]}
    edit["clean"] = [{"ranges": [{"start": 8.1, "end": 9.1}], "auto": False}]
    edit["dub"] = {"id": "dub", "duration": 6, "audio": "dub.wav"}
    edit["sfx"] = [{"id": "bell", "kind": "sound", "file": "bell.wav",
                    "start": 3.9, "end": 4.1, "offset": 1, "fade_out": .1}]
    return edit


def test_split_inside_fade_keeps_attachments_and_two_independent_clips(tmp_path):
    edit = make_edit(tmp_path)
    original = copy.deepcopy(edit)
    edits.split_at(edit, tmp_path, 1)
    left, right, _ = edit["clips"]
    assert (left["start"], left["end"], right["start"], right["end"]) == (2, 3, 3, 6)
    assert left["crop"] == right["crop"] and left["crop"] is not right["crop"]
    assert left["volume"] == right["volume"] == .5
    assert left["fade_in"] == right["fade_in"] == 2
    for key in ("captions", "clean", "dub", "sfx"):
        assert edit[key] == original[key]
    for boundary in (0, 1, 4, 6):
        with pytest.raises(edits.EditError):
            edits.split_at(edit, tmp_path, boundary)


def test_reorder_maps_output_occurrences_and_preserves_audio_phase(tmp_path):
    edit = make_edit(tmp_path)
    edits.move_clip(edit, tmp_path, 1, 0)
    assert [c["scene"] for c in edit["clips"]] == [2, 1]
    assert [(c["start"], c["end"]) for c in edit["captions"]["cues"]] == [(0, 1), (5, 6)]
    assert edit["clean"] == [{"ranges": [{"start": 8.1, "end": 9.1}], "auto": False}]
    assert [(r["start"], r["offset"], r["duration"]) for r in edit["audio_tracks"]] == [(0, 4, 2), (2, 0, 4)]
    assert edit["dub"]["offset"] == 4
    one, two = edit["sfx"]
    assert one["id"] != two["id"]
    assert (one["start"], one["end"], one["offset"], one["fade_offset"]) == (0, .1, 1.1, .1)
    chain = render._audio_fragment(one, one["end"] - one["start"], .5)
    assert "atrim=start=1.100:duration=0.100" in chain
    assert "+0.100/TB" in chain and "afade=t=out:st=0.100:d=0.100" in chain
    assert edits.get_edit(tmp_path, "prj_pd", edit["id"]) == edit


def test_remove_ranges_across_clips_and_inserted_media(tmp_path):
    edit = make_edit(tmp_path)
    edit["clips"][1].update(kind="media", offset=2, file="beat.mov")
    edits.cut_spans(edit, tmp_path, [[1, 2], [3.5, 4.5]])
    assert [(r["start"], r["end"]) for r in edit["clips"]] == [(2, 3), (4, 5.5), (8.5, 10)]
    assert edit["clips"][-1]["offset"] == 2.5
    assert edit["end"] == 4
    assert [(c["start"], c["end"]) for c in edit["captions"]["cues"]] == [(2, 2.5), (2.5, 3)]
    assert not edit["sfx"]
    with pytest.raises(edits.EditError):
        edits.cut_spans(edit, tmp_path, [[0, 4]])


def test_stale_move_cannot_replace_new_split(tmp_path):
    edit = make_edit(tmp_path)
    stale = copy.deepcopy(edit)
    edits.split_at(edit, tmp_path, 2)
    with pytest.raises(edits.EditConflict):
        edits.move_clip(stale, tmp_path, 0, 1)
    assert edits.get_edit(tmp_path, "prj_pd", edit["id"]) == edit


def test_fill_cache_follows_source_interval_not_edit_order(tmp_path):
    from duckcore.engine.textfill import span_key

    edit = make_edit(tmp_path)
    def keys():
        return [span_key(meta=edit["source"], start=c["start"], duration=c["dur"],
                         layers=[], method="test", model_stamp="test") for c in edit["clips"]]

    before = keys()
    edits.move_clip(edit, tmp_path, 1, 0)
    assert keys() == list(reversed(before))
    edits.split_at(edit, tmp_path, 1)
    assert keys()[-1] == before[0] and not set(keys()[:2]).intersection(before)
