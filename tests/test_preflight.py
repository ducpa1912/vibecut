"""Preflight toggles, findings, severity, and loudness/contrast checks."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app
import artifacts
import preflight


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


def _job(**overrides) -> dict:
    scenes = [
        {
            "id": 0, "start": 0.0, "end": 5.0, "dur": 5.0,
            "speech": "I'll show you three things later and",
        },
        {
            "id": 1, "start": 5.0, "end": 10.0, "dur": 5.0,
            "speech": "That is it and",
        },
    ]
    job = {
        "id": "job1",
        "status": "ready",
        "source": {"name": "source.mp4", "duration": 10.0},
        "analysis": {"scenes": scenes, "plans": {"30": _plan()}},
        "renders": {},
        "preflight": {},
    }
    job.update(overrides)
    return job


def _story_job() -> dict:
    job = _job()
    job["stories"] = [
        {
            "id": "story1",
            "plan": _plan(),
            "cues": [
                {"start": 0.0, "end": 1.0, "text": "x" * 40},
                {"start": 1.0, "end": 5.0, "text": "That is it and"},
            ],
            "loudness_lufs": -30.0,
            "safe_zone_contrast": 1.4,
        },
    ]
    return job


def _attach_story_media(job: dict, job_dir: Path) -> dict:
    render = job_dir / "renders" / "reel_30.mp4"
    render.parent.mkdir(parents=True, exist_ok=True)
    render.write_bytes(b"fake-mp4")
    job["stories"][0]["media_path"] = "renders/reel_30.mp4"
    return job


def _jpeg_bytes(color=(20, 20, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _artifact_job(job_dir: Path) -> tuple[dict, str]:
    job = _job()
    for scene in job["analysis"]["scenes"]:
        scene["speech"] = "unrelated analysis plan text"
    spec = artifacts.build_spec(
        job, _plan(), quality="final", aspect="9:16", captions=True,
    )
    manifest = artifacts.make_manifest(
        job["id"], spec, status="ready", record_key="30",
    )
    manifest = artifacts.save_manifest(job_dir, manifest)
    artifact_id = manifest["artifact_id"]
    reel = job_dir / "render.mp4"
    reel.write_bytes(
        b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 32
    )
    poster = job_dir / "poster.jpg"
    poster.write_bytes(_jpeg_bytes())
    artifacts.complete_artifact(
        job_dir, artifact_id,
        reel=reel, poster=poster,
        srt=(
            "1\n00:00:00,000 --> 00:00:01,000\n" + "x" * 40 + "\n\n"
            "2\n00:00:01,000 --> 00:00:05,000\nartifact payoff.\n"
        ),
        vtt="WEBVTT\n\n",
        render_info={"duration": 10.0, "width": 1080, "height": 1920},
    )
    manifest = artifacts.load_manifest(job_dir, artifact_id)
    assert manifest is not None
    job["artifacts"] = {artifact_id: artifacts.manifest_summary(manifest)}
    job["artifact_ids"] = [artifact_id]
    job["renders"] = {"30": artifacts.render_record(manifest)}
    return job, artifact_id


def test_preflight_reports_every_enabled_check_with_metadata(tmp_path):
    result = preflight.run_preflight(
        _attach_story_media(_story_job(), tmp_path), "story1", tmp_path,
    )

    findings = {item["id"]: item for item in result["findings"]}
    assert set(findings) == set(preflight.CHECK_IDS)
    for finding in result["findings"]:
        assert set(finding) == {"id", "severity", "toggle", "message", "suggestion"}
        assert finding["severity"] == "warn"
        assert finding["toggle"] == finding["id"]
        assert finding["message"]
        assert finding["suggestion"]
    assert result["blocked"] is False
    for check_id, meta in result["checks"].items():
        assert meta["style"] == preflight.CHECK_BY_ID[check_id]["style"]
        assert meta["toggle"] == check_id
        assert meta["enabled"] is True
        assert meta["severity"] == "warn"
    assert result["styles"]["loudness"] == "audio"


def test_preflight_job_toggles_are_independent(tmp_path):
    job = _story_job()
    job["preflight"] = {
        "toggles": {"caption_density": False, "loudness": False},
    }
    result = preflight.run_preflight(job, "story1", tmp_path)

    assert result["toggles"]["caption_density"] is False
    assert result["toggles"]["loudness"] is False
    assert "caption_density" not in {item["id"] for item in result["findings"]}
    assert "loudness" not in {item["id"] for item in result["findings"]}
    assert result["checks"]["caption_density"]["status"] == "disabled"
    assert result["checks"]["caption_density"]["enabled"] is False
    assert "dangling_claims" in {item["id"] for item in result["findings"]}


def test_preflight_settings_toggle_and_job_override(tmp_path):
    settings = {"preflight": {"toggles": {"dangling_claims": False}}}
    job = _story_job()
    job["preflight"] = {"dangling_claims": True}
    result = preflight.run_preflight(job, "story1", tmp_path, settings=settings)

    assert result["checks"]["dangling_claims"]["enabled"] is True


def test_preflight_block_severity_only_when_configured(tmp_path):
    job = _attach_story_media(_story_job(), tmp_path)
    job["preflight"] = {"severity": {"loudness": "block"}}
    result = preflight.run_preflight(job, "story1", tmp_path)

    loudness = next(item for item in result["findings"] if item["id"] == "loudness")
    assert loudness["severity"] == "block"
    assert result["blocked"] is True
    assert result["checks"]["loudness"]["severity"] == "block"


def test_preflight_low_and_high_loudness_via_mock(tmp_path, monkeypatch):
    image = tmp_path / "renders" / "poster.jpg"
    image.parent.mkdir()
    image.write_bytes(b"not-needed-for-mock")
    video = tmp_path / "renders" / "reel_30.mp4"
    video.write_bytes(b"fake")
    job = _job(
        renders={
            "30": {
                "status": "ready",
                "path": "reel_30.mp4",
                "poster": "poster.jpg",
                "target": 30,
                "duration": 10.0,
                "plan": _plan(),
            },
        },
    )

    monkeypatch.setattr(preflight, "measure_loudness", lambda path: -30.0)
    low = preflight.run_preflight(job, "30", tmp_path)
    low_finding = next(item for item in low["findings"] if item["id"] == "loudness")
    assert "below" in low_finding["message"]
    assert low["checks"]["loudness"]["details"]["integrated_lufs"] == -30.0
    assert low["checks"]["loudness"]["details"]["source"] == "ffmpeg_render"
    assert low["checks"]["loudness"]["details"]["media_source"] == "render"

    monkeypatch.setattr(preflight, "measure_loudness", lambda path: -6.0)
    high = preflight.run_preflight(job, "30", tmp_path)
    high_finding = next(item for item in high["findings"] if item["id"] == "loudness")
    assert "above" in high_finding["message"]
    assert high["blocked"] is False


def test_preflight_safe_zone_reads_poster_contrast(tmp_path):
    from PIL import Image

    poster = tmp_path / "renders" / "poster.jpg"
    poster.parent.mkdir()
    Image.new("L", (360, 640), color=245).save(poster, format="JPEG")
    job = _job(
        renders={
            "30": {
                "status": "ready",
                "path": "reel_30.mp4",
                "poster": "poster.jpg",
                "target": 30,
                "duration": 10.0,
                "plan": _plan(),
                "loudness_lufs": -14.0,
            },
        },
    )
    (tmp_path / "renders" / "reel_30.mp4").write_bytes(b"fake")

    result = preflight.run_preflight(job, "30", tmp_path)

    contrast = next(
        item for item in result["findings"] if item["id"] == "safe_zone_contrast"
    )
    assert "contrast" in contrast["message"]
    assert result["checks"]["safe_zone_contrast"]["status"] == "finding"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_preflight_extracts_cover_when_poster_is_missing(tmp_path):
    video = tmp_path / "renders" / "reel_30.mp4"
    video.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=white:s=320x180:d=1", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )
    job = _job(
        renders={
            "30": {
                "status": "ready",
                "path": "reel_30.mp4",
                "target": 30,
                "duration": 1.0,
                "plan": _plan(),
                "loudness_lufs": -14.0,
            },
        },
    )

    result = preflight.run_preflight(job, "30", tmp_path)

    contrast = next(
        item for item in result["findings"] if item["id"] == "safe_zone_contrast"
    )
    assert result["checks"]["safe_zone_contrast"]["details"]["source"] == "ffmpeg"
    assert "contrast" in contrast["message"]


def test_preflight_caption_density_threshold(tmp_path):
    job = _story_job()
    job["stories"][0]["cues"] = [
        {"start": 0.0, "end": 2.0, "text": "short"},
        {"start": 2.0, "end": 3.0, "text": "x" * 31},
    ]
    result = preflight.run_preflight(job, "story1", tmp_path)

    density = next(
        item for item in result["findings"] if item["id"] == "caption_density"
    )
    assert "characters per second" in density["message"]
    assert result["checks"]["caption_density"]["details"]["cps"] > preflight.MAX_CAPTION_CPS


def test_preflight_falls_back_to_a_plan_from_scenes(tmp_path):
    job = _job()
    job["analysis"]["plans"] = {}

    result = preflight.run_preflight(job, "30", tmp_path)

    assert result["story_id"] == "30"
    assert result["checks"]["caption_density"]["status"] in {"pass", "unavailable"}


def test_preflight_measures_render_before_source(tmp_path, monkeypatch):
    render = tmp_path / "renders" / "reel_30.mp4"
    render.parent.mkdir()
    render.write_bytes(b"render")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(
        source={"name": "source.mp4", "duration": 10.0, "path": str(source)},
        renders={
            "30": {
                "status": "ready",
                "path": "reel_30.mp4",
                "target": 30,
                "duration": 10.0,
                "plan": _plan(),
            },
        },
    )
    calls: list[str] = []

    def measure(path):
        calls.append(str(path))
        return -14.0

    monkeypatch.setattr(preflight, "measure_loudness", measure)
    result = preflight.run_preflight(job, "30", tmp_path)

    assert calls == [str(render)]
    assert result["media_source"] == "render"


def test_preflight_source_fallback_does_not_run_block_checks(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(source={"name": "source.mp4", "duration": 10.0, "path": str(source)})
    job["preflight"] = {"severity": {"loudness": "block"}}
    calls: list[str] = []
    monkeypatch.setattr(
        preflight, "measure_loudness",
        lambda path: calls.append(str(path)) or -30.0,
    )
    result = preflight.run_preflight(job, "30", tmp_path)

    assert calls == []
    assert result["media_source"] == "source_fallback"
    assert result["narrative_only"] is True
    assert result["blocked"] is False
    assert result["checks"]["loudness"]["status"] == "unavailable"
    assert result["checks"]["safe_zone_contrast"]["status"] == "unavailable"
    assert "source fallback is not used" in result["checks"]["loudness"]["reason"]


def test_preflight_missing_render_does_not_measure_source(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(
        source={"name": "source.mp4", "duration": 10.0, "path": str(source)},
        renders={
            "30": {
                "status": "ready",
                "path": "missing.mp4",
                "target": 30,
                "duration": 10.0,
                "plan": _plan(),
            },
        },
    )
    monkeypatch.setattr(
        preflight, "measure_loudness",
        lambda path: pytest.fail("source fallback must not be measured"),
    )
    result = preflight.run_preflight(job, "30", tmp_path)

    assert result["media_source"] == "missing_render"
    assert result["checks"]["loudness"]["status"] == "unavailable"
    assert "source fallback was not used" in result["checks"]["loudness"]["reason"]


def test_preflight_rejects_absolute_and_parent_import_paths(tmp_path):
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"fake")
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"fake")
    job = _job()
    job["analysis"]["scenes"][0]["speech"] = "Neutral opening."
    job["analysis"]["scenes"][1]["speech"] = "Neutral ending."
    job["stories"] = [{
        "id": "story1",
        "plan": _plan(),
        "media_path": str(secret),
        "poster_path": "../outside.jpg",
        "loudness_lufs": -14.0,
    }]
    result = preflight.run_preflight(job, "story1", tmp_path / "jobdir")

    assert result["media_source"] == "missing_render"
    assert result["checks"]["safe_zone_contrast"]["status"] == "unavailable"
    assert not result["findings"]


def test_preflight_artifact_id_loads_manifest_media_and_captions(tmp_path, monkeypatch):
    job, artifact_id = _artifact_job(tmp_path)
    monkeypatch.setattr(preflight, "measure_loudness", lambda path: -14.0)

    result = preflight.run_preflight(job, artifact_id, tmp_path)

    assert result["media_source"] == "artifact"
    assert result["checks"]["loudness"]["status"] == "pass"
    assert result["checks"]["safe_zone_contrast"]["status"] == "pass"
    density = next(
        item for item in result["findings"] if item["id"] == "caption_density"
    )
    assert "characters per second" in density["message"]
    assert result["checks"]["caption_density"]["details"]["cps"] > preflight.MAX_CAPTION_CPS


def test_preflight_artifact_id_without_summary_loads_manifest(tmp_path, monkeypatch):
    job, artifact_id = _artifact_job(tmp_path)
    job["artifacts"] = {}
    job["artifact_ids"] = []
    monkeypatch.setattr(preflight, "measure_loudness", lambda path: -14.0)

    result = preflight.run_preflight(job, artifact_id, tmp_path)

    assert result["media_source"] == "artifact"
    assert result["checks"]["loudness"]["status"] == "pass"
    assert "caption_density" in {item["id"] for item in result["findings"]}


def test_preflight_render_key_uses_artifact_captions_and_spec(tmp_path, monkeypatch):
    job, artifact_id = _artifact_job(tmp_path)
    monkeypatch.setattr(preflight, "measure_loudness", lambda path: -14.0)

    result = preflight.run_preflight(job, "30", tmp_path)

    assert result["render_key"] == "30"
    assert result["media_source"] == "artifact"
    density = next(
        item for item in result["findings"] if item["id"] == "caption_density"
    )
    assert "characters per second" in density["message"]
    assert result["checks"]["loudness"]["status"] == "pass"


def test_preflight_parse_srt_accepts_cue_settings_and_large_hours():
    cues = preflight.parse_srt(
        "1\n100:00:00,000 --> 100:00:02,000 X1:10 X2:20 Y1:30 Y2:40\n"
        "Positioned cue.\n"
    )

    assert len(cues) == 1
    assert cues[0]["start"] == 360000.0
    assert cues[0]["end"] == 360002.0


def test_preflight_settings_validation():
    assert preflight.validate_settings({"toggles": {"loudness": False}})
    for value in (None, [], {"toggles": "off"}, {"severity": []}):
        with pytest.raises(ValueError):
            preflight.validate_settings(value)


def test_preflight_unknown_story_is_explicit(tmp_path):
    with pytest.raises(preflight.PreflightError) as failed:
        preflight.run_preflight(_job(), "missing-story", tmp_path)
    assert failed.value.code == "story_not_found"
    assert failed.value.status == 404


@pytest.fixture
def api(tmp_path, monkeypatch):
    jobs = tmp_path / "data" / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", tmp_path / "data")
    monkeypatch.setattr(app, "JOBS", jobs)
    client = TestClient(app.app)
    client.jobs_dir = jobs  # type: ignore[attr-defined]
    return client


def test_preflight_api_returns_findings(api):
    job = _story_job()
    directory = api.jobs_dir / "job1"
    directory.mkdir()
    _attach_story_media(job, directory)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")

    response = api.get("/api/jobs/job1/preflight", params={"story_id": "story1"})

    assert response.status_code == 200
    body = response.json()
    assert body["story_id"] == "story1"
    assert body["blocked"] is False
    assert {item["id"] for item in body["findings"]} == set(preflight.CHECK_IDS)

    missing = api.get("/api/jobs/job1/preflight", params={"story_id": "nope"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "story_not_found"


def test_preflight_api_accepts_trust_artifact_id(api, monkeypatch):
    directory = api.jobs_dir / "job1"
    directory.mkdir()
    job, artifact_id = _artifact_job(directory)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(preflight, "measure_loudness", lambda path: -14.0)

    response = api.get(
        "/api/jobs/job1/preflight", params={"story_id": artifact_id},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["story_id"] == artifact_id
    assert body["media_source"] == "artifact"
    assert body["checks"]["loudness"]["status"] == "pass"
    assert body["checks"]["safe_zone_contrast"]["status"] == "pass"
    assert "caption_density" in {item["id"] for item in body["findings"]}
