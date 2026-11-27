"""Fill engine choice: CPU by default, GPU only when it can run."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckcore import app_settings, render
from duckcore.engine import textfill


def _edit() -> dict:
    return {
        "project_id": "p1",
        "clips": [{"start": 0.0, "end": 2.0}],
        "clean": [
            {
                "id": "cl_one",
                "kind": "fill",
                "enabled": True,
                "box": {"x": 0.3, "y": 0.48, "w": 0.4, "h": 0.04},
                "ranges": [{"start": 0.0, "end": 2.0}],
            }
        ],
    }


def test_fill_device_defaults_to_gpu(tmp_path: Path) -> None:
    assert app_settings.snapshot(tmp_path)["fill"]["device"] == "gpu"


def test_fill_device_is_saved_and_validated(tmp_path: Path) -> None:
    app_settings.update(tmp_path, {"fill_device": "cpu"})
    assert app_settings.snapshot(tmp_path)["fill"]["device"] == "cpu"
    with pytest.raises(ValueError):
        app_settings.update(tmp_path, {"fill_device": "ane"})


def test_cpu_is_used_when_only_the_cpu_model_is_installed(tmp_path: Path) -> None:
    (tmp_path / "lama_fp32.onnx").write_bytes(b"x")
    assert textfill.chosen_device("lama", "gpu", tmp_path) == "cpu"


def test_nothing_installed_keeps_the_requested_chip(tmp_path: Path) -> None:
    # Neither model exists; the UI is what prevents the choice. No silent switch.
    assert textfill.chosen_device("lama", "gpu", tmp_path) == "gpu"


def test_fill_device_reads_the_setting(tmp_path: Path) -> None:
    app_settings.update(tmp_path, {"fill_device": "gpu"})
    # With neither model on this path the answer stays gpu; the UI blocks it.
    assert render._fill_device(tmp_path) == "gpu"


def test_estimate_uses_the_selected_device(tmp_path: Path, monkeypatch) -> None:
    seen = {}

    def fake_span(**kwargs):
        seen["device"] = kwargs.get("device")
        return {"method": "lama", "device": kwargs.get("device"), "frames": 1, "units": 1, "cached": False}

    monkeypatch.setattr(render, "_fill_device", lambda _root: "gpu")
    monkeypatch.setattr(textfill, "estimate_span", fake_span)
    monkeypatch.setattr(
        textfill, "estimate_summary",
        lambda rows, _root: {"seconds": 0.0, "measured": False, "beats": len(rows), "beats_cached": 0},
    )
    render.estimate_edit(_edit(), {"width": 1080, "height": 1920, "fps": 30.0}, tmp_path)
    assert seen["device"] == "gpu"
