"""Source Check: OCR geometry, tracklets, kinds, signals and routes."""

from __future__ import annotations

import json
import math
import wave
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import detect
import job_queue
import pipeline
import routes_check


# ---------------------------------------------------------------- fixtures


def box(x: float, y: float, w: float, h: float) -> dict:
    return {"x": x, "y": y, "w": w, "h": h}


def line(text: str, x=0.1, y=0.8, w=0.8, h=0.08, confidence=0.9) -> dict:
    return {"text": text, "box": box(x, y, w, h), "confidence": confidence}


def scene(
    index: int,
    start: float,
    end: float,
    *,
    speech: str = "",
    ocr: str = "",
    boxes: list[dict] | None = None,
    faces: list[dict] | None = None,
    audio_mean: float = -30.0,
    silence: float = 0.2,
) -> dict:
    return {
        "id": index,
        "start": start,
        "end": end,
        "mid": (start + end) / 2,
        "dur": end - start,
        "speech": speech,
        "ocr": ocr,
        "ocr_boxes": boxes or [],
        "faces": faces or [],
        "audio_mean": audio_mean,
        "silence": silence,
    }


def job_record(job_id: str = "job1", root: Path | None = None) -> dict:
    root = root or Path("/tmp")
    return {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": str(root / "source.mp4"),
            "name": "source.mp4",
            "duration": 20.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "size": 30_000_000,
            "has_audio": True,
        },
        "options": {},
        "analysis": {
            "scene_count": 2,
            "engine": {"whisper": True, "transcript_language": "en"},
            "transcript": {"language": "en", "text": "hello", "segments": 2},
            "audio": {"available": True},
            "scenes": [
                scene(
                    0, 0.0, 10.0, speech="hello there", ocr="burned caption",
                    boxes=[line("burned caption")],
                ),
                scene(1, 10.0, 20.0, speech="second beat"),
            ],
        },
        "renders": {},
    }


def sample_payload(rows: list[tuple[float, list[dict]]], fps: float = 0.5) -> dict:
    frames = []
    for index, (moment, lines) in enumerate(rows):
        frames.append({
            "index": index,
            "file": f"{index + 1:06d}.jpg",
            "t": moment,
            "start": moment,
            "end": round(moment + 1.0 / fps, 3),
            "text": lines,
        })
    return {"frames": frames, "vision": True, "fps": fps, "duration": 60.0}


def subtitle_rows(count: int = 5, *, start: float = 10.0) -> list[tuple[float, list[dict]]]:
    return [
        (start + index * 2.0, [line(f"caption number {index}")])
        for index in range(count)
    ]


def observations(rows: list[tuple[float, list[dict]]], fps: float = 0.5) -> list[dict]:
    return detect.observations_from_samples(sample_payload(rows, fps)["frames"])


@pytest.fixture
def check_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    sources = data / "sources"
    sources.mkdir()
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    job = job_record("job1", tmp_path)
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return SimpleNamespace(
        tmp_path=tmp_path, jobs=jobs, job=job, directory=directory, job_id=job["id"],
    )


class InlineExecutor:
    """Run scheduler work on the calling thread so route tests stay fast."""

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            future.set_exception(exc)
        return future

    def shutdown(self, *args, **kwargs):
        return None


@pytest.fixture
def inline_check(monkeypatch):
    scheduler = job_queue.Scheduler("check-test", executor=InlineExecutor())
    monkeypatch.setattr(routes_check, "CHECK_POOL", scheduler)
    return scheduler


# ---------------------------------------------------------------- OCR geometry


def test_ocr_lines_keep_box_text_and_confidence():
    record = {
        "text": [
            {"text": " Hello  world ", "confidence": 0.91, "box": box(0.1, 0.2, 0.3, 0.04)},
            {"text": "second", "confidence": 0.42, "box": box(0.4, 0.2, 0.2, 0.04)},
        ],
    }
    lines = pipeline.ocr_lines(record)
    assert [item["text"] for item in lines] == ["Hello world", "second"]
    assert lines[0]["box"] == {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.04}
    assert lines[0]["confidence"] == 0.91


def test_ocr_lines_drop_low_confidence_short_text_and_bad_boxes():
    record = {
        "text": [
            {"text": "x", "confidence": 0.9, "box": box(0.1, 0.1, 0.1, 0.1)},
            {"text": "faint", "confidence": 0.1, "box": box(0.1, 0.1, 0.1, 0.1)},
            {"text": "no box", "confidence": 0.8},
            {"text": "off frame", "confidence": 0.8, "box": box(1.2, 0.1, 0.3, 0.1)},
            {"text": "zero size", "confidence": 0.8, "box": box(0.2, 0.2, 0, 0.1)},
        ],
    }
    lines = pipeline.ocr_lines(record)
    assert [item["text"] for item in lines] == ["no box", "off frame", "zero size"]
    assert all(item["box"] is None for item in lines)


