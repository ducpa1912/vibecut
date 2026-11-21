"""REQ-20261121-01: choose Core ML or PyTorch for the GPU fill on the Render screen."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from duckcore import app_settings, render
from duckcore.engine import textfill
from duckcore.engine.textfill import coreml_fill
from duckcore.main import create_app


def _package(folder: Path) -> None:
    package = folder / "lama_fill.mlpackage"
    (package / "Data").mkdir(parents=True)
    (package / "Manifest.json").write_text("{}")


@pytest.fixture
def choice(monkeypatch):
    """Isolate the process-wide choice and the launch flag."""
    monkeypatch.setattr(textfill, "_PREFERRED_GPU_ENGINE", textfill.DEFAULT_GPU_ENGINE)
    monkeypatch.delenv("DUCK_FILL_GPU_ENGINE", raising=False)
    monkeypatch.setattr(coreml_fill, "possible", lambda: True)


def test_the_default_is_pytorch_and_the_choice_selects_core_ml(tmp_path, choice) -> None:
    _package(tmp_path)
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"
    assert textfill.prefer_gpu_engine("coreml") == "coreml"
    assert textfill.gpu_engine("lama", tmp_path) == "coreml"
    assert textfill.prefer_gpu_engine("onnx") == "pytorch"
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"


def test_the_launch_flag_still_wins_over_the_choice(tmp_path, choice, monkeypatch) -> None:
    _package(tmp_path)
    textfill.prefer_gpu_engine("coreml")
    monkeypatch.setenv("DUCK_FILL_GPU_ENGINE", "pytorch")
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"
    textfill.prefer_gpu_engine("pytorch")
    monkeypatch.setenv("DUCK_FILL_GPU_ENGINE", "coreml")
    assert textfill.gpu_engine("lama", tmp_path) == "coreml"


def test_core_ml_without_its_package_is_pytorch(tmp_path, choice) -> None:
    textfill.prefer_gpu_engine("coreml")
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"


def test_the_setting_is_stored_validated_and_shown(tmp_path) -> None:
    assert app_settings.fill_gpu_engine(tmp_path) == "pytorch"
    app_settings.update(tmp_path, {"fill_gpu_engine": "coreml"})
    assert app_settings.fill_gpu_engine(tmp_path) == "coreml"
    assert app_settings.snapshot(tmp_path)["fill"]["gpu_engine"] == "coreml"
    with pytest.raises(ValueError):
        app_settings.update(tmp_path, {"fill_gpu_engine": "onnx"})


def test_the_render_reads_the_choice_before_it_fills(tmp_path, choice) -> None:
    app_settings.update(tmp_path, {"fill_gpu_engine": "coreml"})
    render._fill_device(tmp_path)
    assert textfill._PREFERRED_GPU_ENGINE == "coreml"
    app_settings.update(tmp_path, {"fill_gpu_engine": "pytorch"})
    render._fill_device(tmp_path)
    assert textfill._PREFERRED_GPU_ENGINE == "pytorch"


def test_the_settings_route_saves_the_choice(tmp_path, choice) -> None:
    with TestClient(create_app("t", tmp_path)) as client:
        headers = {"Authorization": "Bearer t"}
        done = client.patch("/api/settings", json={"fill_gpu_engine": "coreml"}, headers=headers)
        assert done.status_code == 200 and done.json()["fill"]["gpu_engine"] == "coreml"
        assert textfill._PREFERRED_GPU_ENGINE == "coreml"
        bad = client.patch("/api/settings", json={"fill_gpu_engine": "onnx"}, headers=headers)
        assert bad.status_code == 400
        fill = client.get("/api/engine", headers=headers).json()["fill"]
        assert {"coreml_ready", "coreml_problem", "gpu_engine_flag"} <= set(fill)


def test_fits_matches_the_exact_bucket_rule() -> None:
    filler = coreml_fill.LamaCoreMLFiller.__new__(coreml_fill.LamaCoreMLFiller)
    assert filler.fits(40, 700)          # runs at 64x512, a function of its own
    assert not filler.fits(512, 65)      # would need coarse padding: refused


class _Engine:
    def __init__(self, add: int, size_ok=True, broken=False):
        self.add, self.size_ok, self.broken, self.calls = add, size_ok, broken, 0

    def fits(self, height, width):
        return self.size_ok

    def fill(self, area, mask):
        self.calls += 1
        if self.broken:
            raise RuntimeError("Core ML fill failed")
        return area + self.add


def _area():
    return np.zeros((8, 8, 3), np.uint8), np.ones((8, 8), bool)


def test_each_box_goes_to_core_ml_when_it_fits_and_pytorch_when_not() -> None:
    torch = _Engine(2)
    coreml = _Engine(1)
    routed = textfill._CoreMLRouted(coreml, lambda: torch)
    assert int(routed.fill(*_area())[0, 0, 0]) == 1
    coreml.size_ok = False
    assert int(routed.fill(*_area())[0, 0, 0]) == 2
    coreml.size_ok = True
    # A size miss no longer moves the rest of the span to PyTorch.
    assert int(routed.fill(*_area())[0, 0, 0]) == 1
    assert (routed.coreml_areas, routed.gpu_areas) == (2, 1)
    assert routed.cache_valid


def test_a_core_ml_failure_moves_the_span_to_pytorch_and_is_not_cached() -> None:
    torch = _Engine(2)
    coreml = _Engine(1, broken=True)
    routed = textfill._CoreMLRouted(coreml, lambda: torch)
    wrapper = textfill._GpuOrCpu(lambda: routed, lambda: _Engine(9))
    assert int(wrapper.fill(*_area())[0, 0, 0]) == 2
    assert int(wrapper.fill(*_area())[0, 0, 0]) == 2
    assert coreml.calls == 1 and routed.coreml is None
    assert (routed.coreml_areas, routed.gpu_areas) == (0, 2)
    assert not wrapper.cache_valid   # the wrapper sees the routed engine's mix


def test_a_cpu_fallback_still_marks_the_wrapper_invalid() -> None:
    wrapper = textfill._GpuOrCpu(lambda: _Engine(1, broken=True), lambda: _Engine(3))
    assert wrapper.cache_valid
    assert int(wrapper.fill(*_area())[0, 0, 0]) == 3
    assert not wrapper.cache_valid


def test_the_done_message_names_the_engine_and_the_counts(tmp_path) -> None:
    output = tmp_path / "out.mp4"
    assert render._done_message(output) == "Render complete"
    summary = {"chosen": "coreml", "gpu_engine": "coreml", "coreml_areas": 9, "gpu_areas": 33,
               "fill_seconds": 412.4, "filled_clips": 3, "reused_clips": 1}
    output.with_suffix(".fill.json").write_text(json.dumps(summary))
    message = render._done_message(output)
    assert "Core ML filled 9 of 42 boxes" in message and "fill 412 s" in message and "1 reused" in message
    summary.update(gpu_engine="pytorch", coreml_areas=0, gpu_areas=0)
    output.with_suffix(".fill.json").write_text(json.dumps(summary))
    assert "PyTorch GPU fill 412 s" in render._done_message(output)
    summary.update(filled_clips=0, reused_clips=4)
    output.with_suffix(".fill.json").write_text(json.dumps(summary))
    assert "no new fill" in render._done_message(output)


def test_a_core_ml_span_reports_its_counts_and_stays_cached(tmp_path, monkeypatch) -> None:
    class Process:
        stdin = SimpleNamespace(close=lambda: None)
        def wait(self, **kwargs): return 0
        def poll(self): return 0

    class Reader:
        proc = Process()
        def __init__(self, *args): self.n = 0
        def read(self):
            self.n += 1
            return np.zeros((16, 16, 3), np.uint8) if self.n == 1 else None

    class Writer:
        proc = Process()
        stderr_tail = ""
        def __init__(self, ffmpeg, path, *args): self.path = path
        def write(self, frame): self.path.write_bytes(b"x" * 2048)

    engines = {"coreml": _Engine(1), "torch": _Engine(2)}

    def fake_filler(method, path, *args, **kwargs):
        return engines["coreml"] if str(path).endswith(".mlpackage") else engines["torch"]

    def fake_frames(frames, rects_for, filler, *args, **kwargs):
        filler.fill(*_area())
        engines["coreml"].size_ok = False
        area, mask = _area()
        filler.fill(area + 5, mask)  # a different picture: not a saved fill
        return frames

    monkeypatch.setattr(textfill, "models_dir", lambda *a: tmp_path)
    monkeypatch.setattr(textfill, "engine_choice", lambda *a: (None, ""))
    monkeypatch.setattr(textfill, "chosen_device", lambda *a: "gpu")
    monkeypatch.setattr(textfill, "device_problem", lambda *a: None)
    monkeypatch.setattr(textfill, "model_path", lambda *a: tmp_path / "lama_fill.mlpackage")
    monkeypatch.setattr(textfill, "method_stamp", lambda *a, **k: "p:coreml-gpu")
    monkeypatch.setattr(textfill, "_filler", fake_filler)
    monkeypatch.setattr(textfill, "_Reader", Reader)
    monkeypatch.setattr(textfill, "_Writer", Writer)
    monkeypatch.setattr(textfill, "_finder_for", lambda *a, **k: None)
    monkeypatch.setattr(textfill, "_stop", lambda *a: None)
    monkeypatch.setattr(textfill, "_prune_saved", lambda *a: None)
    learned: list = []
    monkeypatch.setattr(textfill, "_learn_rate", lambda *a, **k: learned.append(k))
    monkeypatch.setattr(textfill, "fill_frames_lama", fake_frames)
    monkeypatch.setattr(textfill, "RATE_MIN_FRAMES", 1)
    result = textfill.prepare_span(
        source="unused", meta={"width": 16, "height": 16, "fps": 30},
        start=0, duration=1 / 30, layers=[{"box": {"x": .1, "y": .1, "w": .5, "h": .5}}],
        method="lama", cache_dir=tmp_path / "fill", data_root=tmp_path, ffmpeg="unused", device="gpu",
    )
    assert result["gpu_engine"] == "coreml"
    assert (result["coreml_areas"], result["gpu_areas"]) == (1, 1)
    assert not result["ephemeral"]
    assert (tmp_path / "fill" / f"{result['key']}.mp4").is_file()
    # A Core ML speed must not teach the PyTorch estimate.
    assert learned and all(k["reused"] for k in learned)
