"""Publish Packet completeness, safety, idempotency, and API delivery."""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import packet


def _scenes() -> list[dict]:
    return [
        {
            "id": 0, "start": 0.0, "end": 5.0, "dur": 5.0,
            "speech": "This is the hook. It has a promise.",
        },
        {
            "id": 1, "start": 5.0, "end": 10.0, "dur": 5.0,
            "speech": "This is the payoff. It lands.",
        },
    ]


def _plan() -> dict:
    return {
        "target": 30,
        "total": 10.0,
        "hook_scene": 0,
        "clip_count": 2,
        "clips": [
            {"scene": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "role": "hook"},
            {"scene": 1, "start": 5.0, "end": 10.0, "dur": 5.0, "role": "payoff"},
        ],
    }


def _job(root: Path, job_id: str = "job1") -> tuple[dict, Path]:
    job_dir = root / "jobs" / job_id
    renders = job_dir / "renders"
    renders.mkdir(parents=True)
    (renders / "reel_30.mp4").write_bytes(b"fake-mp4-payload" * 8)
    (renders / "reel_30.jpg").write_bytes(b"fake-jpeg")
    job = {
        "id": job_id,
        "status": "ready",
        "source": {"name": "Café 日本語 source.mp4", "duration": 60.0},
        "analysis": {"scenes": _scenes()},
        "renders": {
            "30": {
                "status": "ready",
                "path": "reel_30.mp4",
                "poster": "reel_30.jpg",
                "target": 30,
                "duration": 10.0,
                "aspect": "9:16",
                "quality": "final",
                "plan": _plan(),
                "updated": 1.0,
            },
        },
    }
    return job, job_dir


def _request(**overrides) -> packet.PacketRequest:
    values = {
        "story_id": "story one",
        "titles": ["Three things", "The promise", "The payoff"],
        "description": "A short hook that earns the click.",
        "hashtags": ["#one", "two", "#three"],
        "render_keys": ["30"],
        "cover_times": [1.0, 5.0],
    }
    values.update(overrides)
    return packet.PacketRequest(**values)


def test_packet_completeness_and_sidecar_schema(tmp_path):
    job, job_dir = _job(tmp_path)

    manifest = packet.build_packet(job, job_dir, _request())

    assert manifest["schema"] == packet.SCHEMA
    assert len(manifest["packet_id"]) == 24
    assert len(manifest["titles"]) == 3
    assert manifest["description"] == "A short hook that earns the click."
    assert len(manifest["description"]) <= packet.DESCRIPTION_LIMIT
    assert packet.HASHTAG_MIN <= len(manifest["hashtags"]) <= packet.HASHTAG_MAX
    assert len(manifest["media"]) == 1
    assert len(manifest["covers"]) == 2
    media = manifest["media"][0]
    assert media["artifact_id"] == "30"
    assert media["render_key"] == "30"
    assert media["captions_file"].endswith(".srt")
    assert media["captions_source"] == "plan"
    assert len(media["sha256"]) == 64
    for relative in [media["file"], media["captions_file"]] + [
        cover["file"] for cover in manifest["covers"]
    ]:
        assert not Path(relative).is_absolute()
        assert (job_dir / "packets" / manifest["packet_id"] / relative).is_file()
    assert manifest["zip_file"].endswith(".zip")
    sidecar = json.loads(
        (job_dir / "packets" / manifest["packet_id"] / "packet.json").read_text(
            encoding="utf-8"
        )
    )
    assert sidecar["packet_id"] == manifest["packet_id"]
    text = json.dumps(sidecar, ensure_ascii=False)
    assert str(tmp_path) not in text
    assert str(job_dir) not in text
    assert "renders/reel_30" not in text
    assert "fake-mp4" not in text