def test_apply_scene_read_keeps_line_boxes(tmp_path):
    scene_record = scene(0, 0.0, 4.0)
    record = {
        "text": [
            {"text": "first line", "confidence": 0.9, "box": box(0.1, 0.7, 0.8, 0.06)},
            {"text": "second line", "confidence": 0.8, "box": box(0.2, 0.78, 0.6, 0.06)},
        ],
        "faces": [{"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.2, "confidence": 0.9}],
        "salient": [],
    }
    pipeline._apply_scene_read(scene_record, tmp_path, record, True)
    assert scene_record["ocr"] == "first line · second line"
    assert [item["text"] for item in scene_record["ocr_boxes"]] == [
        "first line", "second line",
    ]
    assert scene_record["ocr_boxes"][1]["box"] == box(0.2, 0.78, 0.6, 0.06)
    assert scene_record["ocr_confidence"] == pytest.approx(0.85)
    assert scene_record["faces"] == record["faces"]


def test_apply_scene_read_without_text_keeps_empty_boxes(tmp_path):
    scene_record = scene(0, 0.0, 4.0)
    pipeline._apply_scene_read(scene_record, tmp_path, {}, True)
    assert scene_record["ocr"] == ""
    assert scene_record["ocr_boxes"] == []
    assert scene_record["ocr_confidence"] == 0.0


def test_apply_scene_read_read_text_off_clears_geometry(tmp_path):
    scene_record = scene(0, 0.0, 4.0)
    record = {"text": [line("caption")]}
    pipeline._apply_scene_read(scene_record, tmp_path, record, False)
    assert scene_record["ocr"] == ""
    assert scene_record["ocr_boxes"] == []


# ---------------------------------------------------------------- sampled pass


def _fake_extract(monkeypatch, duration: float, create: int | None = None):
    calls = {}

    def fake_run(cmd, timeout=None):
        calls["cmd"] = cmd
        target = Path(cmd[-1])
        pattern = target.name
        directory = target.parent
        directory.mkdir(parents=True, exist_ok=True)
        cadence = float(cmd[cmd.index("-vf") + 1].split(",")[0].split("=")[1])
        total = int(duration * cadence)
        total = min(total, create if create is not None else total)
        for index in range(1, total + 1):
            (directory / (pattern % index)).write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pipeline, "_ffmpeg", lambda: "/usr/bin/false-ffmpeg")
    monkeypatch.setattr(pipeline, "_run", fake_run)
    return calls


def test_extract_text_frames_reads_two_a_second_and_reports_windows(monkeypatch, tmp_path):
    calls = _fake_extract(monkeypatch, 20.0)
    frames = pipeline.extract_text_frames("/tmp/source.mp4", tmp_path, 20.0)
    assert len(frames) == 40
    assert frames[0]["start"] == 0.0
    assert frames[1]["start"] == 0.5
    assert frames[-1]["end"] == 20.0
    assert "fps=2.0000" in calls["cmd"][calls["cmd"].index("-vf") + 1]


def test_extract_text_frames_lowers_cadence_for_long_sources(monkeypatch, tmp_path):
    _fake_extract(monkeypatch, 20.0, create=4)
    frames = pipeline.extract_text_frames(
        "/tmp/source.mp4", tmp_path, 20.0, max_frames=4,
    )
    assert len(frames) == 4
    assert frames[1]["start"] == pytest.approx(5.0)


def test_extract_text_frames_offsets_a_scene_window(monkeypatch, tmp_path):
    calls = _fake_extract(monkeypatch, 20.0, create=8)
    frames = pipeline.extract_text_frames(
        "/tmp/source.mp4", tmp_path, 20.0, start=4.0, end=8.0,
    )
    assert frames[0]["start"] == 4.0
    assert frames[-1]["end"] == 8.0
    assert calls["cmd"][calls["cmd"].index("-ss") + 1] == "4.000"
    assert calls["cmd"][calls["cmd"].index("-t") + 1] == "4.000"


def test_extract_text_frames_returns_empty_for_zero_duration(monkeypatch, tmp_path):
    _fake_extract(monkeypatch, 0.0)
    assert pipeline.extract_text_frames("/tmp/source.mp4", tmp_path, 0.0) == []


def test_read_text_samples_marks_vision_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline, "extract_text_frames",
        lambda *args, **kwargs: [{
            "index": 0, "file": "000001.jpg", "t": 0.0,
            "start": 0.0, "end": 2.0, "ocr_available": True,
        }],
    )
    monkeypatch.setattr(pipeline.vision, "available", lambda: False)
    result = pipeline.read_text_samples("/tmp/source.mp4", tmp_path, 10.0)
    assert result["vision"] is False
    assert result["frames"][0]["text"] == []


