"""Regression tests for the append-import path."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import json

from duckcore import append, captions, edits
from duckcore.store import ProjectStore


def test_append_rejects_another_project_source(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    first = tmp_path / "imports" / "first.mp4"
    second = tmp_path / "imports" / "second.mp4"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    project = store.create("First", first)
    store.create("Second", second)

    with pytest.raises(append.AppendError, match="another project"):
        append.append_video(
            project["id"],
            second,
            "full",
            store=store,
            data_root=tmp_path,
        )


def test_offset_scene_keeps_global_id_and_time() -> None:
    scene = {"id": 7, "start": 1.0, "end": 3.0, "dur": 2.0, "mid": 2.0}
    shifted = append._offset_scene(scene, 12.5, 41)
    assert shifted["id"] == 41
    assert shifted["start"] == 13.5
    assert shifted["end"] == 15.5
    assert shifted["dur"] == 2.0
    assert shifted["mid"] == 14.5


def test_append_job_reports_done(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        append, "append_locked",
        lambda *args, **kwargs: {"scenes": 2, "offset": 4.0, "duration": 6.0},
    )
    job = append.start_job(
        "prj_job", "source.mp4", "full",
        store=None, data_root=tmp_path, checks=None,
    )
    for _ in range(50):
        status = append.job_status(job["id"])
        if status["state"] in {"done", "failed"}:
            break
        time.sleep(0.02)
    assert status["state"] == "done"
    assert status["scenes"] == 2
    assert status["offset"] == 4.0
    assert append.active_job("prj_job") is None


def test_append_job_keeps_import_when_speech_read_fails(tmp_path: Path, monkeypatch) -> None:
    class Checks:
        def status(self, project_id):
            return {"result": {"append": {"analysis": "failed", "error": "speech unavailable"}}}

    monkeypatch.setattr(
        append, "append_locked",
        lambda *args, **kwargs: {"scenes": 1, "offset": 2.0, "duration": 3.0},
    )
    job = append.start_job(
        "prj_job_warn", "source.mp4", "full",
        store=None, data_root=tmp_path, checks=Checks(),
    )
    for _ in range(50):
        status = append.job_status(job["id"])
        if status["state"] in {"done", "failed"}:
            break
        time.sleep(0.02)
    assert status["state"] == "done"
    assert "speech unavailable" in status["warning"]


def test_append_job_reports_failure(tmp_path: Path, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise append.AppendError("bad video")

    monkeypatch.setattr(append, "append_locked", fail)
    job = append.start_job(
        "prj_job_fail", "source.mp4", "full",
        store=None, data_root=tmp_path, checks=None,
    )
    for _ in range(50):
        status = append.job_status(job["id"])
        if status["state"] in {"done", "failed"}:
            break
        time.sleep(0.02)
    assert status["state"] == "failed"
    assert "bad video" in status["error"]


def test_prepare_edit_does_not_write_before_commit(tmp_path: Path) -> None:
    project = {"id": "prj_prepare", "source_path": str(tmp_path / "source.mp4")}
    result = {
        "meta": {"duration": 4.0, "width": 1920, "height": 1080, "fps": 30.0},
        "scenes": [{"id": 1, "start": 0.0, "end": 4.0}],
    }
    edit, path, created = append._prepare_edit(project, result, [], tmp_path)
    assert created is True
    assert edit["id"].startswith("ed_")
    assert not path.exists()


def test_recover_commits_rolls_back_interrupted_append(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    old_source = tmp_path / "imports" / "old.mp4"
    new_source = tmp_path / "imports" / "new.mp4"
    old_source.parent.mkdir(parents=True)
    old_source.write_bytes(b"old")
    new_source.write_bytes(b"new")
    project = store.create("Project", old_source)
    store.update_source(project["id"], new_source)

    project_dir = tmp_path / "projects" / project["id"]
    check_path = project_dir / "check.json"
    check_path.parent.mkdir(parents=True)
    check_path.write_text('{"scenes": [{"id": 2}], "append": {"analysis": "complete"}}', encoding="utf-8")
    edit_id = "ed_recover01"
    edit_path = project_dir / "edits" / f"{edit_id}.json"
    edit_path.parent.mkdir(parents=True)
    edit_path.write_text('{"id": "ed_recover01", "clips": [{"scene": 2}]}', encoding="utf-8")

    folder = tmp_path / "imports" / "interrupted"
    backup = folder / ".commit"
    backup.mkdir(parents=True)
    (backup / "check.json").write_text('{"scenes": [{"id": 1}], "append": {"analysis": "old"}}', encoding="utf-8")
    (backup / "edit.json").write_text('{"id": "ed_recover01", "clips": [{"scene": 1}]}', encoding="utf-8")
    (backup / "marker.json").write_text(json.dumps({
        "project_id": project["id"],
        "old_source": str(old_source),
        "edit_path": str(edit_path),
        "edit_created": False,
    }), encoding="utf-8")

    append.recover_commits(store, tmp_path)
    assert Path(store.get(project["id"])["source_path"]) == old_source
    assert '"id": 1' in check_path.read_text(encoding="utf-8")
    assert '"scene": 1' in edit_path.read_text(encoding="utf-8")
    assert not folder.exists()


def test_archive_source_moves_master_into_project_history(tmp_path: Path) -> None:
    old = tmp_path / "imports" / "old" / "source.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"master")
    append._archive_source(old, "prj_archive", tmp_path)
    history = tmp_path / "projects" / "prj_archive" / "history"
    assert not old.exists()
    assert [item.name for item in history.iterdir() if item.is_file()]


def test_recover_commits_keeps_committed_append(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    old_source = tmp_path / "imports" / "old.mp4"
    new_source = tmp_path / "imports" / "new.mp4"
    old_source.parent.mkdir(parents=True)
    old_source.write_bytes(b"old")
    new_source.write_bytes(b"new")
    project = store.create("Project", old_source)
    store.update_source(project["id"], new_source)

    folder = tmp_path / "imports" / "committed"
    backup = folder / ".commit"
    backup.mkdir(parents=True)
    (backup / "committed").write_text("1", encoding="utf-8")
    (backup / "marker.json").write_text(json.dumps({
        "project_id": project["id"],
        "old_source": str(old_source),
        "edit_path": str(tmp_path / "projects" / project["id"] / "edits" / "ed_missing.json"),
        "edit_created": False,
    }), encoding="utf-8")

    append.recover_commits(store, tmp_path)
    assert Path(store.get(project["id"])["source_path"]) == new_source
    assert folder.is_dir()
    assert not backup.exists()


def test_remove_source_never_deletes_project_history(tmp_path: Path) -> None:
    history = tmp_path / "projects" / "prj_one" / "history" / "source.mp4"
    history.parent.mkdir(parents=True)
    history.write_bytes(b"master")
    append._remove_source(history, tmp_path)
    assert history.is_file()

    copy = tmp_path / "imports" / "abc" / "source.mp4"
    copy.parent.mkdir(parents=True)
    copy.write_bytes(b"copy")
    append._remove_source(copy, tmp_path)
    assert not copy.exists()


def test_captions_append_only_new_clip_range(tmp_path: Path) -> None:
    edit = {
        "id": "ed_append01",
        "project_id": "prj_append01",
        "clips": [
            {"start": 0.0, "end": 2.0, "dur": 2.0},
            {"start": 5.0, "end": 7.0, "dur": 2.0},
        ],
        "captions": {
            "track_id": "cap_test",
            "burn": False,
            "cues": [
                {"id": "cq_old", "start": 0.0, "end": 1.5, "text": "Old line.", "source_text": "Old line."},
            ],
        },
    }
    transcript = {
        "segments": [
            {"start": 5.2, "end": 6.5, "text": "New line."},
        ],
    }
    track = captions.append_appended(edit, transcript, tmp_path, offset=5.0)
    assert track is not None
    assert [cue["text"] for cue in track["cues"]] == ["Old line.", "New line."]
    assert track["cues"][1]["start"] == pytest.approx(2.2)
    assert track["cues"][1]["source_text"] == "New line."
    saved = edits.get_edit(tmp_path, "prj_append01", "ed_append01")
    assert len(saved["captions"]["cues"]) == 2
