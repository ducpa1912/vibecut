"""Atomic trim, undo and rebind routes (ROADMAP.md, atomic trim contract)."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

import app
import artifacts
import captions
import edits

from test_clipset import api, write_job  # noqa: F401


class FakeReflow:
    def __init__(self):
        self.calls: list[dict] = []
        self.saves = 0
        self.fail = False

    def module(self) -> types.ModuleType:
        module = types.ModuleType("caption_reflow")

        class ReflowError(Exception):
            pass

        module.ReflowError = ReflowError
        owner = self

        class Result:
            def __init__(self, track, counts):
                self.track = track
                self.counts = counts

            def save(self, job_dir):
                owner.saves += 1
                captions.save_track(job_dir, self.track)
                return self.track.id

        def rebuild(job_id, job, set_id, old_story, new_story, old_track_id, **_kwargs):
            owner.calls.append({
                "old": old_story["start"],
                "new": new_story["start"],
                "track": old_track_id,
            })
            if owner.fail:
                raise ReflowError("forced caption failure")
            clip_hash = edits.clip_snapshot_hash(new_story["clips"])
            return Result(
                captions.CaptionTrack(
                    id="cap_" + clip_hash,
                    job_id=job_id,
                    version=1,
                    target=int(round(float(new_story["dur"]))),
                    cues=[],
                    cue_hash="cue_" + clip_hash,
                    style_id="default",
                    clip_hash=clip_hash,
                ),
                {"kept": 3, "moved": 2, "dropped": 1, "added": 4, "manual_kept": 1},
            )

        module.rebuild_for_story = rebuild
        return module


@pytest.fixture
def reflow(monkeypatch):
    fake = FakeReflow()
    monkeypatch.setitem(sys.modules, "caption_reflow", fake.module())
    return fake


def make_set(api, count: int = 3):
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": count}).json()["clip_set"]
    return record, record["stories"][0]


def make_edit(api, record, story, *, aspect="9:16", graphics=None):
    response = api.post("/api/jobs/j1/edits", json={
        "set_id": record["id"],
        "story_id": story["id"],
        "aspect": aspect,
        "graphics": graphics or [],
    })
    assert response.status_code == 200, response.text
    return response.json()["edit"]


def trim_url(record, story) -> str:
    return f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/trim"


def snapshot(api) -> tuple[str, set[str], bool]:
    directory = api.jobs_dir / "j1"
    job_bytes = (directory / "job.json").read_text()
    edit_files = {
        path.name for path in (directory / "edits").glob("*.json")
    } if (directory / "edits").is_dir() else set()
    return job_bytes, edit_files, (directory / "trims").is_dir()


def previous_sentence(api, record, story) -> int:
    payload = api.get(trim_url(record, story)).json()
    ids = [item["id"] for item in payload["pool"]]
    first = story["sentences"][0]["id"]
    return ids[ids.index(first) - 1]


def test_get_trim_contract(api):
    record, story = make_set(api)
    response = api.get(trim_url(record, story))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "revision", "story", "clip_hash", "pool", "neighbours", "aspects",
        "limits",
    }
    assert body["revision"] == 0
    assert body["story"] == {
        "id": story["id"],
        "start": story["start"],
        "end": story["end"],
        "dur": story["dur"],
        "sentence_ids": [item["id"] for item in story["sentences"]],
    }
    assert body["clip_hash"] == edits.clip_snapshot_hash(story["clips"])
    assert body["limits"] == {"min_s": 15.0, "max_s": 90.0}
    assert body["aspects"] == {}
    assert body["neighbours"]["before"] is None
    assert body["neighbours"]["after"]["id"] == record["stories"][1]["id"]
    assert all(set(item) == {"id", "start", "end", "text"} for item in body["pool"])
    assert [item["id"] for item in body["pool"]] == sorted(
        item["id"] for item in body["pool"]
    )


def test_trim_earlier_moves_layers_and_keeps_pins(api, reflow):
    record, story = make_set(api)
    edit = make_edit(api, record, story, graphics=[
        {"type": "text", "kind": "hook", "text": "Source hook", "start": 0.0, "end": 2.0},
        {"type": "text", "kind": "hook", "text": "Pinned hook", "start": 0.0, "end": 2.0, "anchor": "story_start"},
        {"type": "text", "kind": "title", "text": "Middle", "start": 10.0, "end": 12.0},
        {"type": "text", "kind": "cta", "text": "Pinned CTA", "start": 18.0, "end": 20.0, "pin": "story_end"},
    ])
    assert edit["graphics"][1]["pin"] == "story_start"

    payload = api.get(trim_url(record, story)).json()
    start = previous_sentence(api, record, story)
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": start,
        "end_sentence": story["sentences"][-1]["id"],
        "aspects": payload["aspects"],
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["revision"] == 1
    assert result["story"]["start"] < story["start"]
    assert result["duration"] == result["story"]["dur"]
    assert result["clip_hash"] == edits.clip_snapshot_hash(
        app._story_in_set(
            app._clip_set_in_job(app.load_job("j1"), record["id"]),
            story["id"],
        )["clips"]
    )
    layers = {item["text"]: item for item in result["edits"]["9:16"]["graphics"]}
    delta = round(story["start"] - result["story"]["start"], 3)
    assert layers["Source hook"]["start"] == pytest.approx(delta)
    assert layers["Source hook"]["end"] == pytest.approx(2.0 + delta)
    assert layers["Middle"]["start"] == pytest.approx(10.0 + delta)
    assert layers["Pinned hook"]["start"] == 0.0
    assert layers["Pinned hook"]["end"] == 2.0
    assert layers["Pinned CTA"]["start"] == pytest.approx(result["duration"] - 2.0)
    assert layers["Pinned CTA"]["end"] == pytest.approx(result["duration"])
    assert "hidden" not in layers["Source hook"]
    assert result["receipt"]["layers"]["moved"] == ["tx01", "tx03"]
    assert set(result["receipt"]["layers"]["pinned"]) == {"tx02", "tx04"}
    assert result["captions"]["rebuilt"] is True
    assert result["captions"]["clip_hash"] == result["clip_hash"]
    assert result["captions"]["track_id"].startswith("cap_")
    assert result["stale_aspects"] == []
    assert result["undo_token"] == result["receipt"]["id"]
    receipt_path = api.jobs_dir / "j1" / "trims" / f"{result['undo_token']}.json"
    assert receipt_path.is_file()
    stored = json.loads(receipt_path.read_text())
    assert stored["before"]["edits"]["9:16"]["id"] == edit["id"]
    assert stored["before"]["revision"] == 0

    job = app.load_job("j1")
    new_story = app._story_in_set(
        app._clip_set_in_job(job, record["id"]), story["id"],
    )
    assert new_story["revision"] == 1
    assert job["story_captions"][f"{record['id']}:{story['id']}"] == result["captions"]["track_id"]
    current = api.get("/api/jobs/j1/edits/current", params={
        "set_id": record["id"], "story_id": story["id"], "aspect": "9:16",
    }).json()
    assert current["edit"]["id"] == result["edits"]["9:16"]["id"]
    assert current["edit"]["version"] == 2


def test_trim_later_hides_outside_layers_without_deleting(api, reflow):
    record, story = make_set(api)
    make_edit(api, record, story, graphics=[
        {"type": "text", "kind": "hook", "text": "Opening", "start": 0.0, "end": 2.0},
        {"type": "text", "kind": "cta", "text": "Close", "start": 18.0, "end": 20.0},
    ])
    start = story["sentences"][2]["id"]
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": start,
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert response.status_code == 200, response.text
    result = response.json()
    layers = {item["text"]: item for item in result["edits"]["9:16"]["graphics"]}
    assert len(layers) == 2
    assert layers["Opening"]["hidden"] is True
    assert layers["Opening"]["start"] == 0.0
    assert layers["Opening"]["end"] == 2.0
    assert "hidden" not in layers["Close"]
    assert result["receipt"]["layers"]["outside"] == ["tx01"]
    assert result["receipt"]["layers"]["moved"] == ["tx02"]


def test_dry_run_returns_the_result_and_writes_nothing(api, reflow, monkeypatch):
    record, story = make_set(api)
    make_edit(api, record, story)
    before = snapshot(api)

    def forbidden(job_id, mutator):
        raise AssertionError("dry_run must not commit")

    monkeypatch.setattr(app, "update_job", forbidden)
    start = story["sentences"][2]["id"]
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": start,
        "end_sentence": story["sentences"][-1]["id"],
        "dry_run": True,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["revision"] == 1
    assert result["receipt"]["kind"] == "trim"
    assert result["receipt"]["new"]["start"] == result["story"]["start"]
    assert result["edits"]["9:16"]["version"] == 2
    assert reflow.saves == 0
    assert snapshot(api) == before
    assert not (api.jobs_dir / "j1" / "trims" / f"{result['undo_token']}.json").exists()


def test_one_update_job_is_the_only_commit(api, reflow, monkeypatch):
    record, story = make_set(api)
    make_edit(api, record, story)
    calls = []
    original = app.update_job

    def counting(job_id, mutator):
        calls.append(job_id)
        return original(job_id, mutator)

    monkeypatch.setattr(app, "update_job", counting)
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][1]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert response.status_code == 200, response.text
    assert calls == ["j1"]


def test_failed_commit_leaves_orphans_and_never_mutates(api, reflow, monkeypatch):
    record, story = make_set(api)
    make_edit(api, record, story)
    before = snapshot(api)

    def boom(job_id, mutator):
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(app, "update_job", boom)
    with pytest.raises(RuntimeError):
        api.post(trim_url(record, story), json={
            "expected_revision": 0,
            "start_sentence": story["sentences"][2]["id"],
            "end_sentence": story["sentences"][-1]["id"],
        })
    after = snapshot(api)
    assert after[0] == before[0]  # job.json is byte-identical
    assert after[1] >= before[1]  # immutable Edit sidecars may be orphans
    assert after[2] is True  # the receipt is written before the commit
    assert (api.jobs_dir / "j1" / "edits").is_dir()


def test_missing_t2_module_fails_closed_without_writes(api, monkeypatch):
    record, story = make_set(api)
    make_edit(api, record, story)
    before = snapshot(api)
    monkeypatch.setitem(sys.modules, "caption_reflow", None)
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][2]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "caption_rebuild_failed"
    assert snapshot(api) == before


def test_caption_failure_rolls_back_everything(api, reflow):
    record, story = make_set(api)
    edit = make_edit(api, record, story)
    before = snapshot(api)
    reflow.fail = True
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][2]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "caption_rebuild_failed"
    assert response.json()["detail"]["current"]["revision"] == 0
    assert snapshot(api) == before
    job = app.load_job("j1")
    stored = app._story_in_set(
        app._clip_set_in_job(job, record["id"]), story["id"],
    )
    assert stored["start"] == story["start"]
    assert stored.get("revision", 0) == 0
    assert edits.pointer_edit_id(
        job, edits.story_key(record["id"], story["id"], "9:16"),
    ) == edit["id"]


def test_revision_and_edit_conflicts_return_current_state(api, reflow):
    record, story = make_set(api)
    make_edit(api, record, story)
    stale_revision = api.post(trim_url(record, story), json={
        "expected_revision": 9,
        "start_sentence": story["sentences"][1]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert stale_revision.status_code == 409
    detail = stale_revision.json()["detail"]
    assert detail["code"] == "revision_mismatch"
    assert detail["current"]["revision"] == 0
    assert detail["current"]["story"]["id"] == story["id"]

    stale_edit = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][1]["id"],
        "end_sentence": story["sentences"][-1]["id"],
        "aspects": {"9:16": "ed_" + "0" * 32},
    })
    assert stale_edit.status_code == 409
    assert stale_edit.json()["detail"]["code"] == "edit_changed"


def test_patch_clip_set_accepts_expected_revision_and_bumps(api):
    record, story = make_set(api)
    wanted = [item["id"] for item in story["sentences"][1:]]
    url = f"/api/jobs/j1/clip-sets/{record['id']}"
    patched = api.patch(url, json={
        "stories": [{"id": story["id"], "sentences": wanted}],
        "expected_revision": 0,
    })
    assert patched.status_code == 200, patched.text
    updated = next(
        item for item in patched.json()["clip_set"]["stories"]
        if item["id"] == story["id"]
    )
    assert updated["revision"] == 1
    assert updated["start"] == story["sentences"][1]["start"]

    same = api.patch(url, json={
        "stories": [{"id": story["id"], "sentences": wanted}],
        "expected_revision": 1,
    })
    assert same.status_code == 200, same.text
    unchanged = next(
        item for item in same.json()["clip_set"]["stories"]
        if item["id"] == story["id"]
    )
    assert unchanged["revision"] == 1

    stale = api.patch(url, json={
        "stories": [{"id": story["id"], "sentences": wanted}],
        "expected_revision": 0,
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_mismatch"


def test_undo_restores_range_layers_and_captions_as_new_versions(api, reflow):
    record, story = make_set(api)
    make_edit(api, record, story, graphics=[
        {"type": "text", "kind": "hook", "text": "Opening", "start": 0.0, "end": 2.0},
        {"type": "text", "kind": "title", "text": "Middle", "start": 10.0, "end": 12.0},
    ])
    job_dir = app._job_dir("j1")
    old_track = captions.CaptionTrack(
        id="cap_oldtrack",
        job_id="j1",
        version=1,
        target=int(round(story["dur"])),
        cues=[],
        cue_hash="cue_old",
        style_id="default",
        clip_hash=edits.clip_snapshot_hash(story["clips"]),
    )
    captions.save_track(job_dir, old_track)
    app._set_story_track("j1", f"{record['id']}:{story['id']}", old_track.id)
    head = app.load_job("j1")
    old_head = edits.pointer_edit_id(
        head, edits.story_key(record["id"], story["id"], "9:16"),
    )

    trimmed = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][2]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert trimmed.status_code == 200, trimmed.text
    result = trimmed.json()
    assert result["receipt"]["before"]["caption_track"] == old_track.id
    assert result["captions"]["track_id"] != old_track.id

    undone = api.post(trim_url(record, story) + "/undo", json={
        "undo_token": result["undo_token"],
        "expected_revision": result["revision"],
    })
    assert undone.status_code == 200, undone.text
    restored = undone.json()
    assert restored["revision"] == result["revision"] + 1
    assert restored["story"]["start"] == story["start"]
    assert restored["story"]["end"] == story["end"]
    assert restored["clip_hash"] == edits.clip_snapshot_hash(story["clips"])
    layers = {item["text"]: item for item in restored["edits"]["9:16"]["graphics"]}
    assert layers["Opening"]["start"] == 0.0
    assert layers["Opening"]["end"] == 2.0
    assert "hidden" not in layers["Opening"]
    assert restored["edits"]["9:16"]["version"] == result["edits"]["9:16"]["version"] + 1
    assert restored["edits"]["9:16"]["id"] != old_head
    assert restored["captions"]["track_id"] == old_track.id
    assert restored["undo_token"] != result["undo_token"]
    job = app.load_job("j1")
    assert job["story_captions"][f"{record['id']}:{story['id']}"] == old_track.id

    # Redo is the undo of the undo, as a new version.
    redone = api.post(trim_url(record, story) + "/undo", json={
        "undo_token": restored["undo_token"],
        "expected_revision": restored["revision"],
    })
    assert redone.status_code == 200, redone.text
    assert redone.json()["revision"] == restored["revision"] + 1
    assert redone.json()["story"]["start"] == result["story"]["start"]


def test_undo_is_rejected_after_a_later_trim(api, reflow):
    record, story = make_set(api)
    make_edit(api, record, story)
    first = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][1]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    }).json()
    second = api.post(trim_url(record, story), json={
        "expected_revision": first["revision"],
        "start_sentence": story["sentences"][2]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert second.status_code == 200, second.text
    stale = api.post(trim_url(record, story) + "/undo", json={
        "undo_token": first["undo_token"],
        "expected_revision": second.json()["revision"],
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_mismatch"


def test_rebind_repairs_every_stale_aspect(api, reflow):
    record, story = make_set(api)
    first = make_edit(api, record, story, aspect="9:16", graphics=[
        {"type": "text", "kind": "hook", "text": "Nine", "start": 0.0, "end": 2.0},
    ])
    second = make_edit(api, record, story, aspect="4:5", graphics=[
        {"type": "text", "kind": "hook", "text": "Four", "start": 0.0, "end": 2.0},
    ])
    wanted = [item["id"] for item in story["sentences"][1:]]
    patched = api.patch(f"/api/jobs/j1/clip-sets/{record['id']}", json={
        "stories": [{"id": story["id"], "sentences": wanted}],
        "expected_revision": 0,
    })
    assert patched.status_code == 200, patched.text
    payload = api.get(trim_url(record, story)).json()
    assert payload["revision"] == 1
    assert payload["aspects"]["9:16"]["stale"] is True
    assert payload["aspects"]["4:5"]["stale"] is True

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/rebind",
        json={"expected_revision": 1},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["revision"] == 2
    assert result["story"]["start"] == story["sentences"][1]["start"]
    assert result["stale_aspects"] == []
    assert result["receipt"]["kind"] == "rebind"
    assert result["edits"]["9:16"]["id"] != first["id"]
    assert result["edits"]["4:5"]["id"] != second["id"]
    assert result["edits"]["9:16"]["story_ref"]["clip_hash"] == result["clip_hash"]
    assert result["edits"]["4:5"]["story_ref"]["clip_hash"] == result["clip_hash"]
    after = api.get(trim_url(record, story)).json()
    assert after["aspects"]["9:16"]["stale"] is False
    assert after["aspects"]["4:5"]["stale"] is False


def test_rebind_rejects_a_stale_revision(api, reflow):
    record, story = make_set(api)
    make_edit(api, record, story)
    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/rebind",
        json={"expected_revision": 5},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "revision_mismatch"


def test_trim_never_deletes_artifacts(api, reflow, monkeypatch):
    record, story = make_set(api)
    make_edit(api, record, story)
    artifact_id = "art_" + "a" * 24
    artifact_file = api.jobs_dir / "j1" / "artifacts" / artifact_id / "reel.mp4"
    artifact_file.parent.mkdir(parents=True)
    artifact_file.write_bytes(b"old render")
    monkeypatch.setattr(artifacts, "list_manifests", lambda job_dir: [{
        "artifact_id": artifact_id,
        "story_id": story["id"],
        "aspect": "9:16",
        "edit_hash": "old_hash",
    }])
    response = api.post(trim_url(record, story), json={
        "expected_revision": 0,
        "start_sentence": story["sentences"][2]["id"],
        "end_sentence": story["sentences"][-1]["id"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["invalidated_artifacts"] == [artifact_id]
    assert artifact_file.is_file()
    assert artifact_file.read_bytes() == b"old render"
