"""Edit model, versioning, storage, history and the CRUD API."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import captions
import edits
import history_store
import routes_edits
from fastapi import HTTPException

STORY_REF = {
    "set_id": "cs_1",
    "story_id": "s1",
    "clip_hash": "46d92491cfb1bbd7",
    "title": "Story one",
    "duration": 10.0,
    "clip_count": 1,
}


def _clip(**overrides) -> dict:
    value = {
        "scene": 0,
        "start": 0.0,
        "end": 10.0,
        "dur": 10.0,
        "role": "hook",
    }
    value.update(overrides)
    return value


def _story(**overrides) -> dict:
    value = {
        "id": "s1",
        "title": "Story one",
        "start": 0.0,
        "end": 10.0,
        "dur": 10.0,
        "clips": [_clip()],
    }
    value.update(overrides)
    return value


def _job(job_id: str = "job1") -> dict:
    return {
        "id": job_id,
        "status": "ready",
        "created": 1.0,
        "updated": 1.0,
        "source": {
            "name": "source.mp4",
            "path": "/tmp/source.mp4",
            "duration": 20.0,
            "width": 1920,
            "height": 1080,
            "fingerprint": "source-fingerprint",
        },
        "analysis": {
            "scenes": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 10.0,
                    "dur": 10.0,
                    "speech": "hello world",
                    "crops": {"9:16": {"cx": 0.5, "cy": 0.5}},
                },
                {
                    "id": 1,
                    "start": 10.0,
                    "end": 20.0,
                    "dur": 10.0,
                    "speech": "second beat",
                    "crops": {"4:5": {"cx": 0.45, "cy": 0.5}},
                },
            ],
        },
        "clip_sets": [
            {
                "id": "cs_1",
                "stories": [
                    _story(),
                    _story(
                        id="s2",
                        title="Story two",
                        clips=[_clip(scene=1, start=10.0, end=20.0)],
                    ),
                ],
            },
        ],
        "renders": {},
    }


def _write_job(jobs: Path, job: dict) -> None:
    directory = jobs / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")


def _build(**overrides) -> dict:
    value = {"story_ref": dict(STORY_REF), "aspect": "9:16", "created": 1.0}
    value.update(overrides)
    return edits.build_edit(**value)


def _caption_track(job_id: str = "job1", track_id: str = "cap_test") -> captions.CaptionTrack:
    style = captions.normalize_style({})
    return captions.CaptionTrack(
        id=track_id,
        job_id=job_id,
        version=1,
        target=10,
        cues=[
            captions.CaptionCue(
                id="c1", start=0.0, end=2.0, text="First line", clip_index=0,
            ),
            captions.CaptionCue(
                id="c2", start=2.5, end=4.0, text="Second line", clip_index=0,
            ),
        ],
        style=style,
        style_id="clean",
        cue_hash="cuehash",
        style_hash="stylehash",
        clip_hash=STORY_REF["clip_hash"],
        clip_windows=[{"index": 0, "scene": 0, "start": 0.0, "end": 10.0, "duration": 10.0}],
        created=1.0,
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    job = _job()
    _write_job(jobs, job)
    return {
        "tmp_path": tmp_path,
        "data": data,
        "jobs": jobs,
        "dir": jobs / job["id"],
        "job": job,
        "job_id": job["id"],
        "client": TestClient(app.app),
    }


# ---------------------------------------------------------------- model


def test_hash_is_canonical_sha256_of_content():
    edit = _build(
        clean=[{"kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1}}],
        color={"preset": "warm_film"},
        graphics=[{"type": "text", "kind": "hook", "text": "Stop", "start": 0, "end": 2}],
    )
    content = {
        "schema_version": edits.SCHEMA_VERSION,
        "renderer_version": edit["renderer_version"],
        "story_ref": edit["story_ref"],
        "aspect": edit["aspect"],
        "clean": edit["clean"],
        "reframe": edit["reframe"],
        "motion": edit["motion"],
        "color": edit["color"],
        "graphics": edit["graphics"],
        "captions": edit["captions"],
        "audio": edit["audio"],
    }
    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert edit["hash"] == "edh_" + hashlib.sha256(encoded).hexdigest()[:32]
    assert edit["id"].startswith("ed_")
    assert edits.normalize_edit(edit) == edit


def test_hash_ignores_created_version_and_parent_but_id_does_not():
    first = _build(created=10.0)
    second = _build(created=20.0, version=2, parent=first["id"])
    assert first["hash"] == second["hash"]
    assert first["id"] != second["id"]
    restored = edits.build_edit(
        story_ref=STORY_REF, aspect="9:16", created=30.0,
    )
    assert restored["hash"] == first["hash"]
    assert restored["id"] == first["id"]


def test_renderer_version_is_part_of_the_content_hash():
    first = _build()
    second = _build(renderer_version=2)
    assert first["renderer_version"] == edits.RENDERER_VERSION
    assert second["renderer_version"] == 2
    assert first["hash"] != second["hash"]
    assert edits.normalize_edit(second)["hash"] == second["hash"]


def test_layer_defaults_and_counts():
    edit = _build(
        clean=[{"kind": "blur", "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}}],
        motion=[{"kind": "punch_in", "start": 0.0, "end": 1.0}],
        graphics=[
            {"type": "text", "kind": "lower_third", "text": "Name", "start": 0, "end": 2},
            {"type": "fx", "kind": "arrow", "start": 0, "end": 1},
        ],
        captions={"track_id": "cap_test", "style_id": "clean"},
    )
    assert edit["clean"][0]["id"] == "cl01"
    assert edit["clean"][0]["radius"] == 24
    assert edit["clean"][0]["ranges"] == []
    assert edit["motion"][0]["id"] == "mo01"
    assert edit["motion"][0]["amount"] == 0.08
    assert [item["id"] for item in edit["graphics"]] == ["tx01", "fx02"]
    assert edit["graphics"][0]["type"] == "text"
    assert edit["graphics"][1]["type"] == "fx"
    assert edits.layer_counts(edit) == {
        "clean": 1, "motion": 1, "graphics": 2, "captions": 1,
    }
    assert edit["audio"]["mode"] == "original"
    assert edit["audio"]["loudness"] == {"lufs": -14.0, "true_peak": -1.5}


def test_clip_snapshot_hash_matches_caption_engine():
    clips = [_clip(), _clip(scene=1, start=10.0, end=12.0, dur=2.0, role="payoff")]
    assert edits.clip_snapshot_hash(clips) == captions.clip_hash(clips)


def test_clean_ranges_merge_and_sort():
    edit = _build(clean=[{
        "kind": "plate",
        "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
        "ranges": [
            {"start": 2.0, "end": 3.0},
            {"start": 0.5, "end": 1.0},
            {"start": 0.9, "end": 1.4},
        ],
    }])
    assert edit["clean"][0]["ranges"] == [
        {"start": 0.5, "end": 1.4},
        {"start": 2.0, "end": 3.0},
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aspect": "16:9"},
        {"clean": [{"kind": "delogo", "box": {"x": 0, "y": 0, "w": 0.1, "h": 0.1}}]},
        {"clean": [{"kind": "inpaint", "box": {"x": 0, "y": 0, "w": 0.1, "h": 0.1}}]},
        {"clean": [{
            "kind": "plate",
            "box": {"x": 0, "y": 0, "w": 0.1, "h": 0.1},
            "label": "watermark removal",
        }]},
        {"clean": [{
            "kind": "plate",
            "box": {"x": 0, "y": 0, "w": 0.1, "h": 0.1},
            "label": "platform watermark",
        }]},
        {"clean": [{"kind": "blur", "box": {"x": 0.9, "y": 0.9, "w": 0.2, "h": 0.2}}]},
        {"motion": [{"kind": "spin", "start": 0, "end": 1}]},
        {"motion": [{"kind": "shake", "start": 0, "end": 1, "amount": 0.5}]},
        {"color": {"preset": "vaporwave"}},
        {"color": {"preset": "none", "contrast": 2.0}},
        {"graphics": [{"type": "text", "kind": "caption", "text": "x", "start": 0, "end": 1}]},
        {"graphics": [{"type": "fx", "kind": "sticker", "start": 0, "end": 1}]},
        {"graphics": [{"type": "text", "kind": "arrow", "text": "x", "start": 0, "end": 1}]},
        {"audio": {"mode": "karaoke"}},
        {"audio": {"mode": "dub", "duck_db": 3}},
        {"captions": {"track_id": "not a track"}},
    ],
)
def test_invalid_documents_are_rejected(overrides):
    with pytest.raises(edits.EditError):
        _build(**overrides)


def test_unknown_top_level_and_nested_keys_are_rejected():
    edit = _build()
    edit["stray"] = True
    with pytest.raises(edits.EditCorrupt):
        edits.normalize_edit(edit)
    with pytest.raises(edits.EditError):
        _build(reframe={"mode": "auto", "nope": 1})
    with pytest.raises(edits.EditError):
        _build(audio={"mode": "original", "extra": 1})


def test_asset_hashes_are_part_of_the_edit():
    stub = "b" * 64
    edit = _build(
        color={"preset": "none", "lut": {"path": "/tmp/look.cube", "hash": stub}},
        graphics=[{
            "type": "fx", "kind": "sticker", "start": 0, "end": 1,
            "asset": {"id": "spark", "hash": stub},
        }],
        audio={"mode": "original_bed", "music": {"file_hash": stub}},
    )
    assert edit["color"]["lut"]["hash"] == stub
    assert edit["graphics"][0]["asset"]["hash"] == stub
    assert edit["audio"]["music"]["file_hash"] == stub
    with pytest.raises(edits.EditError):
        _build(color={"lut": {"path": "/tmp/x.cube", "hash": "nope"}})


# ---------------------------------------------------------------- storage and versions


def test_save_is_immutable_and_tamper_is_detected(tmp_path):
    edit = _build(created=10.0)
    saved = edits.save_edit(tmp_path, edit)
    assert saved == edit
    again = edits.save_edit(tmp_path, {**edit, "created": 99.0})
    assert again["created"] == 10.0

    path = edits.edit_path(tmp_path, edit["id"])
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["clean"] = [{
        "id": "cl01", "kind": "plate",
        "box": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1},
        "ranges": [], "z": 0, "color": "#000000", "opacity": 1.0,
        "radius": 24, "label": "",
    }]
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(edits.EditCorrupt):
        edits.load_edit(tmp_path, edit["id"])


def test_version_chain_and_restore(tmp_path):
    first = _build(created=10.0)
    edits.save_edit(tmp_path, first)
    second = _build(
        created=20.0,
        version=2,
        parent=first["id"],
        color={"preset": "vivid_pop"},
    )
    edits.save_edit(tmp_path, second)
    chain = edits.version_chain(tmp_path, second["id"])
    assert [item["id"] for item in chain] == [first["id"], second["id"]]

    restored = edits.restored_edit(first, parent_edit=second, created=30.0)
    assert restored["version"] == 3
    assert restored["parent"] == second["id"]
    assert restored["hash"] == first["hash"]
    assert restored["id"] != first["id"]
    edits.save_edit(tmp_path, restored)
    assert len(edits.list_edits(tmp_path, key="cs_1:s1:9:16")) == 3


def test_version_chain_stops_on_a_gap(tmp_path):
    first = _build(created=10.0)
    edits.save_edit(tmp_path, first)
    second = _build(created=20.0, version=2, parent="ed_" + "0" * 32)
    edits.save_edit(tmp_path, second)
    assert [item["id"] for item in edits.version_chain(tmp_path, second["id"])] == [
        second["id"],
    ]


def test_pointer_helpers_ignore_malformed_tables():
    job = {"story_edits": "nope"}
    key = edits.story_key("cs_1", "s1", "9:16")
    assert edits.pointer_edit_id(job, key) is None
    edit = _build(created=10.0)
    assert edits.set_pointer(job, edit) == key
    assert edits.pointer_edit_id(job, key) == edit["id"]
    assert edits.clear_pointer(job, key) is True
    assert edits.pointer_edit_id(job, key) is None
    assert edits.clear_pointer(job, key) is False


def test_history_entry_is_compatible_with_history_store(tmp_path):
    edit = _build(created=10.0)
    edits.save_edit(tmp_path, edit)
    row = edits.append_history(tmp_path, edit)
    assert row is not None
    assert row["type"] == "edit"
    assert row["record_key"] == "cs_1:s1:9:16"
    entries = history_store.list_entries(tmp_path)
    assert [item["id"] for item in entries] == [edit["id"]]
    stored = history_store.get_entry(tmp_path, edit["id"])
    assert stored is not None
    assert stored["snapshot"]["edit"]["hash"] == edit["hash"]


# ---------------------------------------------------------------- routes


def _create(client: TestClient, job_id: str, **overrides) -> dict:
    body = {"set_id": "cs_1", "story_id": "s1", "aspect": "9:16"}
    body.update(overrides)
    response = client.post(f"/api/jobs/{job_id}/edits", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_edit_sets_pointer_history_and_is_idempotent(env):
    client = env["client"]
    created = _create(client, env["job_id"], clean=[{
        "kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1},
    }])
    assert created["version"] == 1
    assert created["changed"] is True
    assert created["key"] == "cs_1:s1:9:16"

    job = app.load_job(env["job_id"])
    assert job["story_edits"]["cs_1:s1:9:16"] == created["id"]
    entries = history_store.list_entries(env["dir"])
    assert entries and entries[0]["type"] == "edit"

    same = _create(client, env["job_id"], clean=[{
        "kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1},
    }])
    assert same["id"] == created["id"]
    assert same["version"] == 1
    assert same["changed"] is False


def test_patch_creates_a_new_version_and_keeps_old_bytes(env):
    client = env["client"]
    created = _create(client, env["job_id"])
    path = edits.edit_path(env["dir"], created["id"])
    before = path.read_bytes()

    response = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}",
        json={"color": {"preset": "warm_film"}},
    )
    assert response.status_code == 200, response.text
    patched = response.json()
    assert patched["changed"] is True
    assert patched["version"] == 2
    assert patched["edit"]["parent"] == created["id"]
    assert path.read_bytes() == before

    job = app.load_job(env["job_id"])
    assert job["story_edits"]["cs_1:s1:9:16"] == patched["id"]

    versions = client.get(
        f"/api/jobs/{env['job_id']}/edits/{patched['id']}/versions",
    )
    assert versions.status_code == 200
    body = versions.json()
    assert [row["version"] for row in body["versions"]] == [1, 2]
    assert body["current"] == patched["id"]


def test_patch_without_changes_is_a_no_op(env):
    client = env["client"]
    created = _create(client, env["job_id"])
    response = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}",
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is False
    assert body["id"] == created["id"]
    assert body["version"] == 1


def test_undo_and_restore_create_versions(env):
    client = env["client"]
    first = _create(client, env["job_id"])
    second = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{first['id']}",
        json={"color": {"preset": "vivid_pop"}},
    ).json()

    undo = client.post(
        f"/api/jobs/{env['job_id']}/edits/{second['id']}/undo",
    )
    assert undo.status_code == 200, undo.text
    undone = undo.json()
    assert undone["version"] == 3
    assert undone["edit"]["parent"] == second["id"]
    assert undone["hash"] == first["hash"]

    restore = client.post(
        f"/api/jobs/{env['job_id']}/edits/{undone['id']}/restore",
        json={"version": second["id"]},
    )
    assert restore.status_code == 200, restore.text
    restored = restore.json()
    assert restored["version"] == 4
    assert restored["edit"]["parent"] == undone["id"]
    assert restored["hash"] == second["hash"]

    stale = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{first['id']}",
        json={"color": {"preset": "cool_fade"}},
    )
    assert stale.status_code == 409


def test_restore_requires_a_version_and_matching_story(env):
    client = env["client"]
    created = _create(client, env["job_id"])
    missing = client.post(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}/restore",
        json={},
    )
    assert missing.status_code == 422

    other = _create(client, env["job_id"], story_id="s2")
    cross = client.post(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}/restore",
        json={"version": other["id"]},
    )
    assert cross.status_code == 409


def test_get_list_and_current_routes(env):
    client = env["client"]
    created = _create(client, env["job_id"])
    fetched = client.get(f"/api/jobs/{env['job_id']}/edits/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["edit"]["hash"] == created["hash"]

    listed = client.get(f"/api/jobs/{env['job_id']}/edits")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["pointers"]["cs_1:s1:9:16"] == created["id"]

    current = client.get(
        f"/api/jobs/{env['job_id']}/edits/current",
        params={"set_id": "cs_1", "story_id": "s1", "aspect": "9:16"},
    )
    assert current.status_code == 200
    assert current.json()["id"] == created["id"]

    partial = client.get(
        f"/api/jobs/{env['job_id']}/edits", params={"set_id": "cs_1"},
    )
    assert partial.status_code == 422


def test_delete_clears_pointer_and_keeps_immutable_versions(env):
    client = env["client"]
    first = _create(client, env["job_id"])
    second = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{first['id']}",
        json={"color": {"preset": "warm_film"}},
    ).json()
    deleted = client.delete(f"/api/jobs/{env['job_id']}/edits/{second['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"cleared": "cs_1:s1:9:16", "kept_versions": 2}
    assert edits.pointer_edit_id(app.load_job(env["job_id"]), "cs_1:s1:9:16") is None
    kept = client.get(f"/api/jobs/{env['job_id']}/edits/{second['id']}")
    assert kept.status_code == 200


def test_stale_head_is_refused_instead_of_forking(env):
    client = env["client"]
    first = _create(client, env["job_id"])
    ahead = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{first['id']}",
        json={"color": {"preset": "warm_film"}},
    ).json()
    base = edits.load_edit(env["dir"], first["id"])
    built_from_first = edits.build_edit(
        story_ref=base["story_ref"], aspect="9:16", version=2, parent=base["id"],
        **{key: base[key] for key in routes_edits._LAYER_FIELDS if key != "motion"},
        motion=[{"kind": "punch_in", "start": 0.0, "end": 1.0, "amount": 0.1}],
    )
    with pytest.raises(HTTPException) as caught:
        routes_edits._persist(env["job_id"], built_from_first)
    assert caught.value.status_code == 409
    assert edits.pointer_edit_id(app.load_job(env["job_id"]), "cs_1:s1:9:16") == ahead["id"]


def test_aspects_fork_independently(env):
    client = env["client"]
    wide = _create(client, env["job_id"], aspect="9:16")
    tall = _create(client, env["job_id"], aspect="4:5")
    assert wide["id"] != tall["id"]
    job = app.load_job(env["job_id"])
    assert job["story_edits"]["cs_1:s1:9:16"] == wide["id"]
    assert job["story_edits"]["cs_1:s1:4:5"] == tall["id"]

    patched = client.patch(
        f"/api/jobs/{env['job_id']}/edits/{wide['id']}",
        json={"color": {"preset": "warm_film"}},
    )
    assert patched.status_code == 200, patched.text
    job = app.load_job(env["job_id"])
    assert job["story_edits"]["cs_1:s1:9:16"] == patched.json()["id"]
    assert job["story_edits"]["cs_1:s1:4:5"] == tall["id"]


def test_unknown_job_set_story_and_aspect(env):
    client = env["client"]
    assert client.post(
        "/api/jobs/missing/edits",
        json={"set_id": "cs_1", "story_id": "s1", "aspect": "9:16"},
    ).status_code == 404
    assert client.post(
        f"/api/jobs/{env['job_id']}/edits",
        json={"set_id": "cs_nope", "story_id": "s1", "aspect": "9:16"},
    ).status_code == 404
    assert client.post(
        f"/api/jobs/{env['job_id']}/edits",
        json={"set_id": "cs_1", "story_id": "s_nope", "aspect": "9:16"},
    ).status_code == 404
    assert client.post(
        f"/api/jobs/{env['job_id']}/edits",
        json={"set_id": "cs_1", "story_id": "s1", "aspect": "1:1"},
    ).status_code == 422
    assert client.post(
        f"/api/jobs/{env['job_id']}/edits",
        json={"set_id": "cs_1", "story_id": "s1", "aspect": "9:16", "stray": 1},
    ).status_code == 422


def test_caption_track_reference_is_owned_and_validated(env):
    client = env["client"]
    captions.save_track(env["dir"], _caption_track())
    created = _create(
        client, env["job_id"],
        captions={"track_id": "cap_test", "style_id": "clean"},
    )
    assert created["edit"]["captions"]["track_id"] == "cap_test"

    missing = client.post(
        f"/api/jobs/{env['job_id']}/edits",
        json={
            "set_id": "cs_1", "story_id": "s1", "aspect": "4:5",
            "captions": {"track_id": "cap_missing"},
        },
    )
    assert missing.status_code == 404

    foreign = _caption_track(job_id="other_job", track_id="cap_foreign")
    captions.save_track(env["dir"], foreign)
    wrong = client.post(
        f"/api/jobs/{env['job_id']}/edits",
        json={
            "set_id": "cs_1", "story_id": "s2", "aspect": "9:16",
            "captions": {"track_id": "cap_foreign"},
        },
    )
    assert wrong.status_code == 409


def test_compile_route_returns_filters_and_overlays(env):
    client = env["client"]
    captions.save_track(env["dir"], _caption_track())
    created = _create(
        client, env["job_id"],
        clean=[{
            "kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1},
        }],
        motion=[{"kind": "punch_in", "start": 0.0, "end": 2.0}],
        color={"preset": "warm_film"},
        graphics=[{
            "type": "text", "kind": "hook", "text": "Stop scrolling",
            "start": 0.0, "end": 2.0,
        }],
        captions={"track_id": "cap_test", "style_id": "clean"},
    )
    response = client.get(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}/compile",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edit_id"] == created["id"]
    segment = body["segments"][0]
    assert segment["crop"] == {"x": 656, "y": 0, "w": 608, "h": 1080}
    assert segment["filter"].startswith("drawbox=")
    assert "zoompan=" in segment["filter"]
    assert "eq=" in segment["filter"]
    assert [layer["type"] for layer in body["overlays"]] == [
        "text", "caption", "caption",
    ]
    assert body["captions"]["cue_count"] == 2

    without = client.get(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}/compile",
        params={"include_captions": "false"},
    )
    assert without.status_code == 200, without.text
    assert without.json()["captions"]["compiled"] is False
    assert [layer["type"] for layer in without.json()["overlays"]] == ["text"]


def test_compile_rejects_a_missing_caption_track(env):
    client = env["client"]
    captions.save_track(env["dir"], _caption_track())
    created = _create(
        client, env["job_id"],
        captions={"track_id": "cap_test", "style_id": "clean"},
    )
    captions.track_path(env["dir"], "cap_test").unlink()
    response = client.get(
        f"/api/jobs/{env['job_id']}/edits/{created['id']}/compile",
    )
    assert response.status_code == 409