def test_read_text_samples_treats_an_empty_probe_as_unavailable(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(
        pipeline, "extract_text_frames",
        lambda *args, **kwargs: [{
            "index": 0, "file": "000001.jpg", "t": 0.0,
            "start": 0.0, "end": 2.0, "ocr_available": True,
        }],
    )
    monkeypatch.setattr(pipeline.vision, "available", lambda: True)
    monkeypatch.setattr(pipeline.vision, "probe_images", lambda directory, files=None: {})
    result = pipeline.read_text_samples("/tmp/source.mp4", tmp_path, 10.0)
    assert result["vision"] is False


def test_read_text_samples_maps_records_to_frames(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline, "extract_text_frames",
        lambda *args, **kwargs: [{
            "index": 0, "file": "000001.jpg", "t": 0.0,
            "start": 0.0, "end": 2.0, "ocr_available": True,
        }],
    )
    monkeypatch.setattr(pipeline.vision, "available", lambda: True)
    monkeypatch.setattr(
        pipeline.vision, "probe_images",
        lambda directory, files=None: {"000001.jpg": {"text": [line("hello")], "width": 960, "height": 540}},
    )
    result = pipeline.read_text_samples("/tmp/source.mp4", tmp_path, 10.0)
    assert result["vision"] is True
    assert result["frames"][0]["text"][0]["text"] == "hello"
    assert not (tmp_path / "check" / "frames").exists()


# ---------------------------------------------------------------- tracklets


def test_merge_lines_joins_two_caption_lines():
    merged = detect.merge_lines(
        [
            line("first line of the caption", 0.15, 0.76, 0.7, 0.06),
            line("second line", 0.2, 0.83, 0.6, 0.06),
        ],
        start=0.0, end=2.0, source="sample",
    )
    assert len(merged) == 1
    assert merged[0]["box"] == box(0.15, 0.76, 0.7, 0.13)
    assert "second line" in merged[0]["text"]


def test_merge_lines_keeps_far_apart_elements_separate():
    merged = detect.merge_lines(
        [
            line("caption", 0.1, 0.8, 0.8, 0.08),
            line("@handle", 0.8, 0.05, 0.15, 0.05),
        ],
        start=0.0, end=2.0, source="sample",
    )
    assert len(merged) == 2


def test_tracklet_contract_fields_and_ranges():
    rows = subtitle_rows(5)
    tracklets = detect.build_tracklets(observations(rows), 30.0)
    assert len(tracklets) == 1
    tracklet = tracklets[0]
    assert set(tracklet) >= {
        "id", "kind", "box", "ranges", "text_sample", "confidence",
    }
    assert tracklet["id"].startswith("trk_")
    assert tracklet["kind"] == "subtitle"
    assert tracklet["ranges"] == [{"start": 9.0, "end": 19.0}]
    assert tracklet["box"] == box(0.1, 0.8, 0.8, 0.08)
    assert 0.0 <= tracklet["confidence"] <= 1.0


def test_time_off_screen_is_not_covered():
    rows = subtitle_rows(3, start=0.0) + subtitle_rows(2, start=10.0)
    tracklets = detect.build_tracklets(observations(rows), 30.0, max_gap=5.0)
    assert [item for tracklet in tracklets for item in tracklet["ranges"]] == [
        {"start": 0.0, "end": 5.0}, {"start": 9.0, "end": 13.0},
    ]


def _timed_lines(*lines):
    """Half-second samples: (text, x, w, first, last) for each line."""
    observed = []
    for text, x, w, first, last in lines:
        t = first
        while t <= last:
            observed.append({
                "text": text, "box": box(x, 0.8, w, 0.04), "confidence": 0.9,
                "start": t, "end": t + 0.5, "t": t, "source": "sample",
            })
            t += 0.5
    return observed


def test_each_line_has_its_own_tight_box_and_time():
    tracklets = detect.build_tracklets(_timed_lines(
        ("the first line of words", 0.3, 0.4, 1.0, 3.0),
        ("a very much longer second subtitle line here", 0.05, 0.9, 3.5, 6.0),
    ), 30.0)
    assert len(tracklets) == 2
    short, long = tracklets
    assert short["box"]["x"] == 0.3 and short["box"]["w"] == 0.4
    assert long["box"]["x"] == 0.05 and long["box"]["w"] == 0.9
    assert short["ranges"] == [{"start": 0.75, "end": 3.25}]
    assert long["ranges"] == [{"start": 3.25, "end": 6.25}]
    assert short["kind"] == long["kind"]
    assert short["id"] != long["id"]


def test_an_ocr_misread_stays_in_the_same_line():
    tracklets = detect.build_tracklets(_timed_lines(
        ("luckin coffee is here", 0.3, 0.4, 1.0, 2.0),
        ("Iuckin coffee is here", 0.3, 0.4, 2.5, 3.0),
    ), 30.0)
    assert len(tracklets) == 1
    assert tracklets[0]["ranges"] == [{"start": 0.75, "end": 3.25}]


def test_a_scan_ignores_the_four_second_scene_readings(tmp_path):
    job = job_record()
    job["analysis"]["scenes"] = [{
        "start": 0.0, "end": 20.0, "mid": 10.0, "ocr": "wide words",
        "ocr_boxes": [{"text": "wide words", "box": box(0.0, 0.5, 1.0, 0.2), "confidence": 0.9}],
    }]

    def sampler(path, job_dir, duration, *, fps, max_frames):
        return sample_payload(subtitle_rows(2, start=0.0))

    report = detect.run_check("job1", job, tmp_path, sampler=sampler, audio_extractor=None)
    assert all(item["box"]["w"] < 1.0 for item in report["tracklets"])


def test_tracklet_ids_are_deterministic_by_time():
    top = (0.0, [line("TOP TITLE", 0.2, 0.1, 0.6, 0.2)])
    bottom = (0.0, [line("caption", 0.1, 0.8, 0.8, 0.08)])
    first = detect.build_tracklets(observations([bottom, top]), 20.0)
    second = detect.build_tracklets(observations([top, bottom]), 20.0)
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert [item["text_sample"] for item in first] == [
        item["text_sample"] for item in second
    ]


def test_build_tracklets_respects_the_limit():
    rows = [
        (index * 2.0, [line("TOP", 0.2, 0.05, 0.5, 0.1), line("BOTTOM", 0.2, 0.85, 0.5, 0.05)])
        for index in range(3)
    ]
    tracklets = detect.build_tracklets(observations(rows), 10.0, max_tracklets=1)
    assert len(tracklets) == 1


def test_subtitle_kind_from_changing_lower_band_text():
    tracklet = detect.build_tracklets(observations(subtitle_rows(5)), 30.0)[0]
    assert tracklet["kind"] == "subtitle"


def test_title_kind_from_large_mid_frame_text():
    rows = [
        (index * 2.0, [line("HOW I DID IT", 0.1, 0.2, 0.8, 0.18)])
        for index in range(4)
    ]
    tracklet = detect.build_tracklets(observations(rows), 10.0)[0]
    assert tracklet["kind"] == "title"


def test_lower_third_is_static_and_narrower_than_a_caption():
    rows = [(index * 2.0, [line("Jane Doe · Founder", 0.08, 0.72, 0.4, 0.08)]) for index in range(4)]
    tracklet = detect.build_tracklets(observations(rows), 20.0)[0]
    assert tracklet["kind"] == "lower_third"


def test_credit_kind_from_small_bottom_text():
    rows = [(index * 2.0, [line("edited by sam", 0.4, 0.88, 0.2, 0.03, 0.6)]) for index in range(3)]
    tracklet = detect.build_tracklets(observations(rows), 20.0)[0]
    assert tracklet["kind"] == "credit"


def test_handle_kind_for_small_corner_handle():
    rows = [(index * 2.0, [line("@myhandle", 0.02, 0.03, 0.15, 0.05)]) for index in range(4)]
    tracklet = detect.build_tracklets(observations(rows), 20.0)[0]
    assert tracklet["kind"] == "handle_or_logo"


def test_handle_kind_for_persistent_corner_logo():
    rows = [(index * 2.0, [line("ACME", 0.82, 0.04, 0.12, 0.05)]) for index in range(4)]
    tracklet = detect.build_tracklets(observations(rows), 20.0)[0]
    assert tracklet["kind"] == "handle_or_logo"


def test_watermark_kind_for_small_platform_mark():
    rows = [(index * 2.0, [line("TikTok", 0.84, 0.05, 0.13, 0.05)]) for index in range(4)]
    tracklet = detect.build_tracklets(observations(rows), 20.0)[0]
    assert tracklet["kind"] == "watermark"


def test_watermark_literal_is_refused_even_in_the_middle():
    rows = [(index * 2.0, [line("WATERMARK", 0.35, 0.45, 0.3, 0.08)]) for index in range(2)]
    tracklet = detect.build_tracklets(observations(rows), 10.0)[0]
    assert tracklet["kind"] == "watermark"


def test_large_platform_name_is_a_title_not_a_watermark():
    rows = [(0.0, [line("TikTok made me buy it", 0.1, 0.2, 0.8, 0.18)])] * 2
    tracklet = detect.build_tracklets(observations(rows), 10.0)[0]
    assert tracklet["kind"] == "title"


def test_untracked_scene_text_without_boxes_still_counts_as_text():
    scenes = [scene(0, 0.0, 5.0, ocr="no geometry here", boxes=[])]
    items = detect.observations_from_scenes(scenes)
    assert len(items) == 1
    tracklets = detect.build_tracklets(items, 5.0)
    assert tracklets[0]["approximate"] is True
    assert tracklets[0]["kind"] == "subtitle"


# ---------------------------------------------------------------- signals


def test_speech_signal_uses_scene_transcript_coverage():
    scenes = [
        scene(0, 0.0, 5.0, speech="hello"),
        scene(1, 5.0, 10.0),
        scene(2, 10.0, 20.0, speech="more"),
    ]
    signal = detect.speech_signal(scenes, 20.0)
    assert signal["available"] is True
    assert signal["speech_seconds"] == 15.0
    assert signal["speech_ratio"] == 0.75
    assert signal["ranges"] == [{"start": 0.0, "end": 5.0}, {"start": 10.0, "end": 20.0}]


def test_faces_signal_coverage_and_count():
    faces = [{"x": 0.3, "y": 0.2, "w": 0.2, "h": 0.2, "confidence": 0.9}]
    scenes = [
        scene(0, 0.0, 5.0, faces=faces),
        scene(1, 5.0, 10.0),
        scene(2, 10.0, 15.0, faces=faces + faces),
    ]
    signal = detect.faces_signal(scenes, 20.0)
    assert signal["present"] is True
    assert signal["count"] == 2
    assert signal["coverage"] == 0.5
    assert signal["ranges"] == [{"start": 0.0, "end": 5.0}, {"start": 10.0, "end": 15.0}]
    assert signal["boxes"] == [{
        "x": 0.3, "y": 0.2, "w": 0.2, "h": 0.2, "confidence": 0.9,
    }]


def test_quality_signal_flags_low_resolution_and_low_bitrate():
    quality = detect.quality_signal({
        "width": 640, "height": 360, "fps": 30.0, "duration": 60.0,
        "size": 1_000_000,
    })
    codes = [item["code"] for item in quality["issues"]]
    assert "low_resolution" in codes
    assert "low_bitrate" in codes
    assert quality["orientation"] == "landscape"
    assert quality["bitrate_mbps"] == pytest.approx(0.133, abs=0.01)


def test_music_from_scenes_detects_steady_non_speech_energy():
    scenes = [
        scene(0, 0.0, 10.0, speech="talking", audio_mean=-12.0),
        scene(1, 10.0, 20.0, speech="", audio_mean=-20.0, silence=0.1),
    ]
    signal = detect.music_from_scenes(scenes)
    assert signal["available"] is True
    assert signal["present"] is True
    assert signal["score"] == 1.0


def test_music_from_scenes_silence_is_not_music():
    scenes = [scene(0, 0.0, 10.0, audio_mean=-60.0, silence=1.0)]
    signal = detect.music_from_scenes(scenes)
    assert signal["present"] is False


def _write_wav(path: Path, seconds: float, amplitude: float, frequency: float = 440.0) -> Path:
    rate = 16000
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        values = []
        for index in range(frames):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * index / rate))
            values.append(value.to_bytes(2, "little", signed=True))
        writer.writeframes(b"".join(values))
    return path


