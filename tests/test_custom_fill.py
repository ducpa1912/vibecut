"""A fill model the user supplies: load it, fall back to LaMa, never ship it."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from duckcore import app_settings
from duckcore.engine import textfill
from duckcore.engine.textfill import custom


def _model_folder(root: Path, name: str = "model.onnx", size: int = 4096) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(b"\0" * size)
    return root


def test_a_folder_without_a_model_says_what_it_needs(tmp_path) -> None:
    assert "Choose a fill model folder" in (custom.problem("") or "")
    assert "not there" in (custom.problem(tmp_path / "nope") or "")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert "model.onnx" in (custom.problem(empty) or "")
    tiny = _model_folder(tmp_path / "tiny", size=10)
    assert "empty" in (custom.problem(tiny) or "")
    assert custom.problem(_model_folder(tmp_path / "ok")) is None


def test_the_folder_is_found_by_file_name(tmp_path) -> None:
    folder = _model_folder(tmp_path / "onnx")
    assert custom.find_model(folder) == folder / "model.onnx"
    torch_folder = _model_folder(tmp_path / "torch", name="model.pt")
    assert custom.find_model(torch_folder) == torch_folder / "model.pt"


def test_a_stub_torch_model_fills_the_hole(tmp_path) -> None:
    torch = pytest.importorskip("torch")

    class Stub(torch.nn.Module):
        def forward(self, image: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
            return image * 0.0 + 0.5  # 0..1 grey, anywhere in the hole

    folder = tmp_path / "mine"
    folder.mkdir()
    module = torch.jit.script(Stub())
    torch.jit.save(module, str(folder / "model.pt"))

    assert custom.problem(folder) is None

    # Through the production loader, the same file the render would read.
    loader = lambda: custom.CustomTorchFiller(folder / "model.pt")  # noqa: E731
    filler = loader()
    area = np.random.default_rng(3).integers(0, 255, (40, 56, 3), dtype=np.uint8)
    mask = np.zeros((40, 56), dtype=bool)
    mask[12:28, 16:40] = True
    out = filler.fill(area, mask)
    assert out.shape == area.shape
    inside = out[mask].astype(np.int16)
    assert abs(float(inside.mean()) - 128.0) < 12.0


def test_a_bad_custom_model_raises_a_plain_message(tmp_path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "model.onnx").write_bytes(b"not a graph")
    with pytest.raises(ValueError) as caught:
        custom.open_filler(folder)
    assert "did not load" in str(caught.value) or "model" in str(caught.value).lower()


def test_the_custom_stamp_separates_the_cache(tmp_path) -> None:
    base = tmp_path / "models"
    base.mkdir()
    (base / "lama_fp32.onnx").write_bytes(b"\0" * 4096)
    (base / "big-lama.pt").write_bytes(b"\0" * 4096)
    model = _model_folder(tmp_path / "mine") / "model.onnx"
    plain = textfill.method_stamp("lama", base, "gpu")
    mine = textfill.method_stamp("lama", base, "gpu", custom=model)
    assert mine != plain and mine.endswith(":custom")
    model.write_bytes(b"\0" * 8192)
    assert textfill.method_stamp("lama", base, "gpu", custom=model) != mine


def test_a_bad_folder_is_refused_in_settings_with_a_plain_message(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        app_settings.update(tmp_path, {"fill_model_path": str(tmp_path / "gone")})
    assert "not there" in str(caught.value)
    folder = _model_folder(tmp_path / "mine")
    app_settings.update(tmp_path, {"fill_model_path": str(folder)})
    status = app_settings.snapshot(tmp_path)["fill"]["model"]
    assert status["ready"] is True and status["file"] == "model.onnx"
    app_settings.update(tmp_path, {"fill_model_path": ""})
    assert textfill.custom_fill_path(tmp_path) is None


def test_the_render_falls_back_when_the_file_cannot_load(tmp_path, monkeypatch) -> None:
    folder = _model_folder(tmp_path / "mine")
    app_settings.update(tmp_path, {"fill_model_path": str(folder)})
    monkeypatch.setattr(
        textfill, "_custom_filler",
        lambda path: (_ for _ in ()).throw(textfill.FillError("Your fill model did not load: bad graph.")),
    )
    path, reason = textfill.custom_fill_model(tmp_path)
    assert path is not None and reason is None  # the folder itself is fine
    with pytest.raises(textfill.FillError) as caught:
        textfill._custom_filler(path)
    assert "did not load" in str(caught.value)
