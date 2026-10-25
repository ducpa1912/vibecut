"""Preflight toggles, findings, severity, and loudness/contrast checks."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import app
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


def test_preflight_reports_every_enabled_check_with_metadata(tmp_path):
    result = preflight.run_preflight(_story_job(), "story1", tmp_path)

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
    job = _story_job()
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


def test_preflight_source_fallback_is_explicit(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    job = _job(source={"name": "source.mp4", "duration": 10.0, "path": str(source)})
    calls: list[str] = []
    monkeypatch.setattr(
        preflight, "measure_loudness",
        lambda path: calls.append(str(path)) or -30.0,
    )
    result = preflight.run_preflight(job, "30", tmp_path)

    assert calls == [str(source)]
    assert result["media_source"] == "source_fallback"
    assert result["checks"]["loudness"]["details"]["media_source"] == "source_fallback"
    assert result["checks"]["loudness"]["details"]["source"] == "ffmpeg_source_fallback"


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