def test_music_from_wav_detects_a_steady_tone(tmp_path):
    path = _write_wav(tmp_path / "tone.wav", 6.0, 0.25)
    signal = detect.music_from_wav(path)
    assert signal["available"] is True
    assert signal["present"] is True
    assert signal["score"] >= 0.45


def test_music_from_wav_ignores_silence(tmp_path):
    path = _write_wav(tmp_path / "silence.wav", 6.0, 0.0)
    signal = detect.music_from_wav(path)
    assert signal["available"] is True
    assert signal["present"] is False


def test_music_from_wav_excludes_speech_spans(tmp_path):
    path = _write_wav(tmp_path / "speech.wav", 6.0, 0.3)
    signal = detect.music_from_wav(path, [{"start": 0.0, "end": 6.0}])
    assert signal["available"] is False


# ---------------------------------------------------------------- report


def report_for(job: dict, rows: list[tuple[float, list[dict]]] | None = None, **kwargs):
    observations_ = detect.observations_from_scenes(job["analysis"]["scenes"])
    if rows:
        observations_ += observations(rows)
    sampled = kwargs.pop("sampled", {"ran": True, "frames": 10, "vision": True})
    kwargs.setdefault("settings", {"rights": {"lock": True}})
    return detect.build_report(job, observations_, sampled=sampled, **kwargs)


