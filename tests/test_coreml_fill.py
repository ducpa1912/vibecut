"""REQ-20261116-01: Core ML is the default GPU fill; PyTorch is the fallback."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from duckcore.engine import textfill
from duckcore.engine.textfill import coreml_fill, lama


def _package(folder: Path, payload: bytes = b"w" * 64) -> Path:
    package = folder / "lama_fill.mlpackage"
    (package / "Data").mkdir(parents=True)
    (package / "Manifest.json").write_text("{}")
    (package / "Data" / "weights.bin").write_bytes(payload)
    return package


@pytest.fixture
def coreml_here(monkeypatch):
    monkeypatch.setattr(coreml_fill, "possible", lambda: True)
    monkeypatch.setenv("DUCK_FILL_GPU_ENGINE", "coreml")


def test_the_version_is_bumped_for_the_new_pixels() -> None:
    assert textfill.VERSION == 18


def test_every_run_size_has_a_bucket_that_holds_it() -> None:
    for side in range(lama.MIN_SIDE, lama.SIZE + 1, lama.STEP):
        for h, w in ((lama.SIZE, side), (side, lama.SIZE)):
            bh, bw = coreml_fill.bucket(h, w)
            assert (bh, bw) in coreml_fill.BUCKETS and bh >= h and bw >= w
    # Below the old 64 floor too, and the smallest bucket is chosen.
    assert coreml_fill.bucket(512, 40) == (512, 64)
    assert coreml_fill.bucket(512, 65) == (512, 128)
    assert coreml_fill.bucket(300, 512) == (384, 512)


def test_core_ml_can_be_selected_explicitly(tmp_path: Path, coreml_here) -> None:
    _package(tmp_path)
    assert textfill.gpu_engine("lama", tmp_path) == "coreml"
    assert textfill.gpu_problem("lama", tmp_path) is None
    assert textfill.model_path("lama", tmp_path, "gpu").name == "lama_fill.mlpackage"
    assert textfill.chosen_device("lama", "gpu", tmp_path) == "gpu"


def test_default_remains_pytorch_until_native_abort_is_resolved(tmp_path, coreml_here, monkeypatch):
    _package(tmp_path)
    monkeypatch.delenv('DUCK_FILL_GPU_ENGINE')
    assert textfill.gpu_engine('lama', tmp_path) == 'pytorch'


def test_pytorch_runs_when_asked_or_when_the_package_is_missing(tmp_path: Path, coreml_here,
                                                                monkeypatch) -> None:
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"
    _package(tmp_path)
    monkeypatch.setenv("DUCK_FILL_GPU_ENGINE", "pytorch")
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"
    assert textfill.model_path("lama", tmp_path, "gpu").name == "big-lama.pt"


def test_a_package_without_its_manifest_is_not_ready(tmp_path: Path, coreml_here) -> None:
    (tmp_path / "lama_fill.mlpackage").mkdir()
    assert textfill.coreml_problem("lama", tmp_path)
    assert textfill.gpu_engine("lama", tmp_path) == "pytorch"


def test_the_core_ml_stamp_separates_the_cache(tmp_path: Path, coreml_here, monkeypatch) -> None:
    package = _package(tmp_path)
    (tmp_path / "big-lama.pt").write_bytes(b"\0" * 4096)
    coreml = textfill.method_stamp("lama", tmp_path, "gpu")
    assert coreml.endswith(":coreml-gpu")
    monkeypatch.setenv("DUCK_FILL_GPU_ENGINE", "pytorch")
    assert textfill.method_stamp("lama", tmp_path, "gpu") != coreml
    monkeypatch.setenv("DUCK_FILL_GPU_ENGINE", "coreml")
    (package / "Data" / "weights.bin").write_bytes(b"v" * 128)
    assert textfill.method_stamp("lama", tmp_path, "gpu") != coreml


def test_the_models_folder_is_found_by_the_package_alone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DUCK_FILL_MODELS", raising=False)
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    _package(tmp_path / "models" / "fill")
    assert textfill.models_dir(tmp_path) == tmp_path / "models" / "fill"


def test_the_package_is_seeded_into_app_data_once(tmp_path: Path, monkeypatch) -> None:
    bundle = tmp_path / "bundle"
    _package(bundle)
    monkeypatch.setenv("DUCK_FILL_MODELS", str(bundle))
    data = tmp_path / "data"
    textfill.seed_models(data)
    seeded = data / "models" / "fill" / "lama_fill.mlpackage"
    assert (seeded / "Data" / "weights.bin").read_bytes() == b"w" * 64
    before = (seeded / "Manifest.json").stat().st_ino
    textfill.seed_models(data)
    assert (seeded / "Manifest.json").stat().st_ino == before


def test_a_core_ml_failure_moves_to_pytorch_not_the_cpu(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "big-lama.pt").write_bytes(b"\0" * 4096)
    monkeypatch.setattr(textfill, "torch_problem", lambda method, directory: None)
    seen = []
    monkeypatch.setattr(textfill, "_filler",
                        lambda method, path, device="gpu": seen.append((Path(path).name, device)))
    textfill._fallback_filler("lama", tmp_path, tmp_path / "lama_fill.mlpackage")
    assert seen == [("big-lama.pt", "gpu")]
    seen.clear()
    textfill._fallback_filler("lama", tmp_path, tmp_path / "big-lama.pt")
    assert seen == [("lama_fp32.onnx", "cpu")]


def test_same_size_package_replacement_is_seeded(tmp_path):
    source = _package(tmp_path / 'bundle', b'a' * 64)
    destination = _package(tmp_path / 'data', b'b' * 64)
    textfill._seed_package(source, destination)
    assert (destination / 'Data/weights.bin').read_bytes() == b'a' * 64


def test_compiler_destination_and_failed_compile_preserve_cache(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    package = _package(tmp_path / 'source')
    old = tmp_path / 'cache/lama_fill-old.mlmodelc'
    old.mkdir(parents=True)
    def compile_model(source, destination):
        assert destination.endswith('.mlmodelc')
        raise RuntimeError('compile failed')
    monkeypatch.setitem(sys.modules, 'coremltools', SimpleNamespace(models=SimpleNamespace(utils=SimpleNamespace(compile_model=compile_model))))
    with pytest.raises(RuntimeError): coreml_fill._compiled(package, old.parent)
    assert old.is_dir()


def test_fallback_chain_and_saved_cache_isolation(tmp_path, monkeypatch):
    class Broken:
        def fill(self, *args): raise RuntimeError('GPU failed')
    class CPU:
        def fill(self, area, mask): return area + 1
    monkeypatch.setattr(textfill, 'torch_problem', lambda *a: None)
    monkeypatch.setattr(textfill, '_filler', lambda method,path,device: Broken() if device=='gpu' else CPU())
    fallback = textfill._GpuOrCpu(lambda: Broken(), lambda: textfill._fallback_filler('lama', tmp_path, tmp_path/'lama_fill.mlpackage'))
    saved = textfill._SavedFills(textfill._CountedFiller(fallback), tmp_path/'saved', 'coreml')
    area=np.zeros((8,8,3),np.uint8);mask=np.ones((8,8),bool)
    assert saved.fill(area,mask).max() == 1
    assert not fallback.cache_valid
    assert not list((tmp_path/'saved').glob('*.npy'))


def test_successful_compile_uses_cache_on_second_load(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    package = _package(tmp_path / 'source')
    calls = []
    def compile_model(source, destination):
        assert destination.endswith('.mlmodelc')
        calls.append(destination)
        Path(destination).mkdir()
        return destination
    monkeypatch.setitem(sys.modules, 'coremltools', SimpleNamespace(models=SimpleNamespace(utils=SimpleNamespace(compile_model=compile_model))))
    first = coreml_fill._compiled(package, tmp_path/'cache')
    assert coreml_fill._compiled(package, tmp_path/'cache') == first
    assert len(calls) == 1


def test_fallback_span_is_not_installed_under_primary_key(tmp_path, monkeypatch):
    # Exercise the real prepare_span publication boundary without video media.
    from types import SimpleNamespace
    class Process:
        stdin = SimpleNamespace(close=lambda: None)
        def wait(self, **kwargs): return 0
        def poll(self): return 0
    class Reader:
        proc = Process()
        def __init__(self, *args): self.n = 0
        def read(self):
            self.n += 1
            return np.zeros((16,16,3), np.uint8) if self.n == 1 else None
    class Writer:
        proc = Process()
        stderr_tail = ''
        def __init__(self, ffmpeg, path, *args): self.path = path
        def write(self, frame): self.path.write_bytes(b'x' * 2048)
    monkeypatch.setattr(textfill, 'models_dir', lambda *a: tmp_path)
    monkeypatch.setattr(textfill, 'engine_choice', lambda *a: (None, ''))
    monkeypatch.setattr(textfill, 'chosen_device', lambda *a: 'gpu')
    monkeypatch.setattr(textfill, 'device_problem', lambda *a: None)
    monkeypatch.setattr(textfill, 'model_path', lambda *a: tmp_path/'lama_fill.mlpackage')
    monkeypatch.setattr(textfill, 'method_stamp', lambda *a,**k: 'primary:coreml-gpu')
    monkeypatch.setattr(textfill, '_filler', lambda *a,**k: (_ for _ in ()).throw(RuntimeError('bad coreml')))
    monkeypatch.setattr(textfill, '_fallback_filler', lambda *a: SimpleNamespace(fill=lambda area,mask:area))
    monkeypatch.setattr(textfill, '_Reader', Reader)
    monkeypatch.setattr(textfill, '_Writer', Writer)
    monkeypatch.setattr(textfill, '_finder_for', lambda *a,**k: None)
    monkeypatch.setattr(textfill, '_stop', lambda *a: None)
    monkeypatch.setattr(textfill, '_prune_saved', lambda *a: None)
    monkeypatch.setattr(textfill, 'fill_frames_lama', lambda frames,*a,**k: frames)
    result = textfill.prepare_span(source='unused',meta={'width':16,'height':16,'fps':30},
        start=0,duration=1/30,layers=[{'box':{'x':.1,'y':.1,'w':.5,'h':.5}}],
        method='lama',cache_dir=tmp_path/'fill',data_root=tmp_path,ffmpeg='unused',device='gpu')
    assert '.fallback-' in result['path']
    assert not (tmp_path/'fill'/f"{result['key']}.mp4").exists()


def test_saved_cache_skips_reads_after_fallback(tmp_path, monkeypatch):
    from types import SimpleNamespace
    area=np.zeros((8,8,3),np.uint8);mask=np.ones((8,8),bool)
    filler=SimpleNamespace(cache_valid=False,fill=lambda area,mask: area+2)
    saved=textfill._SavedFills(filler,tmp_path,'primary')
    saved._path=lambda *a: (_ for _ in ()).throw(AssertionError('must not read primary cache'))
    assert saved.fill(area,mask).max()==2


class _Model:
    def __init__(self, seen):
        self.seen = seen

    def predict(self, feed):
        self.seen.append(feed["image"].shape)
        return {"output": np.full(feed["image"].shape, 0.5, np.float32)}


def test_the_filler_pads_to_a_bucket_and_returns_the_area_size() -> None:
    seen: list = []
    filler = coreml_fill.LamaCoreMLFiller.__new__(coreml_fill.LamaCoreMLFiller)
    filler._model = lambda h, w: _Model(seen)
    area = np.zeros((40, 700, 3), np.uint8)
    mask = np.zeros((40, 700), bool)
    mask[10:30, 100:600] = True
    out = filler.fill(area, mask)
    assert out.shape == area.shape and out.dtype == np.uint8
    assert seen == [(1, 3, 64, 512)]
    assert int(out[20, 300, 0]) == 127


def test_a_core_ml_error_is_a_runtime_error_for_the_fallback() -> None:
    class Broken:
        def predict(self, feed):
            raise ValueError("bad")

    filler = coreml_fill.LamaCoreMLFiller.__new__(coreml_fill.LamaCoreMLFiller)
    filler._model = lambda h, w: Broken()
    with pytest.raises(RuntimeError):
        filler.fill(np.zeros((40, 80, 3), np.uint8), np.ones((40, 80), bool))


def test_coarse_padding_is_refused_before_prediction():
    filler = coreml_fill.LamaCoreMLFiller.__new__(coreml_fill.LamaCoreMLFiller)
    filler._model = lambda *a: pytest.fail('must preserve PyTorch padding')
    with pytest.raises(RuntimeError, match='no exact'):
        filler.fill(np.zeros((512,65,3),np.uint8),np.ones((512,65),bool))
