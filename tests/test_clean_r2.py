"""Clean R2: honest time before and during a fill, and a real one-second test."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

import render
import textfill

ROOT = Path(__file__).resolve().parents[1]
CLEAN = (ROOT / "static/studio/edit/layers/clean.js").read_text(encoding="utf-8")
FINISH = (ROOT / "static/studio/finish.js").read_text(encoding="utf-8")
INDEX = (ROOT / "static/studio/edit/index.js").read_text(encoding="utf-8")
PREVIEW = (ROOT / "static/studio/edit/preview.js").read_text(encoding="utf-8")
META = {"width": 720, "height": 1280, "fps": 30.0, "fingerprint": "f"}
BOTTOM = {"id": "a", "box": {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.05}, "ranges": []}
TOP = {"id": "b", "box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.05}, "ranges": []}


def _estimate(tmp_path, layers, method="sttn"):
    return textfill.estimate_span(
        meta=META, start=0.0, duration=2.0, layers=layers, method=method,
        cache_dir=tmp_path / "fill", data_root=tmp_path,
    )


def test_sttn_cost_counts_strips_and_lama_counts_frames(tmp_path):
    assert _estimate(tmp_path, [BOTTOM])["units"] == 60
    assert _estimate(tmp_path, [BOTTOM, TOP])["units"] == 120
    assert _estimate(tmp_path, [BOTTOM, TOP], "lama")["units"] == 60


def test_frames_outside_the_ranges_cost_nothing(tmp_path):
    late = {**BOTTOM, "ranges": [{"start": 1.0, "end": 2.0}]}
    assert _estimate(tmp_path, [late])["frames"] == 30


def test_a_cached_clip_costs_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    model = tmp_path / textfill.MODEL_FILES["sttn"]
    model.write_bytes(b"x")
    key = textfill.span_key(
        meta=META, start=0.0, duration=2.0, layers=[BOTTOM], method="sttn",
        model_stamp=textfill._model_stamp(model),
    )
    (tmp_path / "fill").mkdir()
    (tmp_path / "fill" / f"{key}.mp4").write_bytes(b"x" * 2048)
    row = _estimate(tmp_path, [BOTTOM])
    assert row["cached"] is True
    summary = textfill.estimate_summary([row], tmp_path)
    assert summary["seconds"] == 0 and "already done" in summary["text"]


def test_summary_is_honest_about_a_first_guess(tmp_path):
    row = {"method": "sttn", "frames": 60, "units": 600, "cached": False}
    summary = textfill.estimate_summary([row], tmp_path)
    assert summary["seconds"] == 2760.0
    assert summary["text"].startswith("AI fill adds up to about 46 min")
    assert "first guess" in summary["text"]


def test_lama_starts_from_a_first_guess(tmp_path):
    row = {"method": "lama", "frames": 60, "units": 60, "cached": False}
    summary = textfill.estimate_summary([row], tmp_path)
    assert summary["unmeasured"] == []
    assert summary["measured"] is False
    assert "first guess" in summary["text"]

def test_no_fill_means_no_sentence(tmp_path):
    assert textfill.estimate_summary([], tmp_path)["text"] == ""


def test_this_machines_rate_replaces_the_seed(tmp_path):
    assert textfill.fill_rate(tmp_path, "sttn") == {"seconds": 4.6, "measured": False}
    assert textfill.fill_rate(tmp_path, "lama") == {"seconds": 1.2, "measured": False}
    # A figure saved before key frames and tight areas is not used.
    (tmp_path / textfill.RATES_FILE).write_text('{"lama": {"seconds": 8.3, "runs": 9}}', encoding="utf-8")
    assert textfill.fill_rate(tmp_path, "lama") == {"seconds": 1.2, "measured": False}
    textfill.record_rate(tmp_path, "lama", 10, 20.0)
    assert textfill.fill_rate(tmp_path, "lama") == {"seconds": 2.0, "measured": True}
    (tmp_path / textfill.RATES_FILE).unlink()
    textfill.record_rate(tmp_path, "sttn", 100, 200.0)
    assert textfill.fill_rate(tmp_path, "sttn") == {"seconds": 2.0, "measured": True}
    textfill.record_rate(tmp_path, "sttn", 100, 400.0)
    assert textfill.fill_rate(tmp_path, "sttn")["seconds"] == 3.0
    row = {"method": "sttn", "frames": 60, "units": 100, "cached": False}
    assert "first guess" not in textfill.estimate_summary([row], tmp_path)["text"]


def test_a_damaged_rate_file_falls_back_to_the_seed(tmp_path):
    (tmp_path / textfill.RATES_FILE).write_text("not json", encoding="utf-8")
    assert textfill.fill_rate(tmp_path, "sttn")["measured"] is False
    textfill.record_rate(tmp_path, "sttn", 10, 20.0)
    assert textfill.fill_rate(tmp_path, "sttn")["seconds"] == 2.0


def test_duration_text_stays_rough():
    assert textfill.duration_text(20) == "under a minute"
    assert textfill.duration_text(2400) == "about 40 min"
    assert textfill.duration_text(7320) == "about 2 h 2 min"
    assert textfill.duration_text(7200) == "about 2 h"


def _fill_pass(tmp_path, monkeypatch, *, cached):
    messages = []
    clock = [1000.0]
    monkeypatch.setattr(render.time, "monotonic", lambda: clock[0])

    def fake_span(**kwargs):
        clock[0] += 100.0
        kwargs["progress"](0.5, "STTN (video) 15/30")
        clock[0] += 100.0
        return {"path": "x", "key": "k", "cached": cached, "method": "sttn"}

    monkeypatch.setattr(textfill, "prepare_span", fake_span)
    monkeypatch.setattr(textfill, "release_fillers", lambda: None)
    monkeypatch.setattr(render, "_ffmpeg", lambda: "ffmpeg")
    segments = [
        {"fill": {"method": "sttn", "layers": []}, "start": 0.0, "frames": 30},
        {"fill": {"method": "sttn", "layers": []}, "start": 1.0, "frames": 30},
    ]
    job_dir = tmp_path / "jobs" / "j"
    job_dir.mkdir(parents=True)
    render._prepare_fills("s.mp4", META, job_dir, segments, lambda value, text: messages.append(text), None)
    return messages


def test_render_progress_shows_time_left(tmp_path, monkeypatch):
    messages = _fill_pass(tmp_path, monkeypatch, cached=False)
    assert "about 5 min left" in messages[0]
    assert "left" in messages[1]


def test_prepare_span_sweeps_orphaned_part_files(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / textfill.MODEL_FILES["sttn"]).write_bytes(b"x")
    cache = tmp_path / "fill"
    cache.mkdir()
    stale = cache / ".old.part.mp4"
    stale.write_bytes(b"x")

    class Stop(Exception):
        pass

    def stop(*_args):
        assert not stale.exists()
        raise Stop

    monkeypatch.setattr(textfill, "_filler", stop)
    try:
        textfill.prepare_span(
            source="s.mp4", meta=META, start=0.0, duration=1.0, layers=[BOTTOM],
            method="sttn", cache_dir=cache, data_root=tmp_path,
        )
    except Stop:
        pass
    assert not stale.exists()


def test_a_long_fill_records_its_rate(tmp_path, monkeypatch):
    import io

    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / textfill.MODEL_FILES["sttn"]).write_bytes(b"x")
    monkeypatch.setenv("VIBECUT_FILL_TEXT_MASK", "off")
    meta = {"width": 64, "height": 64, "fps": 10.0, "fingerprint": "f"}
    frames = [np.zeros((64, 64, 3), dtype=np.uint8) for _ in range(70)]

    class Proc:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()

        def poll(self):
            return 0

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    class Reader:
        def __init__(self, *args):
            self.proc = Proc()
            self.items = iter(frames)

        def read(self):
            return next(self.items, None)

    class Writer:
        def __init__(self, _ffmpeg, output, *args):
            self.proc = Proc()
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"x" * 2048)

        def write(self, frame):
            pass

    class Filler:
        def fill(self, strips):
            return strips

    monkeypatch.setattr(textfill, "_Reader", Reader)
    monkeypatch.setattr(textfill, "_Writer", Writer)
    monkeypatch.setattr(textfill, "_filler", lambda *args: Filler())
    textfill.prepare_span(
        source="s.mp4", meta=meta, start=0.0, duration=7.0,
        layers=[{**BOTTOM, "box": {"x": 0.1, "y": 0.5, "w": 0.8, "h": 0.2}}],
        method="sttn", cache_dir=tmp_path / "fill", data_root=tmp_path,
    )
    assert textfill.fill_rate(tmp_path, "sttn")["measured"] is True
    assert os.path.isfile(tmp_path / textfill.RATES_FILE)


def test_the_panel_and_finish_show_the_estimate():
    assert "fill-estimate" in CLEAN and "st-fill-estimate" in CLEAN
    assert "/fill-estimate?" in FINISH and "st-finish-fill-note" in FINISH


def test_the_one_frame_preview_is_labelled_and_the_real_test_exists():
    assert "Before / After" in CLEAN
    assert "LaMa preview · one frame" in INDEX
    assert "Test 1 second" in CLEAN and "Cancel test" in CLEAN
    assert "function testCleanLayer(layerId)" in INDEX and "/cancel" in INDEX
    assert "st-compare-video" in PREVIEW and 'id="st-compare-play"' in PREVIEW