def test_recommendation_clean_then_compose_when_text_is_found():
    job = job_record()
    report = report_for(job, subtitle_rows(4, start=0.0))
    assert report["recommendation"] == "clean_then_compose"
    assert report["text"]["present"] is True
    assert report["text"]["confirmed"] is True


def test_recommendation_compose_when_no_text_is_found():
    job = job_record()
    job["analysis"]["scenes"] = [
        scene(0, 0.0, 10.0, speech="talking"),
        scene(1, 10.0, 20.0, speech="more"),
    ]
    report = report_for(job)
    assert report["recommendation"] == "compose"
    assert report["text"]["present"] is False


def test_recommendation_music_first_for_a_silent_source():
    job = job_record()
    job["source"]["has_audio"] = False
    job["analysis"]["scenes"] = [scene(0, 0.0, 20.0, audio_mean=-20.0, silence=0.1)]
    job["analysis"]["transcript"] = None
    job["analysis"]["engine"] = {}
    report = report_for(job)
    assert report["recommendation"] == "music_first"


def test_unconfirmed_text_never_reports_a_clean_source():
    job = job_record()
    job["analysis"]["scenes"] = [scene(0, 0.0, 20.0)]
    report = report_for(job, sampled={"ran": True, "frames": 0, "vision": False})
    assert report["text"]["confirmed"] is False
    assert report["text"]["present"] is False
    codes = [item["code"] for item in report["warnings"]]
    assert "text_unconfirmed" in codes
    assert any(
        "unconfirmed" in reason.lower()
        for reason in report["recommendation_reasons"]
    )


