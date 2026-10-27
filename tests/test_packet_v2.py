"""Publish Packet v2: Edit, audio, music, layer assets and identity."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app
import artifacts
import audio
import color
import edits
import fx
import packet


def _mp4_bytes() -> bytes:
    if not shutil.which("ffmpeg"):
        return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 32
    with tempfile.TemporaryDirectory(prefix="vibecut-packet-v2-") as temporary:
        path = Path(temporary) / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", "color=c=red:s=320x180:d=1", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(path),
            ],
            check=True,
        )
        return path.read_bytes()


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(20, 120, 80)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _scenes() -> list[dict]:
    return [
        {"id": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "speech": "Hook."},
        {"id": 1, "start": 5.0, "end": 10.0, "dur": 5.0, "speech": "Payoff."},
    ]


def _plan() -> dict:
    return {
        "target": 10,
        "total": 10.0,
        "hook_scene": 0,
        "clip_count": 2,
        "clips": [
            {"scene": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "role": "hook"},
            {"scene": 1, "start": 5.0, "end": 10.0, "dur": 5.0, "role": "payoff"},
        ],
    }


def _job(tmp_path: Path) -> tuple[dict, Path]:
    job_dir = tmp_path / "jobs" / "job1"
    (job_dir / "renders").mkdir(parents=True)
    (job_dir / "renders" / "reel_10.mp4").write_bytes(_mp4_bytes())
    (job_dir / "renders" / "reel_10.jpg").write_bytes(_jpeg_bytes())
    job = {
        "id": "job1",
        "status": "ready",
        "source": {
            "name": "JOYLO AV1.mp4",
            "duration": 10.0,
            "width": 320,
            "height": 180,
            "path": "",
        },
        "analysis": {"scenes": _scenes()},
        "story_edits": {},
        "renders": {},
    }
    return job, job_dir


def _edit_for(job: dict, job_dir: Path, bed_hash: str) -> dict:
    plan = _plan()
    edit = edits.build_edit(
        story_ref={
            "set_id": "cs_1",
            "story_id": "s1",
            "clip_hash": edits.clip_snapshot_hash(plan["clips"]),
            "duration": 10.0,
            "clip_count": 2,
        },
        aspect="9:16",
        motion=[{"kind": "punch_in", "start": 1.0, "end": 2.0}],
        color={"lut": color.lut_asset("golden_hour")},
        graphics=[fx.sticker("star", 2.0, 3.0)],
        audio={
            "mode": "dub",
            "duck_db": -18,
            "music": {"source": "library", "file_hash": bed_hash},
            "voice": {"engine": "say", "model": "say", "voice": "Tingting"},
            "translate": {"target": "zh", "mode": "smooth"},
        },
    )
    edits.save_edit(job_dir, edit)
    job["story_edits"] = {"cs_1:s1:9:16": edit["id"]}
    return edit


def _music_bed(job_dir: Path) -> dict:
    payload = b"RIFF....WAVEfmt fake bed bytes"
    digest_payload = __import__("hashlib").sha256(payload).hexdigest()
    bed = job_dir / "audio" / "music" / f"{digest_payload[:12]}-bed.wav"
    bed.parent.mkdir(parents=True, exist_ok=True)
    bed.write_bytes(payload)
    entry = {
        "schema": 1,
        "source": "library",
        "file": f"audio/music/{bed.name}",
        "file_hash": digest_payload,
        "licence": {"type": "own", "note": "test bed"},
        "provider": {},
        "brief": {"mood": "warm", "instrumental": True},
        "bpm": 96.0,
        "in": 0.0,
        "out": 10.0,
        "duration": 10.0,
        "locked": True,
    }
    (job_dir / "audio" / "music.json").write_text(json.dumps(entry), encoding="utf-8")
    return entry


def _artifact(job: dict, job_dir: Path, edit: dict, transcript_id: str = "tr_1_abcd") -> dict:
    plan = _plan()
    spec = artifacts.build_spec(
        job,
        plan,
        story_id="s1",
        edit_hash=edit["hash"],
        transcript_id=transcript_id,
        audio_plan=audio.plan_from_edit(edit["audio"]),
    )
    manifest = artifacts.make_manifest("job1", spec, status="ready", record_key="10")
    manifest["set_id"] = "cs_1"
    artifacts.assign_version(job_dir, manifest)
    manifest = artifacts.save_manifest(job_dir, manifest)
    artifact_id = manifest["artifact_id"]
    artifacts.store_media(
        job_dir,
        artifact_id,
        job_dir / "renders" / "reel_10.mp4",
        job_dir / "renders" / "reel_10.jpg",
    )
    artifacts.write_captions(
        job_dir,
        artifact_id,
        "1\n00:00:00,000 --> 00:00:02,000\nA cue\n",
        "WEBVTT\n\n00:00.000 --> 00:02.000\nA cue\n",
    )
    job["renders"]["10"] = {
        "status": "ready",
        "path": f"artifacts/{artifact_id}/reel.mp4",
        "poster": f"artifacts/{artifact_id}/poster.jpg",
        "artifact_id": artifact_id,
        "target": 10,
        "duration": 10.0,
        "aspect": "9:16",
        "quality": "final",
        "updated": 1.0,
    }
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return manifest


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    job, job_dir = _job(tmp_path)
    bed = _music_bed(job_dir)
    edit = _edit_for(job, job_dir, bed["file_hash"])
    manifest = _artifact(job, job_dir, edit)
    monkeypatch.setattr(packet, "_frame_cover", lambda *args, **kwargs: _jpeg_bytes())
    return job, job_dir, edit, manifest, bed


def _request(artifact_id: str) -> packet.PacketRequest:
    return packet.PacketRequest(
        story_id="s1",
        artifact_ids=[artifact_id],
        titles=["One", "Two", "Three"],
        description="A complete packet.",
        hashtags=["#a", "#b", "#c"],
        cover_times=[1.0, 5.0],
    )


def test_packet_v2_writes_edit_audio_music_and_layer_assets(fixture, tmp_path):
    job, job_dir, edit, artifact, bed = fixture

    manifest = packet.build_packet(job, job_dir, _request(artifact["artifact_id"]))

    assert manifest["schema"] == packet.SCHEMA == "vibecut.publish_packet/2"
    assert manifest["identity"]["edit"]["hash"] == edit["hash"]
    assert manifest["identity"]["transcript_id"] == "tr_1_abcd"
    assert manifest["identity"]["music_hash"] == bed["file_hash"]

    assert manifest["edit"]["file"] == "edit.json"
    assert manifest["edit"]["version"] == 1
    assert manifest["audio"]["file"] == "audio.json"
    assert manifest["audio"]["mode"] == "dub"
    assert manifest["music"]["file"] == "music.json"
    assert manifest["music"]["file_hash"] == bed["file_hash"]

    root = job_dir / "packets" / manifest["packet_id"]
    edit_doc = json.loads((root / "edit.json").read_text(encoding="utf-8"))
    assert edit_doc["id"] == edit["id"]
    assert edit_doc["audio"]["translate"] == {"target": "zh", "mode": "smooth"}
    assert edit_doc["color"]["lut"]["path"].startswith("assets/lut/")
    for name in ("edit.json", "audio.json", "music.json"):
        assert str(tmp_path) not in (root / name).read_text(encoding="utf-8")
    audio_doc = json.loads((root / "audio.json").read_text(encoding="utf-8"))
    assert audio_doc["translate"] == {"target": "zh", "mode": "smooth"}
    assert audio_doc["provenance"] == {
        "engine": "say", "model": "say", "voice_id": "Tingting", "ai_voice": True,
    }
    music_doc = json.loads((root / "music.json").read_text(encoding="utf-8"))
    assert music_doc["file_hash"] == bed["file_hash"]
    assert music_doc["licence"]["type"] == "own"
    assert music_doc["bpm"] == 96.0

    kinds = {row["kind"] for row in manifest["layer_assets"]}
    assert kinds == {"lut", "sticker"}
    for row in manifest["layer_assets"]:
        path = root / row["file"]
        assert path.is_file()
        assert __import__("hashlib").sha256(path.read_bytes()).hexdigest() == row["sha256"]

    assert [cover["source"] for cover in manifest["covers"]] == ["frame", "frame"]
    assert manifest["media"][0]["identity"]["edit"]["id"] == edit["id"]
    assert manifest["media"][0]["audio"]["hash"] == audio_doc["hash"]
    assert manifest["media"][0]["music"]["file_hash"] == bed["file_hash"]

    with __import__("zipfile").ZipFile(
        packet.packet_zip_path(job_dir, manifest["packet_id"]),
    ) as archive:
        names = set(archive.namelist())
    assert {"edit.json", "audio.json", "music.json"} <= names
    assert any(name.startswith("assets/lut/") for name in names)
    assert any(name.startswith("assets/sticker/") for name in names)

    again = packet.build_packet(job, job_dir, _request(artifact["artifact_id"]))
    assert again["packet_id"] == manifest["packet_id"]
    assert str(tmp_path) not in json.dumps(manifest)


def test_packet_hash_covers_edit_transcript_audio_and_music(tmp_path):
    job, job_dir = _job(tmp_path)
    bed = _music_bed(job_dir)
    edit = _edit_for(job, job_dir, bed["file_hash"])
    artifact = _artifact(job, job_dir, edit)
    base = packet.build_packet(job, job_dir, _request(artifact["artifact_id"]))

    changed_edit = edits.build_edit(
        story_ref=edit["story_ref"],
        aspect="9:16",
        motion=edit["motion"],
        color=edit["color"],
        graphics=edit["graphics"],
        audio={**edit["audio"], "translate": {"target": "vi", "mode": "smooth"}},
        version=2,
        parent=edit["id"],
    )
    edits.save_edit(job_dir, changed_edit)
    job["story_edits"] = {"cs_1:s1:9:16": changed_edit["id"]}
    changed_artifact = _artifact(job, job_dir, changed_edit)
    assert changed_artifact["artifact_id"] != artifact["artifact_id"]
    changed = packet.build_packet(
        job, job_dir, _request(changed_artifact["artifact_id"]),
    )
    assert changed["packet_id"] != base["packet_id"]
    assert changed["identity"]["edit"]["hash"] != base["identity"]["edit"]["hash"]
    assert changed["identity"]["audio_hash"] != base["identity"]["audio_hash"]


def test_packet_route_builds_and_records_refs(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    job, source_dir = _job(tmp_path)
    job_dir = jobs / "job1"
    shutil.move(str(source_dir), str(job_dir))
    bed = _music_bed(job_dir)
    edit = _edit_for(job, job_dir, bed["file_hash"])
    artifact = _artifact(job, job_dir, edit)
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(packet, "_frame_cover", lambda *args, **kwargs: _jpeg_bytes())
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SHARES", data / "shares.json")
    client = TestClient(app.app)
    body = {
        "story_id": "s1",
        "titles": ["One", "Two", "Three"],
        "description": "Route packet.",
        "hashtags": ["#a", "#b", "#c"],
        "cover_times": [1.0, 5.0],
    }

    response = client.post(
        f"/api/jobs/job1/artifacts/{artifact['artifact_id']}/packet", json=body,
    )
    assert response.status_code == 200, response.text
    manifest = response.json()
    assert manifest["edit"]["id"] == edit["id"]
    job = app.load_job("job1")
    assert manifest["packet_id"] in job["packet_refs"]

    wrong = client.post(
        f"/api/jobs/job1/artifacts/{artifact['artifact_id']}/packet",
        json={**body, "artifact_ids": ["art_" + "0" * 24]},
    )
    assert wrong.status_code == 400

    missing = client.post("/api/jobs/job1/artifacts/art_" + "0" * 24 + "/packet", json=body)
    assert missing.status_code == 404


def test_packet_without_a_bed_has_no_music_document(tmp_path, monkeypatch):
    job, job_dir = _job(tmp_path)
    plan = _plan()
    edit = edits.build_edit(
        story_ref={
            "set_id": "cs_1",
            "story_id": "s1",
            "clip_hash": edits.clip_snapshot_hash(plan["clips"]),
            "duration": 10.0,
            "clip_count": 2,
        },
        aspect="9:16",
        audio={"mode": "original"},
    )
    edits.save_edit(job_dir, edit)
    job["story_edits"] = {"cs_1:s1:9:16": edit["id"]}
    artifact = _artifact(job, job_dir, edit)
    monkeypatch.setattr(packet, "_frame_cover", lambda *args, **kwargs: _jpeg_bytes())

    manifest = packet.build_packet(job, job_dir, _request(artifact["artifact_id"]))

    assert manifest["music"] is None
    assert manifest["audio"]["mode"] == "original"
    assert manifest["identity"]["music_hash"] == ""
    assert not (job_dir / "packets" / manifest["packet_id"] / "music.json").exists()
