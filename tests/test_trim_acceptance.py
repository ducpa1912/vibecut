"""Round 2 trim acceptance tests against the frozen atomic contract.

The file skips on branches without the T1/T2 modules and runs on merged main.
Every request goes through the public routes; the only direct calls are pure
mapping helpers and the caption-track predicate T2 owns.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("routes_trim")
pytest.importorskip("caption_reflow")

import app  # noqa: E402
import artifacts  # noqa: E402
import caption_reflow  # noqa: E402
import captions as caption_engine  # noqa: E402
import compose_render  # noqa: E402
import edits  # noqa: E402
import exports  # noqa: E402
import packet  # noqa: E402
import render  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "trim_job"
if str(FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURE_DIR))
import trim_fixture  # noqa: E402


# ---------------------------------------------------------------- fixture


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setenv("VIBECUT_EXPERIMENTAL", "1")
    return TestClient(app.app)


@pytest.fixture
def quiet_submit(monkeypatch):
    submitted: list[tuple] = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    return submitted


def setup_job(client: TestClient) -> dict:
    directory = trim_fixture.write_ready_job(app.JOBS)
    assert directory.is_dir()
    created = client.post("/api/jobs/j1/clip-sets", json={"count": 3})
    assert created.status_code == 200, created.text
    record = created.json()["clip_set"]

    patches = [
        {"id": story["id"], "sentences": list(range(start, end))}
        for story, (start, end) in zip(record["stories"], trim_fixture.STORY_RANGES)
    ]
    patched = client.patch(
        f"/api/jobs/j1/clip-sets/{record['id']}",
        json={"stories": patches},
    )
    assert patched.status_code == 200, patched.text
    record = patched.json()["clip_set"]
    story = next(
        item for item in record["stories"]
        if item["sentences"][0]["id"] == trim_fixture.TRIM_STORY_RANGE[0]
    )
    return {"set_id": record["id"], "story_id": story["id"], "record": record}


def layer(layer_id: str, start: float, end: float, text: str) -> dict:
    return {
        "id": layer_id,
        "type": "text",
        "kind": "lower_third",
        "text": text,
        "start": start,
        "end": end,
    }


def make_edits(client: TestClient, ids: dict) -> dict:
    layers = [
        layer("prefix", 0.6, 2.6, "Prefix hook"),
        layer("moved", 9.0, 11.0, "Moved lower third"),
        layer("clipped", 6.5, 9.5, "Crossing lower third"),
        layer("tail", 20.5, 22.0, "Tail call to action"),
    ]
    edits_by_aspect = {}
    for aspect in ("9:16", "4:5"):
        response = client.post("/api/jobs/j1/edits", json={
            "set_id": ids["set_id"],
            "story_id": ids["story_id"],
            "aspect": aspect,
            "graphics": layers,
        })
        assert response.status_code == 200, response.text
        edits_by_aspect[aspect] = response.json()["edit"]
    return edits_by_aspect


def clip_sets(job: dict) -> list[dict]:
    value = job.get("clip_sets") or []
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)]


def current_story(ids: dict) -> dict:
    job = app.load_job("j1")
    record = next(item for item in clip_sets(job) if item["id"] == ids["set_id"])
    return next(
        item for item in record["stories"] if item["id"] == ids["story_id"]
    )


def trim_url(ids: dict) -> str:
    return (
        f"/api/jobs/j1/clip-sets/{ids['set_id']}"
        f"/stories/{ids['story_id']}"
    )


def get_trim(client: TestClient, ids: dict) -> dict:
    response = client.get(f"{trim_url(ids)}/trim")
    assert response.status_code == 200, response.text
    return response.json()


def post_trim(client: TestClient, ids: dict, **body) -> object:
    return client.post(f"{trim_url(ids)}/trim", json=body)


def detail_code(response) -> str:
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("code") or body.get("code") or "")
    if isinstance(body, dict):
        return str(body.get("code") or "")
    return ""


def public_edit(result: dict, aspect: str = "9:16") -> dict:
    value = result["edits"][aspect]
    return value.get("edit", value) if isinstance(value, dict) else value


def graphic(edit: dict, layer_id: str) -> dict:
    return next(item for item in edit["graphics"] if item["id"] == layer_id)


def snapshot() -> dict:
    job_dir = app._job_dir("j1")
    job = app.load_job("j1")
    manifests = {}
    for manifest in artifacts.list_manifests(job_dir):
        path = job_dir / "artifacts" / manifest["artifact_id"] / "manifest.json"
        manifests[manifest["artifact_id"]] = path.read_bytes() if path.is_file() else b""
    return {
        "job": (job_dir / "job.json").read_bytes(),
        "pointers": json.loads(json.dumps(job.get("story_edits") or {})),
        "captions": json.loads(json.dumps(job.get("story_captions") or {})),
        "stories": json.loads(json.dumps(job.get("clip_sets") or [])),
        "manifests": manifests,
    }


def track_for(result: dict, aspect: str = "9:16") -> caption_engine.CaptionTrack:
    track_id = result["captions"]["track_id"]
    track = caption_engine.load_track(app._job_dir("j1"), track_id)
    assert track is not None
    return track


# ---------------------------------------------------------------- mapping


def _clip_start(clip: dict) -> float:
    return float(clip["start"])


def _clip_end(clip: dict) -> float:
    if clip.get("end") is not None:
        return float(clip["end"])
    return float(clip["start"]) + float(clip.get("dur") or clip.get("duration") or 0.0)


def source_at(clips: list[dict], output: float) -> float:
    cursor = 0.0
    for clip in clips:
        duration = _clip_end(clip) - _clip_start(clip)
        if output <= cursor + duration + 1e-9:
            return _clip_start(clip) + max(0.0, min(duration, output - cursor))
        cursor += duration
    return _clip_end(clips[-1])


def output_at(clips: list[dict], source: float) -> float | None:
    cursor = 0.0
    for clip in clips:
        start, end = _clip_start(clip), _clip_end(clip)
        if start - 1e-9 <= source <= end + 1e-9:
            return cursor + max(0.0, min(end - start, source - start))
        cursor += end - start
    return None


def shifted(clips: list[dict], old_clips: list[dict], time: float) -> float:
    value = output_at(clips, source_at(old_clips, time))
    assert value is not None
    return value


# ---------------------------------------------------------------- start / end


def test_start_trim_later_shifts_layers_and_hides_the_prefix(client):
    ids = setup_job(client)
    make_edits(client, ids)
    old = current_story(ids)
    before_revision = get_trim(client, ids)["revision"]

    response = post_trim(
        client, ids,
        expected_revision=before_revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code == 200, response.text
    result = response.json()

    new = current_story(ids)
    assert result["story"]["id"] == old["id"]
    assert new["start"] == 16 * trim_fixture.SCENE_SECONDS
    assert new["end"] == 20 * trim_fixture.SCENE_SECONDS
    assert result["duration"] == pytest.approx(new["dur"], abs=0.05)
    assert result["revision"] == before_revision + 1
    assert result["clip_hash"] == edits.clip_snapshot_hash(new["clips"])

    current = public_edit(result)
    prefix = graphic(current, "prefix")
    assert prefix["hidden"] is True
    assert prefix["start"] == pytest.approx(0.6, abs=0.05)
    assert prefix["end"] == pytest.approx(2.6, abs=0.05)

    moved = graphic(current, "moved")
    assert not moved.get("hidden")
    assert moved["start"] == pytest.approx(
        shifted(new["clips"], old["clips"], 9.0), abs=0.05,
    )
    assert moved["end"] == pytest.approx(
        shifted(new["clips"], old["clips"], 11.0), abs=0.05,
    )

    clipped = graphic(current, "clipped")
    assert clipped["start"] == pytest.approx(0.0, abs=0.05)
    assert clipped["end"] == pytest.approx(1.5, abs=0.05)

    receipt = result["receipt"]
    assert "moved" in receipt["layers"]["moved"]
    assert "clipped" in receipt["layers"]["clipped"]
    assert "prefix" in receipt["layers"]["outside"]
    assert result["revision"] > int(old.get("revision") or 0)


def test_start_trim_earlier_shifts_layers_forward(client):
    ids = setup_job(client)
    make_edits(client, ids)
    old = current_story(ids)
    revision = get_trim(client, ids)["revision"]

    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=12,
        end_sentence=19,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    new = current_story(ids)
    assert result["story"]["id"] == new["id"]
    assert new["start"] == 12 * trim_fixture.SCENE_SECONDS
    assert result["duration"] > old["dur"]

    current = public_edit(result)
    for layer_id, start, end in (
        ("prefix", 0.6, 2.6),
        ("moved", 9.0, 11.0),
        ("clipped", 6.5, 9.5),
    ):
        item = graphic(current, layer_id)
        assert not item.get("hidden"), layer_id
        assert item["start"] == pytest.approx(
            shifted(new["clips"], old["clips"], start), abs=0.05,
        ), layer_id
        assert item["end"] == pytest.approx(
            shifted(new["clips"], old["clips"], end), abs=0.05,
        ), layer_id


def test_end_trim_flags_layers_past_the_new_end(client):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]

    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=14,
        end_sentence=17,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    current = public_edit(result)

    tail = graphic(current, "tail")
    assert tail["hidden"] is True
    assert tail["start"] == pytest.approx(20.5, abs=0.05)
    assert "tail" in result["receipt"]["layers"]["outside"]
    assert not graphic(current, "moved").get("hidden")


# ---------------------------------------------------------------- captions


def test_caption_track_is_rebuilt_for_the_new_clips(client):
    ids = setup_job(client)
    make_edits(client, ids)
    old = current_story(ids)
    old_edit = edits.load_edit(
        app._job_dir("j1"),
        edits.pointer_edit_id(app.load_job("j1"), f"{ids['set_id']}:{ids['story_id']}:9:16"),
    )
    assert old_edit is not None
    old_track = caption_engine.load_track(
        app._job_dir("j1"), old_edit["captions"]["track_id"],
    )
    assert old_track is not None
    old_cue = next(cue for cue in old_track.cues if "17" in cue.text)
    revision = get_trim(client, ids)["revision"]

    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    new = current_story(ids)
    track = track_for(result)

    assert result["captions"]["track_id"] != old_track.id
    assert result["captions"]["clip_hash"] == result["clip_hash"]
    assert track.clip_hash == result["clip_hash"]
    assert track.id != old_track.id
    assert result["receipt"]["captions"]["kept"] >= 1
    assert result["receipt"]["captions"]["dropped"] >= 1

    expected = shifted(new["clips"], old["clips"], old_cue.start)
    kept = next(cue for cue in track.cues if "17" in cue.text)
    assert kept.start == pytest.approx(expected, abs=0.35)
    assert kept.start >= 0.0
    assert kept.end <= result["duration"] + 0.05


def test_cached_caption_track_is_rejected_after_a_clip_change(client):
    ids = setup_job(client)
    make_edits(client, ids)
    job = app.load_job("j1")
    key = f"{ids['set_id']}:{ids['story_id']}:9:16"
    edit = edits.load_edit(app._job_dir("j1"), edits.pointer_edit_id(job, key))
    assert edit is not None
    old_track_id = edit["captions"]["track_id"]

    raw = json.loads((app._job_dir("j1") / "job.json").read_text())
    record = next(
        item for item in clip_sets(raw) if item["id"] == ids["set_id"]
    )
    story = next(item for item in record["stories"] if item["id"] == ids["story_id"])
    story["clips"][0]["start"] += 0.5
    story["clips"][0]["dur"] -= 0.5
    (app._job_dir("j1") / "job.json").write_text(json.dumps(raw))

    track = app.default_story_caption_track("j1", ids["set_id"], ids["story_id"])
    assert track is None or track.id != old_track_id
    if track is not None:
        assert track.clip_hash != edit["story_ref"]["clip_hash"]


def test_manual_caption_fix_survives_the_trim(client):
    ids = setup_job(client)
    make_edits(client, ids)
    job = app.load_job("j1")
    key = f"{ids['set_id']}:{ids['story_id']}:9:16"
    edit = edits.load_edit(app._job_dir("j1"), edits.pointer_edit_id(job, key))
    assert edit is not None
    track = caption_engine.load_track(
        app._job_dir("j1"), edit["captions"]["track_id"],
    )
    assert track is not None
    cues = [cue.to_dict() for cue in track.cues]
    target = next(cue for cue in cues if "17" in cue["text"])
    target["text"] = "Manual name fix"
    edited = client.patch(
        f"/api/jobs/j1/captions/{track.id}", json={"cues": cues},
    )
    assert edited.status_code == 200, edited.text
    fixed_track_id = edited.json()["track_id"]
    revision = get_trim(client, ids)["revision"]

    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["captions"]["track_id"] != fixed_track_id
    new_track = track_for(result)
    assert any("Manual name fix" in cue.text for cue in new_track.cues)
    assert result["receipt"]["captions"]["manual_kept"] >= 1


# ---------------------------------------------------------------- one lineage


def _queue_after_trim(client, ids):
    revision = get_trim(client, ids)["revision"]
    trimmed = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert trimmed.status_code == 200, trimmed.text
    return trimmed.json()


def test_burn_and_srt_read_the_one_trimmed_track(client, quiet_submit):
    ids = setup_job(client)
    make_edits(client, ids)
    result = _queue_after_trim(client, ids)
    track = track_for(result)
    job = app.load_job("j1")
    story = current_story(ids)
    record = next(
        item for item in clip_sets(job) if item["id"] == ids["set_id"]
    )
    plan = app._story_plan(job, record, story, ids["set_id"])
    prepared = render.prepare_render(plan, job["source"], None)
    edit = public_edit(result)

    compiled = compose_render.compile_edit(
        edit,
        clips=prepared["clips"],
        source=job["source"],
        scenes=job["analysis"]["scenes"],
        caption_track=track.to_dict(),
        size=(360, 640),
    )
    burned = [item for item in compiled["overlays"] if item["type"] == "caption"]
    assert len(burned) == len(track.cues)
    for cue, overlay in zip(track.cues, burned):
        assert overlay["start"] == pytest.approx(cue.start, abs=0.001)
        assert overlay["end"] == pytest.approx(cue.end, abs=0.001)
        assert " ".join(overlay["text"].split()) == " ".join(cue.text.split())

    srt = client.get(f"/api/jobs/j1/captions/{track.id}/srt")
    assert srt.status_code == 200, srt.text
    parsed = caption_engine.parse_srt(srt.text)
    assert len(parsed) == len(track.cues)
    for cue, row in zip(track.cues, parsed):
        assert row["start"] == pytest.approx(cue.start, abs=0.001)
        assert row["end"] == pytest.approx(cue.end, abs=0.001)
        assert " ".join(row["text"].split()) == " ".join(cue.text.split())

    render_response = client.post(
        f"/api/jobs/j1/clip-sets/{ids['set_id']}"
        f"/stories/{ids['story_id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert render_response.status_code == 200, render_response.text
    body = render_response.json()
    assert body["edit_id"] == edit["id"]
    assert body["edit_hash"] == edit["hash"]
    assert body["caption_track_id"] == track.id
    queued = quiet_submit[-1][1]["edit"]
    assert queued["id"] == edit["id"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is needed for a readable packet")
def test_packet_carries_the_trimmed_cues(client, quiet_submit, tmp_path, monkeypatch):
    ids = setup_job(client)
    make_edits(client, ids)
    result = _queue_after_trim(client, ids)
    track = track_for(result)
    edit = public_edit(result)

    rendered = client.post(
        f"/api/jobs/j1/clip-sets/{ids['set_id']}"
        f"/stories/{ids['story_id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert rendered.status_code == 200, rendered.text
    body = rendered.json()
    artifact_id = body["artifact_id"]
    job_dir = app._job_dir("j1")
    manifest = artifacts.load_manifest(job_dir, artifact_id)
    assert manifest is not None

    reel = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=red:s=320x180:d=1", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(reel),
        ],
        check=True,
    )
    artifacts.store_media(job_dir, artifact_id, reel, None)
    cue_rows = [cue.to_dict() for cue in track.cues]
    artifacts.write_captions(
        job_dir, artifact_id, exports.srt(cue_rows), exports.vtt(cue_rows),
    )
    manifest["status"] = "ready"
    artifacts.save_manifest(job_dir, manifest)

    job = app.load_job("j1")
    record_key = body["render"]["record_key"]
    job["renders"][record_key] = {
        "status": "ready",
        "artifact_id": artifact_id,
        "path": f"artifacts/{artifact_id}/reel.mp4",
        "target": int(result["duration"]),
        "duration": float(result["duration"]),
        "aspect": "9:16",
        "quality": "final",
        "captions": True,
        "edit_id": edit["id"],
        "edit_hash": edit["hash"],
        "updated": 1.0,
    }
    app.save_job(job)

    def jpeg() -> bytes:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (32, 32), (20, 120, 80)).save(buffer, format="JPEG")
        return buffer.getvalue()

    monkeypatch.setattr(packet, "_frame_cover", lambda *args, **kwargs: jpeg())
    request = packet.PacketRequest(
        story_id=ids["story_id"],
        artifact_ids=[artifact_id],
        titles=["One", "Two", "Three"],
        description="Trim packet.",
        hashtags=["#trim", "#packet", "#test"],
    )
    built = packet.build_packet(app.load_job("j1"), job_dir, request)
    packet_dir = job_dir / "packets" / built["packet_id"]
    srt_files = sorted(packet_dir.rglob("*.srt"))
    assert srt_files, "packet has no SRT"
    parsed = caption_engine.parse_srt(srt_files[0].read_text())
    assert len(parsed) == len(track.cues)
    for cue, row in zip(track.cues, parsed):
        assert row["start"] == pytest.approx(cue.start, abs=0.001)
        assert row["end"] == pytest.approx(cue.end, abs=0.001)
        assert " ".join(row["text"].split()) == " ".join(cue.text.split())


# ---------------------------------------------------------------- atomicity


def test_caption_rebuild_failure_writes_nothing(client, monkeypatch):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]
    before = snapshot()

    def boom(*args, **kwargs):
        raise caption_reflow.ReflowError("forced caption failure")

    monkeypatch.setattr(caption_reflow, "rebuild_for_story", boom)
    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code == 409, response.text
    assert detail_code(response) == "caption_rebuild_failed"
    assert snapshot() == before


def test_edit_build_failure_writes_nothing(client, monkeypatch):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]
    before = snapshot()

    def boom(*args, **kwargs):
        raise edits.EditError("forced Edit failure")

    monkeypatch.setattr(edits, "build_edit", boom)
    import routes_trim

    if hasattr(routes_trim, "build_edit"):
        monkeypatch.setattr(routes_trim, "build_edit", boom)
    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code >= 400
    assert snapshot() == before


def test_commit_failure_writes_nothing(client, monkeypatch):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]
    before = snapshot()

    def boom(*args, **kwargs):
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(app, "update_job", boom)
    import routes_trim

    if hasattr(routes_trim, "update_job"):
        monkeypatch.setattr(routes_trim, "update_job", boom)
    unsafe = TestClient(app.app, raise_server_exceptions=False)
    response = unsafe.post(
        f"{trim_url(ids)}/trim",
        json={
            "expected_revision": revision,
            "start_sentence": 16,
            "end_sentence": 19,
        },
    )
    assert response.status_code >= 400
    assert snapshot() == before


def test_dry_run_reports_the_result_without_writing(client):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]
    before = snapshot()

    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
        dry_run=True,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["story"]["start"] == 16 * trim_fixture.SCENE_SECONDS
    assert result["duration"] == pytest.approx(16.0, abs=0.05)
    assert snapshot() == before


# ---------------------------------------------------------------- races


def test_stale_revision_returns_409_with_the_current_payload(client):
    ids = setup_job(client)
    make_edits(client, ids)
    current = get_trim(client, ids)
    before = snapshot()

    response = post_trim(
        client, ids,
        expected_revision=int(current["revision"]) - 1,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code == 409, response.text
    assert detail_code(response) == "revision_mismatch"
    detail = response.json()["detail"]
    assert detail["current"]["revision"] == current["revision"]
    assert snapshot() == before


def test_two_trims_make_the_old_revision_stale(client):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]
    first = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=15,
        end_sentence=19,
    )
    assert first.status_code == 200, first.text
    after_first = snapshot()

    second = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert second.status_code == 409, second.text
    assert detail_code(second) == "revision_mismatch"
    assert snapshot() == after_first

    retry = post_trim(
        client, ids,
        expected_revision=first.json()["revision"],
        start_sentence=16,
        end_sentence=19,
    )
    assert retry.status_code == 200, retry.text
    assert current_story(ids)["start"] == 16 * trim_fixture.SCENE_SECONDS


def test_stories_patch_then_edit_save_is_409_and_render_fails_closed(
    client, quiet_submit,
):
    ids = setup_job(client)
    created = make_edits(client, ids)
    current = get_trim(client, ids)
    revision = int(current["revision"])
    story = current_story(ids)
    kept = [item["id"] for item in story["sentences"][1:]]

    stale_patch = client.patch(
        f"/api/jobs/j1/clip-sets/{ids['set_id']}",
        json={
            "stories": [{"id": ids["story_id"], "sentences": kept}],
            "expected_revision": revision - 1,
        },
    )
    assert stale_patch.status_code == 409, stale_patch.text
    assert detail_code(stale_patch) == "revision_mismatch"

    patched = client.patch(
        f"/api/jobs/j1/clip-sets/{ids['set_id']}",
        json={
            "stories": [{"id": ids["story_id"], "sentences": kept}],
            "expected_revision": revision,
        },
    )
    assert patched.status_code == 200, patched.text
    after = get_trim(client, ids)
    assert after["revision"] != revision
    assert after["aspects"]["9:16"]["stale"] is True

    save = client.patch(
        f"/api/jobs/j1/edits/{created['9:16']['id']}",
        json={"graphics": created["9:16"]["graphics"]},
    )
    assert save.status_code == 409, save.text

    rendered = client.post(
        f"/api/jobs/j1/clip-sets/{ids['set_id']}"
        f"/stories/{ids['story_id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert rendered.status_code == 409, rendered.text
    assert detail_code(rendered) == "edit_stale"
    assert quiet_submit == []


def test_rebind_repairs_every_stale_aspect(client):
    ids = setup_job(client)
    created = make_edits(client, ids)
    raw = json.loads((app._job_dir("j1") / "job.json").read_text())
    record = next(
        item for item in clip_sets(raw) if item["id"] == ids["set_id"]
    )
    story = next(item for item in record["stories"] if item["id"] == ids["story_id"])
    story["clips"][0]["start"] += 0.5
    story["clips"][0]["dur"] -= 0.5
    (app._job_dir("j1") / "job.json").write_text(json.dumps(raw))
    current = get_trim(client, ids)
    assert current["aspects"]["9:16"]["stale"] is True
    assert current["aspects"]["4:5"]["stale"] is True

    repaired = client.post(f"{trim_url(ids)}/rebind", json={
        "expected_revision": current["revision"],
    })
    assert repaired.status_code == 200, repaired.text
    result = repaired.json()
    assert result["story"]["id"] == ids["story_id"]
    for aspect in ("9:16", "4:5"):
        fresh = public_edit(result, aspect)
        assert fresh["id"] != created[aspect]["id"]
        assert fresh["story_ref"]["clip_hash"] == result["clip_hash"]
    after = get_trim(client, ids)
    assert after["aspects"]["9:16"]["stale"] is False
    assert after["aspects"]["4:5"]["stale"] is False


def test_finish_fails_closed_on_an_unreadable_edit(client, quiet_submit):
    ids = setup_job(client)
    created = make_edits(client, ids)
    edit_id = created["9:16"]["id"]
    path = edits.edit_path(app._job_dir("j1"), edit_id)
    assert path.is_file()
    path.unlink()

    rendered = client.post(
        f"/api/jobs/j1/clip-sets/{ids['set_id']}"
        f"/stories/{ids['story_id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert rendered.status_code == 409, rendered.text
    assert detail_code(rendered) == "edit_stale"
    assert quiet_submit == []


# ---------------------------------------------------------------- aspects + undo


def test_multi_aspect_rebind_keeps_the_old_artifact_immutable(
    client, quiet_submit,
):
    ids = setup_job(client)
    created = make_edits(client, ids)
    job = app.load_job("j1")
    story = current_story(ids)
    record = next(
        item for item in clip_sets(job) if item["id"] == ids["set_id"]
    )
    plan = app._story_plan(job, record, story, ids["set_id"])
    spec = artifacts.build_spec(
        job,
        plan,
        story_id=ids["story_id"],
        edit_hash=created["9:16"]["hash"],
        captions=True,
        cues=[cue.to_dict() for cue in caption_engine.load_track(
            app._job_dir("j1"), created["9:16"]["captions"]["track_id"],
        ).cues],
    )
    manifest = artifacts.make_manifest("j1", spec, status="ready", record_key="old")
    artifacts.assign_version(app._job_dir("j1"), manifest)
    manifest = artifacts.save_manifest(app._job_dir("j1"), manifest)
    artifact_id = manifest["artifact_id"]
    manifest_path = (
        app._job_dir("j1") / "artifacts" / artifact_id / "manifest.json"
    )
    manifest_before = manifest_path.read_bytes()
    app.update_job("j1", lambda value: value["renders"].update({
        "old:9x16:cap": {
            "status": "ready",
            "artifact_id": artifact_id,
            "target": int(story["dur"]),
            "duration": float(story["dur"]),
            "aspect": "9:16",
            "quality": "final",
            "captions": True,
            "edit_id": created["9:16"]["id"],
            "edit_hash": created["9:16"]["hash"],
            "updated": 1.0,
        },
    }))

    revision = get_trim(client, ids)["revision"]
    response = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["clip_hash"] == edits.clip_snapshot_hash(
        current_story(ids)["clips"]
    )
    for aspect in ("9:16", "4:5"):
        fresh = public_edit(result, aspect)
        assert fresh["id"] != created[aspect]["id"]
        assert fresh["story_ref"]["clip_hash"] == result["clip_hash"]
    assert get_trim(client, ids)["aspects"]["9:16"]["stale"] is False
    assert get_trim(client, ids)["aspects"]["4:5"]["stale"] is False
    assert manifest_path.read_bytes() == manifest_before
    assert artifact_id in result["invalidated_artifacts"]

    for aspect in ("9:16", "4:5"):
        rendered = client.post(
            f"/api/jobs/j1/clip-sets/{ids['set_id']}"
            f"/stories/{ids['story_id']}/render",
            json={"quality": "final", "aspect": aspect},
        )
        assert rendered.status_code == 200, rendered.text
        body = rendered.json()
        assert body["edit_id"] == public_edit(result, aspect)["id"]
        assert body["edit_hash"] == public_edit(result, aspect)["hash"]


def test_undo_restores_range_layers_captions_and_a_new_version(client):
    ids = setup_job(client)
    created = make_edits(client, ids)
    old = current_story(ids)
    old_edit = edits.load_edit(app._job_dir("j1"), created["9:16"]["id"])
    assert old_edit is not None
    old_track_id = old_edit["captions"]["track_id"]
    revision = get_trim(client, ids)["revision"]

    trimmed = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert trimmed.status_code == 200, trimmed.text
    trimmed_result = trimmed.json()
    trim_receipt = app._job_dir("j1") / "trims" / f"{trimmed_result['receipt']['id']}.json"
    assert trim_receipt.is_file()

    undone = client.post(f"{trim_url(ids)}/trim/undo", json={
        "undo_token": trimmed_result["undo_token"],
        "expected_revision": trimmed_result["revision"],
    })
    assert undone.status_code == 200, undone.text
    result = undone.json()
    restored = current_story(ids)

    assert restored["start"] == pytest.approx(old["start"], abs=0.01)
    assert restored["end"] == pytest.approx(old["end"], abs=0.01)
    assert [item["id"] for item in restored["sentences"]] == [
        item["id"] for item in old["sentences"]
    ]
    assert result["revision"] == trimmed_result["revision"] + 1
    assert result["captions"]["track_id"] == old_track_id
    assert result["clip_hash"] == edits.clip_snapshot_hash(restored["clips"])
    assert result["captions"]["clip_hash"] == result["clip_hash"]
    assert result["undo_token"] != trimmed_result["undo_token"]
    undo_receipt = app._job_dir("j1") / "trims" / f"{result['receipt']['id']}.json"
    assert undo_receipt.is_file()

    fresh = public_edit(result)
    assert fresh["id"] != old_edit["id"]
    assert fresh["version"] > old_edit["version"]
    for layer_id in ("prefix", "moved", "clipped", "tail"):
        was = graphic(old_edit, layer_id)
        now = graphic(fresh, layer_id)
        assert now["start"] == pytest.approx(was["start"], abs=0.01), layer_id
        assert now["end"] == pytest.approx(was["end"], abs=0.01), layer_id
        assert not now.get("hidden"), layer_id


def test_undo_after_a_later_trim_is_409(client):
    ids = setup_job(client)
    make_edits(client, ids)
    revision = get_trim(client, ids)["revision"]
    first = post_trim(
        client, ids,
        expected_revision=revision,
        start_sentence=15,
        end_sentence=19,
    )
    assert first.status_code == 200, first.text
    token = first.json()["undo_token"]
    first_revision = first.json()["revision"]

    second = post_trim(
        client, ids,
        expected_revision=first_revision,
        start_sentence=16,
        end_sentence=19,
    )
    assert second.status_code == 200, second.text
    before = snapshot()

    late = client.post(f"{trim_url(ids)}/trim/undo", json={
        "undo_token": token,
        "expected_revision": first_revision,
    })
    assert late.status_code == 409, late.text
    assert detail_code(late) in {"revision_mismatch", "undo_stale"}
    assert snapshot() == before