def test_watermark_is_flagged_and_can_be_cleaned():
    job = job_record()
    rows = [{"text": "TikTok", "box": box(0.84, 0.05, 0.13, 0.05), "confidence": 0.9}]
    report = report_for(job, [(index * 2.0, rows) for index in range(4)])
    assert report["clean_prefill"][0]["action"] != "refused"
    warning = next(
        item for item in report["warnings"] if item["code"] == "watermark_detected"
    )
    assert warning["severity"] == "warning"


def test_handle_requires_attestation_and_stays_disabled():
    job = job_record()
    rows = [line("@myhandle", 0.02, 0.03, 0.15, 0.05)]
    report = report_for(job, [(index * 2.0, rows) for index in range(4)])
    entry = report["clean_prefill"][0]
    assert entry["kind"] == "handle_or_logo"
    assert entry["action"] == "crop_guard"
    assert entry["enabled"] is False
    assert entry["blocked"] == "attestation_required"
    assert "handle_requires_attestation" in [item["code"] for item in report["warnings"]]


def test_attestation_unlocks_the_clean_layer_but_not_handles_by_default():
    job = job_record()
    rows = [line("@myhandle", 0.02, 0.03, 0.15, 0.05)]
    report = report_for(
        job, [(index * 2.0, rows) for index in range(4)],
        attestation=True,
    )
    assert report["rights"] == {"attested": True, "source": "check_request"}
    assert report["policy"]["clean_allowed"] is True
    entry = report["clean_prefill"][0]
    assert entry["blocked"] is None
    assert entry["enabled"] is False  # off by default even when attested
    assert "rights_not_attested" not in [item["code"] for item in report["warnings"]]


def test_attestation_from_the_job_is_read():
    job = job_record()
    job["rights"] = {"attested": "true"}
    report = report_for(job)
    assert report["rights"] == {"attested": True, "source": "job"}
    assert report["policy"]["clean_allowed"] is True


def test_cleanup_block_reason_keys_on_the_detected_kind():
    locked = {"rights": {"lock": True}}
    assert detect.cleanup_block_reason(
        "watermark", attested=True, settings=locked,
    ) is None
    assert detect.cleanup_block_reason(
        "watermark", attested=False, settings=locked,
    ) == "attestation_required"
    assert (
        detect.cleanup_block_reason(
            "handle_or_logo", attested=False, settings=locked,
        )
        == "attestation_required"
    )
    assert detect.cleanup_block_reason(
        "handle_or_logo", attested=True, settings=locked,
    ) is None
    assert (
        detect.cleanup_block_reason("subtitle", attested=False, settings=locked)
        == "rights_not_attested"
    )
    assert detect.cleanup_block_reason(
        "subtitle", attested=True, settings=locked,
    ) is None


def test_prefill_opens_with_the_lock_off_but_keeps_the_hard_rules():
    tracklets = [
        {
            "id": "trk_sub", "kind": "subtitle",
            "box": {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09},
            "ranges": [{"start": 0.0, "end": 4.0}], "confidence": 0.9,
        },
        {
            "id": "trk_water", "kind": "watermark",
            "box": {"x": 0.84, "y": 0.05, "w": 0.13, "h": 0.05},
            "ranges": [{"start": 0.0, "end": 4.0}], "confidence": 0.9,
        },
        {
            "id": "trk_handle", "kind": "handle_or_logo",
            "box": {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05},
            "ranges": [{"start": 0.0, "end": 4.0}], "confidence": 0.9,
        },
    ]
    entries = detect.clean_prefill(
        tracklets, attested=False, settings={"rights": {"lock": False}},
    )
    by_id = {item["tracklet_id"]: item for item in entries}
    assert by_id["trk_sub"]["enabled"] is True
    assert by_id["trk_sub"]["blocked"] is None
    assert by_id["trk_water"]["blocked"] == "attestation_required"
    assert by_id["trk_water"]["enabled"] is False
    assert by_id["trk_handle"]["blocked"] == "attestation_required"
    assert by_id["trk_handle"]["enabled"] is False


