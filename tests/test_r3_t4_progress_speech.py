"""R3 T4: honest Import/Check progress, speech auto-detect, retry, disk copy."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import detect
import disk
import pipeline
import stt

GIB = 1024 ** 3


def _scene(index: int, start: float, end: float, *, deep: bool = True) -> dict:
    return {
        "id": index, "start": start, "end": end, "dur": end - start,
        "mid": (start + end) / 2, "deep": deep, "speech": "",
    }


# ---------------------------------------------------------------- progress


def test_progress_is_monotonic_stage_weighted_and_has_no_zero_eta():
    clock = [100.0]
    calls: list[tuple[str, float, str]] = []
    tracker = pipeline.ProgressTracker(
        lambda stage, fraction, message: calls.append((stage, fraction, message)),
        clock=lambda: clock[0],
    )
    assert tracker.eta_seconds() is None
    tracker.emit("scanning", 0.0, "Slicing the timeline")
    assert "estimating" in calls[-1][2]

    clock[0] += 1.0
    tracker.emit("scanning", 0.40, "Scanning cuts · 0:20 / 0:53")
    clock[0] += 1.0
    tracker.emit("scanning", 0.80, "Scanning cuts · 0:42 / 0:53")
    clock[0] += 1.0
    tracker.emit("scanning", 1.0, "Timeline sliced")
    clock[0] += 1.0
    tracker.emit("crop", 0.50, "Tracking crop · 25 / 50")
    clock[0] += 1.0
    tracker.emit("crop", 1.0, "Tracking crop · 50 / 50")
    clock[0] += 1.0
    tracker.emit("speech", 0.30, "Transcribing · 8 / 25")

    values = [fraction for _stage, fraction, _message in calls]
    assert values == sorted(values)
    assert all(0.0 < value <= 1.0 for value in values)
    assert calls[-1][0] == "reading"  # app.py's ACTIVE status, not "speech"
    # Crop is a real band, not two percent: at half its frames the bar is
    # already moving, and 50 / 50 is followed by more work.
    crop = [(fraction, message) for stage, fraction, message in calls if "crop" in message]
    assert crop and 0.60 <= crop[0][0] <= 0.78
    assert crop[0][1].startswith("Tracking crop · 25 / 50")
    assert any(message.startswith("Tracking crop · 50 / 50") for _stage, _fraction, message in calls)

    eta = tracker.eta_seconds()
    assert eta is not None and eta >= 1
    assert "about" in tracker.decorate("Reading frames") and "left" in tracker.decorate("Reading frames")


def test_eta_hides_before_ten_percent_and_uses_elapsed_when_unreliable():
    clock = [0.0]
    tracker = pipeline.ProgressTracker(clock=lambda: clock[0])
    tracker.emit("scanning", 0.0, "Slicing the timeline")
    assert tracker.value < 0.10
    assert tracker.eta_seconds() is None
    assert tracker.decorate("Slicing").endswith("estimating")

    clock[0] += 1.0
    tracker.emit("scanning", 1.0, "Timeline sliced")  # now 20%
    # No rate window yet: elapsed + stage, not a fabricated number.
    assert tracker.eta_seconds() is None
    decorated = tracker.decorate("Pulling stills")
    assert "so far" in decorated and "about" not in decorated


def test_eta_does_not_oscillate_wildly_on_a_steady_rate():
    clock = [0.0]
    tracker = pipeline.ProgressTracker(clock=lambda: clock[0])
    estimates: list[int] = []
    for step in range(24):
        clock[0] = step * 2.0
        tracker.emit("scanning", min(0.98, 0.05 + step * 0.04), "Scanning cuts")
        eta = tracker.eta_seconds()
        if eta is not None:
            estimates.append(eta)
    assert estimates and all(value >= 1 for value in estimates)
    assert max(estimates) <= min(estimates) * 8


def test_analyze_source_never_moves_backwards_and_says_smoothing_not_done(
    tmp_path, monkeypatch,
):
    scenes = [_scene(0, 0.0, 5.0), _scene(1, 5.0, 10.0)]
    calls: list[tuple[str, float, str]] = []

    def scan(path, duration, progress):
        progress(0.0, "Scanning cuts · 0:00 / 0:10")
        progress(0.7, "Scanning cuts · 0:07 / 0:10")
        return scenes, {}

    monkeypatch.setattr(pipeline, "scan_scenes", scan)
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args: None)
    monkeypatch.setattr(pipeline, "audio_features", lambda *args: {"available": False})
    monkeypatch.setattr(pipeline, "select_deep_scenes", lambda scenes, duration: [0, 1])
    monkeypatch.setattr(pipeline, "extract_thumbs", lambda *args: None)
    monkeypatch.setattr(pipeline.vision, "available", lambda: True)
    monkeypatch.setattr(pipeline, "_apply_scene_read", lambda *args: None)
    monkeypatch.setattr(pipeline, "attach_speech", lambda *args: None)
    monkeypatch.setattr(pipeline, "score_scenes", lambda *args: None)
    monkeypatch.setattr(pipeline, "attach_crop_paths", lambda *args: None)
    monkeypatch.setattr(pipeline, "auto_hook", lambda scenes: {"id": 0})
    monkeypatch.setattr(pipeline, "make_plans", lambda *args: [])
    monkeypatch.setattr(pipeline, "_deep_limit", lambda: 40)

    tracking = {
        "s00000_0.jpg": tmp_path / "s00000_0.jpg",
        "s00000_1.jpg": tmp_path / "s00000_1.jpg",
    }

    def tracking_frames(path, deep, job_dir, progress):
        progress(0.5, "Tracking crop · 1 / 2")
        return tracking

    def probe(directory, files, *, progress=None, label="Reading frames", batch_size=8):
        if progress:
            progress(1.0, f"{label} · {len(files)} / {len(files)}")
        return {}

    monkeypatch.setattr(pipeline, "extract_tracking_frames", tracking_frames)
    monkeypatch.setattr(pipeline, "_probe_images_progress", probe)

    analysis = pipeline.analyze_source(
        "/tmp/source.mp4",
        {"duration": 10.0, "width": 1080, "height": 1920, "has_audio": False},
        tmp_path,
        {"ocr": True, "smart_crop": True, "crop_tracking": True, "transcribe": False},
        lambda stage, fraction, message: calls.append((stage, fraction, message)),
    )

    assert analysis["engine"]["stt_enabled"] is False
    values = [fraction for _stage, fraction, _message in calls]
    assert values == sorted(values)
    assert all(0.0 < value <= 0.995 for value in values)
    messages = [message for _stage, _fraction, message in calls]
    assert any(message.startswith("Tracking crop · 1 / 2") for message in messages)
    assert any(message.startswith("Smoothing crop paths · 2 / 2") for message in messages)
    assert not any(message.startswith("Tracking crop · 2 / 2") for message in messages)


def test_cancel_event_stops_a_pipeline_child_process(monkeypatch):
    import threading
    import time as clock

    event = threading.Event()
    stt.set_cancel_event(event)
    try:
        timer = threading.Timer(0.3, event.set)
        timer.start()
        started = clock.monotonic()
        with pytest.raises(stt.SttCancelled):
            pipeline._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=60)
        assert clock.monotonic() - started < 5
    finally:
        stt.set_cancel_event(None)


# ---------------------------------------------------------------- speech


def test_whisper_auto_language_omits_the_flag(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)
    captured: dict = {}

    class Result:
        returncode = 0

    def fake_run(cmd, stdout=None, stderr=None, timeout=None, env=None):
        captured["cmd"] = cmd
        out = Path(cmd[cmd.index("--output-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "transcript.json").write_text(json.dumps({
            "language": "zh",
            "segments": [{
                "start": 0.0, "end": 1.0, "text": "你好",
                "avg_logprob": -0.2, "no_speech_prob": 0.01,
                "compression_ratio": 1.1,
                "words": [{"word": "你好", "start": 0.0, "end": 1.0, "probability": 0.9}],
            }],
        }), encoding="utf-8")
        return Result()

    monkeypatch.setattr(stt, "_whisper_binary", lambda: "mlx_whisper")
    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    result = stt.transcribe(wav, tmp_path, 1.0, lambda *_: None, language="")
    assert result and result["language"] == "zh"
    assert "--language" not in captured["cmd"]


def test_auto_language_skips_apple_and_lets_whisper_detect(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)
    seen: list[tuple[str, str]] = []
    errors: list[dict] = []

    monkeypatch.setattr(stt, "has_speech_energy", lambda path: True)
    monkeypatch.setattr(stt, "prepare_audio", lambda source, job_dir, *, source_hash="": (source, "h"))
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: True)

    def chunked(prepared, job_dir, duration, *, audio_hash, engine, model, language,
                vocabulary, timeout, progress, helper):
        seen.append((engine, language))
        return {
            "language": "zh",
            "segments": [{"start": 0.0, "end": 1.0, "text": "你好"}],
            "words": [{"w": "你好", "start": 0.0, "end": 1.0, "confidence": 0.9}],
        }

    monkeypatch.setattr(stt, "_chunked_run", chunked)
    result = stt.transcribe_source(
        wav, tmp_path, 2.0,
        routes=[
            {"provider": "apple", "model": "on-device-3b"},
            {"provider": "whisper", "model": "mlx-community/whisper-large-v3-turbo"},
        ],
        language="",
        errors=errors,
    )
    assert result and result["language"] == "zh"
    assert seen == [("whisper", "")]
    assert any(item["provider"] == "apple" for item in errors)


def test_retry_speech_reuses_the_job_without_reading_frames(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    scenes = [_scene(0, 0.0, 10.0)]
    job = {
        "id": "j1",
        "source": {"path": str(source), "duration": 10.0, "has_audio": True},
        "options": {"transcribe": True, "speech_language": "en"},
        "analysis": {"scenes": scenes, "engine": {"stt_enabled": True}},
    }

    def no_frames(*args, **kwargs):
        raise AssertionError("retry must not read frames")

    monkeypatch.setattr(pipeline, "extract_thumbs", no_frames)
    monkeypatch.setattr(pipeline, "_probe_images_progress", no_frames)
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args: wav)
    monkeypatch.setattr(
        stt, "transcribe_source",
        lambda *args, **kwargs: {
            "language": "zh", "segments": [{"start": 0.0, "end": 1.0, "text": "你好"}],
            "words": [], "provider": "whisper", "text": "你好",
        },
    )
    monkeypatch.setattr(stt, "attach_speech", lambda scenes, transcript: scenes[0].update(speech="你好"))

    result = pipeline.retry_speech(job, tmp_path, progress=lambda *args: None)
    assert result["ok"] is True
    assert result["transcript"]["language"] == "zh"
    assert result["engine"]["stt_language"] == "auto"
    assert scenes[0]["speech"] == "你好"


def test_check_warning_distinguishes_speech_off_from_engine_empty():
    base = {
        "id": "b",
        "source": {"path": "/tmp/b.mp4", "duration": 88.8, "has_audio": True},
        "analysis": {
            "scenes": [],
            "engine": {
                "vision": True, "whisper": False,
                "stt_enabled": True, "stt_language": "auto",
                "stt_error": "No transcript returned.",
            },
            "transcript": None,
        },
    }
    report = detect.build_report(
        base, [],
        sampled={"ran": True, "frames": 1, "vision": True},
        settings={"rights": {"lock": False}},
    )
    codes = [item["code"] for item in report["warnings"]]
    message = " ".join(item["message"] for item in report["warnings"])
    assert "speech_engine_empty" in codes
    assert "Speech was on" in message
    assert "Import it again" not in message
    assert report["audio"]["speech_state"] == "engine_empty"
    assert report["audio"]["speech_language"] == "auto"

    off = json.loads(json.dumps(base))
    off["options"] = {"transcribe": False}
    off["analysis"]["engine"]["stt_enabled"] = False
    off["analysis"]["engine"]["stt_error"] = None
    report_off = detect.build_report(
        off, [],
        sampled={"ran": True, "frames": 1, "vision": True},
        settings={"rights": {"lock": False}},
    )
    assert report_off["audio"]["speech_state"] == "off"
    assert any(item["code"] == "speech_off" for item in report_off["warnings"])


def test_check_progress_is_monotonic(tmp_path):
    values: list[float] = []

    def sampler(path, job_dir, duration, *, fps, max_frames, progress):
        progress(0.75, "Reading text · frame 75 / 100")
        progress(0.20, "Reading text · frame 20 / 100")  # a stale child update
        return {"frames": [], "vision": True, "fps": fps}

    detect.run_check(
        "j1",
        {
            "id": "j1", "status": "ready",
            "source": {"path": "/tmp/x.mp4", "duration": 10.0, "has_audio": True},
            "analysis": {"scenes": []},
        },
        tmp_path,
        sampler=sampler,
        audio_extractor=lambda *args, **kwargs: None,
        progress=lambda fraction, message: values.append(fraction),
    )
    assert values == sorted(values)
    assert values[-1] == 1.0


# ---------------------------------------------------------------- disk


def test_disk_refusal_speaks_gb_and_path_import_does_not_demand_copy_reserve(
    monkeypatch, tmp_path,
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    monkeypatch.setattr(disk, "usage", lambda path: (100 * GIB, 0, int(4.3 * GIB)))
    path_report = disk.report(disk.estimate_path(source), tmp_path)
    assert path_report["ok"] is True
    assert path_report["in_place"] is True
    assert path_report["reserve_bytes"] == 0

    render_report = disk.report(disk.estimate_render(30), tmp_path)
    assert render_report["ok"] is False
    assert render_report["reserve_bytes"] == 5 * GIB

    # Above the reserve: a real path read still does not demand the 5 GB copy
    # reserve.  Renders on the same volume still do.
    monkeypatch.setattr(disk, "usage", lambda path: (100 * GIB, 0, int(5.05 * GIB)))
    assert disk.report(disk.estimate_path(source), tmp_path)["ok"] is True
    assert disk.report(disk.estimate_render(30), tmp_path)["ok"] is False

    with pytest.raises(disk.InsufficientSpace) as caught:
        disk.preflight(disk.estimate_render(30), tmp_path)
    payload = caught.value.as_dict()
    assert " bytes" not in payload["message"]
    assert "GB" in payload["message"]
    assert {"free_gb", "reserve_gb", "shortfall_gb"} <= set(payload)
    assert payload["shortfall_gb"] > 0


# ---------------------------------------------------------------- Check UI helpers

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")
STUDIO = Path(__file__).resolve().parents[1] / "static" / "studio"


def _run_check_module(body: str):
    script = (
        f"const m = await import({json.dumps((STUDIO / 'check.js').as_uri())});\n"
        f"const out = await (async () => {{ {body} }})();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


@needs_node
def test_check_eta_copy_and_speech_status_helpers():
    out = _run_check_module("""
        return {
          intro: m.checkIntroCopy(52.9),
          before: m.etaText(0.05, 30, 3, "Reading text"),
          measured: m.etaText(0.42, 17, 20, "Reading text"),
          elapsed: m.etaText(0.42, null, 20, "Reading text"),
          eta: m.estimateRemaining([{t: 0, p: 0.10}, {t: 5, p: 0.20}, {t: 10, p: 0.30}]),
          smooth: [m.smoothEta(100, 50), m.smoothEta(1, 100)],
          off: m.speechStatus({transcript: false, speech_state: "off"}),
          empty: m.speechStatus({transcript: false, speech_state: "engine_empty"}),
          read: m.speechStatus({transcript: true, language: "zh"}),
        };
    """)
    assert "0:53" in out["intro"]
    assert "few minutes" not in out["intro"]
    assert out["before"] == "Estimating time left"
    assert out["measured"].startswith("About 0:17 left")
    assert out["elapsed"].startswith("0:20 elapsed")
    assert out["eta"] is not None and out["eta"] >= 1
    assert out["smooth"] == [61, 80]
    assert out["off"] == "Off at import"
    assert out["empty"] == "Engine returned nothing"
    assert out["read"] == "Read · zh"
