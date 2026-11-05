"""Preflight toggles, findings, severity, and loudness/contrast checks."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app
import artifacts
import captions
import cleanup
import detect
import edits
import preflight
import routes_cleanup


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


# --------------------------------------------------------- Wave 4 T2: markers

JOB_ID = "job-preflight"
SET_ID = "cs_preflight"
STORY_ID = "st_preflight"


def _edit_job(tmp_path: Path, *, aspect: str = "9:16") -> dict:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake-source")
    return {
        "id": JOB_ID,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": str(source),
            "name": "source.mp4",
            "duration": 10.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "size": 11,
            "has_audio": True,
            "fingerprint": "preflight-source",
        },
        "options": {},
        "analysis": {
            "scene_count": 1,
            "hook_scene": 0,
            "scenes": [{
                "id": 0,
                "start": 0.0,
                "end": 10.0,
                "dur": 10.0,
                "mid": 5.0,
                "ocr": "",
                "speech": "A clean opening line.",
                "faces": [{"x": 0.38, "y": 0.34, "w": 0.24, "h": 0.24, "confidence": 0.94}],
                "deep": True,
                "tags": [],
                "crop": {"cx": 0.5, "cy": 0.5},
                "crop_mode": "center",
            }],
        },
        "clip_sets": [{
            "id": SET_ID,
            "job_id": JOB_ID,
            "stories": [{
                "id": STORY_ID,
                "title": "Preflight story",
                "start": 0.0,
                "end": 10.0,
                "dur": 10.0,
                "clips": [{
                    "scene": 0, "start": 0.0, "end": 10.0,
                    "dur": 10.0, "role": "hook",
                }],
            }],
        }],
        "renders": {},
        "preflight": {},
        "aspect": aspect,
    }


@pytest.fixture
def edit_api(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "1")
    directory = jobs / JOB_ID
    directory.mkdir()
    job = _edit_job(tmp_path)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return SimpleNamespace(
        tmp_path=tmp_path,
        jobs=jobs,
        directory=directory,
        job=job,
        client=TestClient(app.app),
    )


def _story_ref(job: dict) -> dict:
    story = job["clip_sets"][0]["stories"][0]
    return {
        "set_id": SET_ID,
        "story_id": STORY_ID,
        "clip_hash": edits.clip_snapshot_hash(story["clips"]),
        "title": story["title"],
        "duration": 10.0,
        "clip_count": 1,
    }


def _save_preflight_edit(env, *, aspect: str = "9:16", **layers):
    edit = edits.build_edit(
        story_ref=_story_ref(env.job),
        aspect=aspect,
        created=1.0,
        **layers,
    )
    edits.save_edit(env.directory, edit)
    return edit


def _fake_residual(monkeypatch, report=None, error=None):
    def measure(*_args, **_kwargs):
        if error is not None:
            raise error
        return report or {
            "pass": True,
            "residual_pct": 0.0,
            "target_pct": 0.5,
            "layers": [],
            "samples": [],
            "frames_sampled": 4,
            "residual_frames": 0,
            "ocr_available": True,
        }

    monkeypatch.setattr(routes_cleanup, "measure_residual", measure)
    return measure


def _marker_kinds(body: dict) -> set[str]:
    return {item["kind"] for item in body["markers"]}


def test_edit_preflight_endpoint_returns_the_marker_contract(edit_api, monkeypatch):
    _fake_residual(monkeypatch)
    edit = _save_preflight_edit(
        edit_api,
        graphics=[
            {
                "type": "text", "kind": "hook", "text": "Same place",
                "start": 0.0, "end": 5.0, "anchor": "center",
                "box": {"w": 0.6, "h": 0.12},
            },
            {
                "type": "text", "kind": "title", "text": "Same place",
                "start": 2.0, "end": 7.0, "anchor": "center",
                "box": {"w": 0.6, "h": 0.12},
            },
        ],
        audio={
            "mode": "dub",
            "loudness": {"lufs": -20.0, "true_peak": -1.5},
            "voice": {"engine": "say", "voice": "Samantha", "rate": 1.4},
            "music": {
                "source": "library", "track": "bed.wav",
                "name": "Night bed", "license": None,
            },
        },
    )

    response = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}/preflight",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"markers", "pass"}
    assert body["pass"] is False
    assert {"collision", "loudness", "voice_fit", "missing_music_license"} <= _marker_kinds(body)
    for marker in body["markers"]:
        assert {"t", "end", "kind", "severity", "message"} <= set(marker)
        assert marker["kind"] in preflight.MARKER_KINDS
        assert marker["severity"] in preflight.SEVERITIES
        assert marker["end"] > marker["t"]
        assert marker["message"]
    collision = next(item for item in body["markers"] if item["kind"] == "collision")
    assert collision["t"] == 2.0
    assert collision["end"] == 5.0
    assert collision["layer_id"] in {"tx01", "tx02"}


def test_edit_preflight_residual_marker_and_failure_are_advisory(edit_api, monkeypatch):
    edit = _save_preflight_edit(
        edit_api,
        clean=[{
            "kind": "plate",
            "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
            "ranges": [{"start": 0.0, "end": 10.0}],
            "label": "Caption cover",
        }],
    )
    _fake_residual(monkeypatch, report={
        "pass": False,
        "residual_pct": 100.0,
        "target_pct": 0.5,
        "layers": [{
            "layer_id": "cl01", "kind": "plate", "frames": 4,
            "residual_frames": 4, "residual_pct": 100.0,
        }],
        "samples": [{"t": 1.0, "residual": True, "text": ["OLD"]}],
        "frames_sampled": 4,
        "residual_frames": 4,
        "ocr_available": True,
    })
    dirty = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}/preflight",
    )
    assert dirty.status_code == 200, dirty.text
    residual = [
        item for item in dirty.json()["markers"] if item["kind"] == "residual_text"
    ]
    assert residual and residual[0]["layer_id"] == "cl01"
    assert "100.0%" in residual[0]["message"]
    assert dirty.json()["pass"] is False

    _fake_residual(
        monkeypatch,
        error=routes_cleanup.ResidualFailure("render exploded", 500),
    )
    failed = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}/preflight",
    )
    assert failed.status_code == 200, failed.text
    info = [
        item for item in failed.json()["markers"]
        if item["kind"] == "residual_text"
    ]
    assert info and info[0]["severity"] == "info"
    assert "render exploded" in info[0]["message"]
    assert failed.json()["pass"] is True


def test_preflight_face_overlap_and_four_five_marker(edit_api, monkeypatch):
    _fake_residual(monkeypatch)
    edit = _save_preflight_edit(
        edit_api,
        aspect="4:5",
        graphics=[{
            "type": "text", "kind": "hook", "text": "Big card",
            "start": 0.0, "end": 10.0, "anchor": "center",
            "box": {"w": 0.8, "h": 0.8},
        }],
    )
    response = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}/preflight",
    )
    assert response.status_code == 200, response.text
    kinds = _marker_kinds(response.json())
    assert "face_overlap" in kinds
    assert "collision" not in kinds

    safe = preflight.safe_zone_markers({
        "aspect": "4:5",
        "overlays": [{
            "id": "tx99", "kind": "hook", "start": 0.0, "end": 10.0,
            "rect": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "safe_zone": True,
        }],
    }, 10.0)
    assert [item["kind"] for item in safe] == ["aspect_4_5"]
    assert "4:5" in safe[0]["message"]


def test_preflight_404_and_story_errors_are_json(edit_api):
    missing = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/ed_{'0' * 32}/preflight",
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Edit not found."

    job = _edit_job(edit_api.tmp_path)
    job["clip_sets"][0]["stories"][0]["id"] = "st_other"
    edit = _save_preflight_edit(edit_api)
    (edit_api.directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    broken = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}/preflight",
    )
    assert broken.status_code == 409
    assert broken.json()["detail"]["code"] == "story_not_found"


def test_caption_density_markers_count_characters_per_second():
    markers = preflight.caption_density_markers({
        "cues": [
            {"start": 0.0, "end": 1.0, "text": "x" * 40},
            {"start": 1.0, "end": 2.0, "text": "fine"},
        ],
    }, 10.0)
    assert len(markers) == 1
    assert markers[0]["kind"] == "caption_density"
    assert markers[0]["layer_id"] == "cap01"
    assert "40.0 characters per second" in markers[0]["message"]


# ------------------------------------------------- Wave 4 T2: residual route


def _clean_residual_edit(env):
    return _save_preflight_edit(
        env,
        clean=[{
            "kind": "plate",
            "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
            "ranges": [{"start": 0.0, "end": 10.0}],
        }],
    )


def _fake_frame(monkeypatch, *, raises: Exception | None = None):
    calls = []

    def render_frame(job, compiled, t, quality, aspect):
        calls.append(t)
        if raises is not None:
            raise raises
        return b"fake-jpg"

    def probe(directory):
        return {
            path.name: {"text": [], "faces": []}
            for path in sorted(Path(directory).glob("*.jpg"))
        }

    monkeypatch.setattr(routes_cleanup, "_render_frame", render_frame)
    monkeypatch.setattr(routes_cleanup, "_probe_images", probe)
    return calls


def test_residual_route_hard_frame_cap(edit_api, monkeypatch):
    edit = _clean_residual_edit(edit_api)
    _fake_frame(monkeypatch)
    response = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": edit["id"], "max_frames": cleanup.RESIDUAL_MAX_FRAMES + 1},
    )
    assert response.status_code == 422
    assert "capped" in response.json()["detail"]
    assert str(cleanup.RESIDUAL_MAX_FRAMES) in response.json()["detail"]


def test_residual_route_render_failure_is_json_with_a_logged_traceback(
    edit_api, monkeypatch, caplog,
):
    edit = _clean_residual_edit(edit_api)
    _fake_frame(monkeypatch, raises=RuntimeError("ffmpeg vanished"))
    response = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": edit["id"], "max_frames": 2},
    )
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "Residual render failed" in detail
    assert "ffmpeg vanished" in detail
    assert any(
        "residual failed" in record.getMessage()
        for record in caplog.records
    )


def test_residual_route_deadline_is_a_clear_504(edit_api, monkeypatch):
    edit = _clean_residual_edit(edit_api)
    _fake_frame(monkeypatch)
    ticks = iter([1_000_000.0, 1_000_500.0])
    monkeypatch.setattr(
        routes_cleanup,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks)),
    )
    response = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": edit["id"], "max_frames": 2},
    )
    assert response.status_code == 504
    assert "budget" in response.json()["detail"]
    assert "max_frames" in response.json()["detail"]


# --------------------------------------------- Wave 4 T2: Clean kind gate


def _clean_body(*layers) -> dict:
    return {
        "set_id": SET_ID,
        "story_id": STORY_ID,
        "aspect": "9:16",
        "clean": list(layers),
    }


def test_clean_save_needs_the_tick_for_a_watermark_and_allows_screen_text(edit_api):
    detect.write_report(edit_api.directory, {
        "schema": 1, "status": "ready", "complete": True,
        "tracklets": [
            {
                "id": "trk_water", "kind": "watermark",
                "box": {"x": 0.8, "y": 0.05, "w": 0.15, "h": 0.06},
                "ranges": [{"start": 0.0, "end": 10.0}],
            },
        ],
    })
    watermark = {
        "kind": "blur",
        "box": {"x": 0.8, "y": 0.05, "w": 0.15, "h": 0.06},
        "tracklet_id": "trk_water",
        "tracklet_kind": "watermark",
    }
    refused = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/edits", json=_clean_body(watermark),
    )
    assert refused.status_code == 409
    assert "watermark" in refused.json()["detail"]


def test_clean_save_handle_needs_attestation_and_old_edits_still_save(edit_api):
    handle = {
        "kind": "blur",
        "box": {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05},
        "tracklet_id": "trk_handle",
        "tracklet_kind": "handle_or_logo",
    }
    locked = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/edits", json=_clean_body(handle),
    )
    assert locked.status_code == 409
    assert "Own-footage attestation" in locked.json()["detail"]

    edit_api.client.post(
        f"/api/jobs/{JOB_ID}/rights",
        json={"attested": True, "source": "import"},
    )
    allowed = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/edits", json=_clean_body(handle),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["edit"]["clean"][0]["tracklet_kind"] == "handle_or_logo"

    legacy = {
        "kind": "plate",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
    }
    old = edit_api.client.post(
        f"/api/jobs/{JOB_ID}/edits", json=_clean_body(legacy),
    )
    assert old.status_code == 200, old.text
    assert "tracklet_id" not in old.json()["edit"]["clean"][0]
    assert "tracklet_kind" not in old.json()["edit"]["clean"][0]


def test_clean_optional_provenance_keeps_old_hash_unchanged(edit_api):
    old = edits.build_edit(
        story_ref=_story_ref(edit_api.job),
        aspect="9:16",
        clean=[{
            "kind": "plate",
            "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
        }],
        created=1.0,
    )
    assert "tracklet_id" not in old["clean"][0]
    edits.save_edit(edit_api.directory, old)
    reloaded = edits.load_edit(edit_api.directory, old["id"])
    assert reloaded["hash"] == old["hash"]

    built = cleanup.tracklet_clean_layers([{
        "id": "trk_sub", "kind": "subtitle",
        "box": {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09},
        "ranges": [{"start": 0.0, "end": 10.0}],
        "confidence": 0.9,
    }], attested=True)
    normalized = edits.normalize_clean(built["layers"])
    assert normalized[0]["tracklet_id"] == "trk_sub"
    assert normalized[0]["tracklet_kind"] == "subtitle"
    assert normalized[0]["kind"] == "delogo"


def test_preflight_marks_baked_check_text_with_no_clean_layer(edit_api, monkeypatch):
    _fake_residual(monkeypatch)
    report = {
        "schema": 1,
        "status": "ready",
        "complete": True,
        "tracklets": [{
            "id": "trk_old", "kind": "subtitle",
            "box": {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09},
            "ranges": [{"start": 0.0, "end": 10.0}],
            "text_sample": "OLD CAPTION", "confidence": 0.9,
        }],
    }
    detect.write_report(edit_api.directory, report)
    edit = _save_preflight_edit(edit_api)

    response = edit_api.client.get(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}/preflight",
    )

    assert response.status_code == 200, response.text
    residual = [
        item for item in response.json()["markers"]
        if item["kind"] == "residual_text"
    ]
    assert residual
    assert "no active Clean layer" in residual[0]["message"]
    assert "OLD CAPTION" in residual[0]["message"]
    assert response.json()["pass"] is False