def test_lock_off_report_does_not_nag_for_the_rights_note():
    job = job_record()
    report = report_for(
        job,
        subtitle_rows(4, start=0.0),
        settings={"rights": {"lock": False}},
    )
    assert "rights_not_attested" not in [item["code"] for item in report["warnings"]]
    assert report["policy"]["clean_allowed"] is True
    entry = next(item for item in report["clean_prefill"] if item["kind"] == "subtitle")
    assert entry["enabled"] is True


def test_subtitle_prefill_uses_delogo_in_the_caption_zone():
    job = job_record()
    report = report_for(job, subtitle_rows(4, start=0.0))
    entry = next(item for item in report["clean_prefill"] if item["kind"] == "subtitle")
    assert entry["action"] == "delogo"
    assert entry["enabled"] is False  # rights not attested


def test_mid_frame_subtitle_warns_and_uses_delogo():
    job = job_record()
    rows = [
        (index * 2.0, [line(f"caption {index}", 0.1, 0.5, 0.8, 0.08)])
        for index in range(4)
    ]
    report = report_for(job, rows)
    entry = next(item for item in report["clean_prefill"] if item["kind"] == "subtitle")
    assert entry["action"] == "delogo"
    assert "mid_frame_text" in [item["code"] for item in report["warnings"]]


def test_speech_unknown_warns_without_a_transcript():
    job = job_record()
    job["analysis"]["transcript"] = None
    job["analysis"]["engine"] = {}
    job["analysis"]["scenes"] = [scene(0, 0.0, 20.0)]
    report = report_for(job)
    codes = [item["code"] for item in report["warnings"]]
    assert "speech_unknown" in codes


def test_report_includes_audio_faces_and_quality():
    job = job_record()
    job["analysis"]["scenes"][1]["faces"] = [
        {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.2, "confidence": 0.9},
    ]
    job["analysis"]["scenes"][1]["speech"] = ""
    report = report_for(job)
    assert report["audio"]["speech_ratio"] == 0.5
    assert report["faces"]["present"] is True
    assert report["quality"]["width"] == 1920
    assert report["schema"] == detect.SCHEMA_VERSION


def test_write_and_load_report_round_trip(tmp_path):
    job = job_record()
    report = report_for(job)
    path = detect.write_report(tmp_path, report)
    assert path.name == detect.REPORT_FILE
    assert detect.load_report(tmp_path) == report


def test_state_report_is_not_complete():
    report = detect.state_report({"id": "j1", "source": {"duration": 10.0}}, "running")
    assert report["status"] == "running"
    assert report["complete"] is False
    assert report["recommendation"] is None
    assert report["text"]["present"] is None


# ---------------------------------------------------------------- orchestration


def test_run_check_samples_text_and_persists(tmp_path):
    job = job_record()
    calls = {}

    def sampler(path, job_dir, duration, *, fps, max_frames):
        calls.update({"path": path, "duration": duration, "fps": fps})
        return sample_payload(subtitle_rows(4, start=0.0))

    report = detect.run_check(
        "job1", job, tmp_path, sampler=sampler, audio_extractor=None,
    )
    assert calls == {"path": job["source"]["path"], "duration": 20.0, "fps": 2.0}
    assert report["tracklets"][0]["kind"] == "subtitle"
    stored = detect.load_report(tmp_path)
    assert stored == report
    assert report["engine"]["sampled_pass"] is True


def test_run_check_passes_a_scene_window_to_the_sampler(tmp_path):
    job = job_record()
    calls = {}

    def sampler(path, job_dir, duration, *, fps, max_frames, **kwargs):
        calls.update({"duration": duration, **kwargs})
        return sample_payload(subtitle_rows(2, start=5.0))

    report = detect.run_check(
        "job1", job, tmp_path, sampler=sampler, audio_extractor=None,
        start=4.0, end=8.0,
    )
    assert calls["duration"] == 20.0
    assert calls["start"] == 4.0 and calls["end"] == 8.0
    assert report["scope"] == {"start": 4.0, "end": 8.0}
    assert report["status"] == "ready"


def test_run_check_survives_a_sampler_failure(tmp_path):
    job = job_record()

    def sampler(*args, **kwargs):
        raise RuntimeError("ffmpeg missing")

    report = detect.run_check("job1", job, tmp_path, sampler=sampler)
    assert report["status"] == "ready"
    assert report["text"]["confirmed"] is False
    codes = [item["code"] for item in report["warnings"]]
    assert "sampled_pass_failed" in codes
    assert report["engine"]["sampler_error"] == "ffmpeg missing"