def test_packet_never_serializes_an_absolute_source_name(tmp_path):
    job, job_dir = _job(tmp_path)
    job["source"]["name"] = "/Users/someone/private/source.mp4"

    manifest = packet.build_packet(job, job_dir, _request())

    sidecar = (job_dir / "packets" / manifest["packet_id"] / "packet.json").read_text(
        encoding="utf-8"
    )
    assert manifest["source"]["name"] == "source.mp4"
    assert "/Users/someone/private" not in sidecar


def test_packet_filename_safety_and_unicode(tmp_path):
    job, job_dir = _job(tmp_path)
    unsafe = "../../日本語 Café: / Story *?"
    manifest = packet.build_packet(job, job_dir, _request(story_id=unsafe))

    packet_dir = job_dir / "packets" / manifest["packet_id"]
    for path in packet_dir.rglob("*"):
        if not path.is_file():
            continue
        assert path.name.isascii()
        assert " " not in path.name
        assert ".." not in path.name
        assert path.name == Path(path.name).name
    assert packet.safe_filename("../../Café 日本語!") == "cafe"
    assert packet.safe_filename("日本語") == "packet"
    assert packet.safe_filename("") == "packet"


def test_packet_is_idempotent(tmp_path):
    job, job_dir = _job(tmp_path)
    request = _request()

    first = packet.build_packet(job, job_dir, request)
    second = packet.build_packet(job, job_dir, request)

    assert second["packet_id"] == first["packet_id"]
    assert second["created"] == first["created"]
    packets = [path for path in (job_dir / "packets").iterdir() if path.is_dir()]
    assert len(packets) == 1
    first_zip = (job_dir / "packets" / first["packet_id"] / first["zip_file"]).read_bytes()
    third = packet.build_packet(job, job_dir, request)
    assert (job_dir / "packets" / third["packet_id"] / third["zip_file"]).read_bytes() == first_zip


def test_packet_zip_contents(tmp_path):
    job, job_dir = _job(tmp_path)
    manifest = packet.build_packet(job, job_dir, _request())
    zip_path = packet.packet_zip_path(job_dir, manifest["packet_id"])

    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(archive.namelist())
        assert "packet.json" in names
        assert any(name.startswith("media/") for name in names)
        assert any(name.startswith("captions/") for name in names)
        assert len([name for name in names if name.startswith("covers/")]) == 2
        assert not any(name.endswith(".zip") for name in names)
        assert not any(name.startswith("/") or ".." in Path(name).parts for name in names)
        zipped_packet = json.loads(archive.read("packet.json"))
        assert zipped_packet["packet_id"] == manifest["packet_id"]
        assert archive.testzip() is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_packet_extracts_covers_from_video_when_no_poster(tmp_path):
    job, job_dir = _job(tmp_path)
    video = job_dir / "renders" / "reel_30.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=red:s=320x180:d=1", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )
    (job_dir / "renders" / "reel_30.jpg").unlink()
    job["renders"]["30"].pop("poster")

    manifest = packet.build_packet(
        job, job_dir, _request(cover_times=[0.1, 0.7]),
    )

    assert [cover["source"] for cover in manifest["covers"]] == ["ffmpeg", "ffmpeg"]
    assert all(cover["bytes"] > 0 for cover in manifest["covers"])


def test_packet_builds_captions_from_analysis_when_record_has_no_plan(tmp_path):
    job, job_dir = _job(tmp_path)
    job["renders"]["30"].pop("plan")

    manifest = packet.build_packet(job, job_dir, _request())

    media = manifest["media"][0]
    assert media["captions_source"] == "plan"
    captions = (job_dir / "packets" / manifest["packet_id"] / media["captions_file"])
    assert "-->" in captions.read_text(encoding="utf-8")


def test_packet_blocks_queued_or_missing_artifact(tmp_path):
    job, job_dir = _job(tmp_path)
    job["renders"]["30"]["status"] = "queued"

    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(job, job_dir, _request())
    assert failed.value.code == "artifact_not_ready"
    assert not list(job_dir.rglob("*.zip"))
    packets = job_dir / "packets"
    assert not packets.exists() or not [path for path in packets.iterdir() if path.is_dir()]

    job, job_dir = _job(tmp_path / "missing")
    (job_dir / "renders" / "reel_30.mp4").unlink()
    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(job, job_dir, _request())
    assert failed.value.code == "artifact_missing"
    assert not list(job_dir.rglob("*.zip"))


