"""Regression tests for the user-test defects."""

from __future__ import annotations

from duckcore.captions import _cues_for_clip
from duckcore.clean import _merge_stacked_titles


def test_repeated_whisper_chunk_makes_one_cue() -> None:
    cues = _cues_for_clip(
        [
            {"start": 3.4, "end": 3.625, "text": "And this one is uncomfortable."},
            {"start": 3.625, "end": 6.54, "text": "And this one is uncomfortable."},
        ],
        clip_start=0.0,
        clip_end=10.0,
        out_start=0.0,
    )
    assert len(cues) == 1
    assert cues[0][2] == "And this one is uncomfortable."
    assert cues[0][0] == 3.4
    assert cues[0][1] == 6.54


def test_overlapping_segments_do_not_overlap_cues() -> None:
    cues = _cues_for_clip(
        [
            {"start": 0.0, "end": 2.0, "text": "First line."},
            {"start": 1.7, "end": 4.0, "text": "Second line."},
        ],
        clip_start=0.0,
        clip_end=5.0,
        out_start=0.0,
    )
    assert [text for _start, _end, text in cues] == ["First line.", "Second line."]
    assert cues[0][1] <= cues[1][0]
    assert all(end - start >= 0.6 for start, end, _text in cues)


def test_five_millisecond_cue_is_removed_or_extended() -> None:
    cues = _cues_for_clip(
        [
            {"start": 9.0, "end": 9.9, "text": "Before."},
            {"start": 10.12, "end": 10.125, "text": "Sliver."},
            {"start": 10.2, "end": 11.4, "text": "After."},
        ],
        clip_start=0.0,
        clip_end=12.0,
        out_start=0.0,
    )
    assert all(end - start >= 0.25 for start, end, _text in cues)
    assert len({text for _start, _end, text in cues}) == len(cues)


def test_stacked_large_titles_become_one_fill_block() -> None:
    layers = [
        {
            "kind": "fill",
            "large": True,
            "box": {"x": 0.058, "y": 0.699, "w": 0.403, "h": 0.138},
            "ranges": [{"start": 2.625, "end": 3.75}],
            "text_sample": "wrong",
            "tracklet_id": "a",
        },
        {
            "kind": "fill",
            "large": True,
            "box": {"x": 0.150, "y": 0.830, "w": 0.420, "h": 0.150},
            "ranges": [{"start": 2.625, "end": 3.75}],
            "text_sample": "room",
            "tracklet_id": "b",
        },
        {
            "kind": "fill",
            "large": False,
            "box": {"x": 0.4, "y": 0.45, "w": 0.2, "h": 0.08},
            "ranges": [{"start": 3.625, "end": 4.0}],
            "text_sample": "this",
            "tracklet_id": "c",
        },
    ]
    merged = _merge_stacked_titles(layers)
    assert len(merged) == 2
    block = merged[0]
    assert block["box"]["y"] == 0.699
    assert abs(block["box"]["h"] - 0.281) < 0.001
    assert block["track"] == []
    assert block["text_sample"] == "wrong room"
    assert merged[1]["text_sample"] == "this"


def test_sentence_across_a_cut_appears_once() -> None:
    segments = [{"start": 0.0, "end": 6.0, "text": "A sentence that crosses the cut."}]
    first = _cues_for_clip(segments, clip_start=0.0, clip_end=3.0, out_start=0.0)
    second = _cues_for_clip(segments, clip_start=3.0, clip_end=6.0, out_start=3.0)
    combined = " ".join(text for _start, _end, text in first + second)
    assert combined.count("sentence") == 1
    assert combined.count("crosses") == 1


def test_active_clean_only_reads_layers_at_that_time() -> None:
    from duckcore.main import _active_clean

    edit = {
        "clean": [
            {"id": "a", "ranges": [{"start": 0.0, "end": 2.0}]},
            {"id": "b", "ranges": [{"start": 8.0, "end": 9.0}]},
        ]
    }
    assert [item["id"] for item in _active_clean(edit, 1.0)] == ["a"]
    assert [item["id"] for item in _active_clean(edit, 8.5)] == ["b"]


def test_clip_trim_and_queue_clear(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from duckcore import edits
    from duckcore.main import create_app

    source = tmp_path / "source.mp4"
    source.write_bytes(b"not a real video")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Trim test", "source_path": str(source)},
        ).json()["project"]
        edit = {
            "schema": 1,
            "id": "ed_trimtest01",
            "project_id": project["id"],
            "kind": "full",
            "title": "Full video",
            "created": 1.0,
            "updated": 1.0,
            "source": {"duration": 10.0, "width": 1080, "height": 1080, "fps": 24.0},
            "start": 0.0,
            "end": 10.0,
            "clips": [
                {"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "body"},
                {"scene": 1, "start": 4.0, "end": 10.0, "dur": 6.0, "role": "body"},
            ],
            "clean": [],
            "captions": None,
            "audio": {"mode": "original"},
        }
        edits.save_edit(edit, tmp_path)

        trimmed = client.patch(
            f"/api/projects/{project['id']}/edits/ed_trimtest01/clips/0",
            headers=headers,
            json={"start": 0.5, "end": 3.5},
        )
        assert trimmed.status_code == 200
        saved = trimmed.json()["edit"]
        assert saved["clips"][0]["start"] == 0.5
        assert saved["clips"][0]["end"] == 3.5
        assert saved["start"] == 0.5

        cleared = client.post("/api/queue/clear", headers=headers)
        assert cleared.status_code == 200
        assert cleared.json()["items"] == []