def test_run_check_skips_sampling_when_disabled(tmp_path):
    job = job_record()
    report = detect.run_check(
        "job1", job, tmp_path, sampler=None, sample_text=False,
    )
    assert report["text"]["confirmed"] is False
    assert report["engine"]["sampled_pass"] is False
    assert report["text"]["present"] is True  # scene OCR still found text
    assert report["tracklets"][0]["kind"] == "subtitle"


def test_run_check_uses_audio_when_available(tmp_path):
    job = job_record()
    for item in job["analysis"]["scenes"]:
        item["speech"] = ""
    wav = _write_wav(tmp_path / "bed.wav", 6.0, 0.2)
    calls = []

    def extractor(path, has_audio, job_dir):
        calls.append((path, has_audio))
        return wav

    report = detect.run_check(
        "job1", job, tmp_path,
        sampler=lambda *args, **kwargs: sample_payload([]),
        audio_extractor=extractor,
    )
    assert calls == [(job["source"]["path"], True)]
    assert report["audio"]["music"]["method"] == "energy_stability"
    assert not wav.exists()


# ---------------------------------------------------------------- routes


def fake_pipeline_sampler(*args, **kwargs):
    return sample_payload(subtitle_rows(4, start=0.0))


def test_check_routes_run_and_return_the_report(check_env, inline_check, monkeypatch):
    monkeypatch.setattr(pipeline, "read_text_samples", fake_pipeline_sampler)
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args, **kwargs: None)
    client = TestClient(app.app)

    started = client.post(f"/api/jobs/{check_env.job_id}/check", json={})
    assert started.status_code == 200
    report = started.json()
    assert report["status"] == "ready"
    assert report["recommendation"] == "clean_then_compose"
    assert report["tracklets"]
    assert (check_env.directory / "check" / "source_report.json").exists()

    fetched = client.get(f"/api/jobs/{check_env.job_id}/check")
    assert fetched.status_code == 200
    assert fetched.json() == report

    stored = app.load_job(check_env.job_id)
    assert stored["check"]["status"] == "ready"
    assert stored["check"]["tracklet_count"] == len(report["tracklets"])


def test_check_post_caches_the_report_until_forced(check_env, inline_check, monkeypatch):
    calls = []

    def sampler(*args, **kwargs):
        calls.append(1)
        return sample_payload(subtitle_rows(4, start=0.0))

    monkeypatch.setattr(pipeline, "read_text_samples", sampler)
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args, **kwargs: None)
    client = TestClient(app.app)

    assert client.post(f"/api/jobs/{check_env.job_id}/check").status_code == 200
    assert client.post(f"/api/jobs/{check_env.job_id}/check").status_code == 200
    assert len(calls) == 1
    assert client.post(
        f"/api/jobs/{check_env.job_id}/check", json={"force": True},
    ).status_code == 200
    assert len(calls) == 2


def test_check_post_recovers_from_a_stale_running_record(
    check_env, inline_check, monkeypatch,
):
    monkeypatch.setattr(pipeline, "read_text_samples", fake_pipeline_sampler)
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args, **kwargs: None)
    job = app.load_job(check_env.job_id)
    job["check"] = {"status": "running", "task_id": "gone"}
    app.save_job(job)
    client = TestClient(app.app)
    response = client.post(f"/api/jobs/{check_env.job_id}/check")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_check_post_rejects_an_unready_job(check_env, inline_check):
    job = app.load_job(check_env.job_id)
    job["status"] = "scanning"
    app.save_job(job)
    client = TestClient(app.app)
    response = client.post(f"/api/jobs/{check_env.job_id}/check")
    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


def test_check_get_before_run_is_404(check_env):
    client = TestClient(app.app)
    response = client.get(f"/api/jobs/{check_env.job_id}/check")
    assert response.status_code == 404


def test_check_unknown_job_is_404(inline_check):
    client = TestClient(app.app)
    assert client.get("/api/jobs/missing/check").status_code == 404
    assert client.post("/api/jobs/missing/check").status_code == 404


def test_check_worker_failure_is_visible(check_env, inline_check, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("check exploded")

    monkeypatch.setattr(routes_check.detect, "run_check", boom)
    client = TestClient(app.app)
    response = client.post(f"/api/jobs/{check_env.job_id}/check")
    assert response.status_code == 500
    assert response.json()["status"] == "failed"

    fetched = client.get(f"/api/jobs/{check_env.job_id}/check")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "failed"
    assert "check exploded" in fetched.json()["error"]
    stored = app.load_job(check_env.job_id)
    assert stored["check"]["status"] == "failed"


def test_check_body_rejects_unknown_fields(check_env, inline_check):
    client = TestClient(app.app)
    response = client.post(
        f"/api/jobs/{check_env.job_id}/check", json={"bogus": 1},
    )
    assert response.status_code == 422


def test_check_body_validates_fps(check_env, inline_check):
    client = TestClient(app.app)
    response = client.post(
        f"/api/jobs/{check_env.job_id}/check", json={"fps": 30},
    )
    assert response.status_code == 422