def test_packet_blocks_stale_checksum(tmp_path):
    job, job_dir = _job(tmp_path)
    job["renders"]["30"]["sha256"] = "0" * 64

    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(job, job_dir, _request())
    assert failed.value.code == "artifact_stale"
    assert not list(job_dir.rglob("*.zip"))


def test_packet_validates_titles_description_and_hashtags(tmp_path):
    job, job_dir = _job(tmp_path)
    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(job, job_dir, _request(titles=["Only one"]))
    assert failed.value.code == "titles_invalid"
    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(job, job_dir, _request(description="x" * 126))
    assert failed.value.code == "description_too_long"
    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(job, job_dir, _request(hashtags=["#one"]))
    assert failed.value.code == "hashtags_invalid"


def test_packet_artifact_id_adapter_refuses_unknown_id(tmp_path):
    job, job_dir = _job(tmp_path)
    with pytest.raises(packet.PacketError) as failed:
        packet.build_packet(
            job, job_dir,
            _request(render_keys=[], artifact_ids=["trust-artifact-1"]),
        )
    assert failed.value.code == "artifact_missing"


def test_packet_accepts_trust_core_artifact_ids_without_new_identity(tmp_path):
    job, job_dir = _job(tmp_path)
    job["artifacts"] = {
        "trust-artifact-1": {
            "status": "ready",
            "path": "renders/reel_30.mp4",
            "poster": "reel_30.jpg",
            "target": 30,
            "duration": 10.0,
            "plan": _plan(),
        },
    }

    manifest = packet.build_packet(
        job, job_dir,
        _request(render_keys=[], artifact_ids=["trust-artifact-1"]),
    )

    assert len(manifest["media"]) == 1
    assert manifest["media"][0]["artifact_id"] == "trust-artifact-1"
    assert manifest["media"][0]["render_key"] is None
    assert manifest["media"][0]["captions_source"] == "plan"


@pytest.fixture
def api(tmp_path, monkeypatch):
    data = tmp_path / "api-data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    client = TestClient(app.app)
    client.jobs_dir = jobs  # type: ignore[attr-defined]
    return client


def _write_api_job(jobs: Path) -> dict:
    job, job_dir = _job(jobs.parent, "job1")
    # _job creates <root>/jobs/job1; align it with the API's jobs dir.
    if job_dir != jobs / "job1":
        import shutil

        shutil.move(str(job_dir), str(jobs / "job1"))
        job_dir = jobs / "job1"
    (jobs / "job1" / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job


def test_packet_api_build_get_and_zip(api):
    job = _write_api_job(api.jobs_dir)
    body = {
        "story_id": "story one",
        "render_keys": ["30"],
        "titles": ["One", "Two", "Three"],
        "description": "A short hook.",
        "hashtags": ["#a", "#b", "#c"],
        "cover_times": [1.0, 5.0],
    }

    created = api.post("/api/jobs/job1/packets", json=body)
    assert created.status_code == 200, created.text
    manifest = created.json()
    assert manifest["packet_id"]
    assert manifest["zip_url"].endswith("/zip")
    assert (api.jobs_dir / "job1" / "packets" / manifest["packet_id"]).is_dir()

    fetched = api.get(f"/api/jobs/job1/packets/{manifest['packet_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["titles"] == ["One", "Two", "Three"]

    archive = api.get(f"/api/jobs/job1/packets/{manifest['packet_id']}/zip")
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"
    assert archive.content[:2] == b"PK"

    missing = api.post(
        "/api/jobs/job1/packets",
        json={**body, "render_keys": ["60"]},
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "artifact_missing"
    assert job["renders"]["30"]["status"] == "ready"
