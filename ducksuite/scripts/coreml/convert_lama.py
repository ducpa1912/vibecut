"""REQ-20261116-01: convert the shipped LaMa TorchScript to one Core ML package.

Core ML cannot take LaMa's Fourier layers at a flexible size (coremltools 9.0
fails on the complex ops), so each run size the app uses is converted on its own
and the sizes are merged into one multifunction package that keeps one copy of
the weights. The sizes are ``textfill.coreml_fill.BUCKETS``.

Usage:
  python convert_lama.py <big-lama.pt> <out-dir>            # every bucket, then merge
  python convert_lama.py <big-lama.pt> <out-dir> 512x64     # one size only
Each size is saved as ``<out-dir>/sizes/lama_<h>x<w>.mlpackage`` and skipped when
it is already there, so a stopped run resumes. The merged package is
``<out-dir>/lama_fill.mlpackage``.
"""
import sys
import time
import warnings
from pathlib import Path

import coremltools as ct
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from duckcore.engine.textfill.coreml_fill import BUCKETS, function_name  # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2])
only = sys.argv[3] if len(sys.argv) > 3 else ""
sizes_dir = out / "sizes"
sizes_dir.mkdir(parents=True, exist_ok=True)

model = None


class Wrap(torch.nn.Module):
    def __init__(self, inner):
        super().__init__()
        self.inner = inner

    def forward(self, image, mask):
        return self.inner(image, mask)


def convert(h: int, w: int) -> Path:
    global model
    target = sizes_dir / f"lama_{h}x{w}.mlpackage"
    if target.exists():
        return target
    if model is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = torch.jit.load(str(src), map_location="cpu").eval()
    image = torch.rand(1, 3, h, w)
    mask = (torch.rand(1, 1, h, w) > 0.9).float()
    t0 = time.time()
    traced = torch.jit.trace(Wrap(model), (image, mask), check_trace=False)
    ml = ct.convert(
        traced,
        inputs=[ct.TensorType(name="image", shape=(1, 3, h, w)),
                ct.TensorType(name="mask", shape=(1, 1, h, w))],
        outputs=[ct.TensorType(name="output")],
        convert_to="mlprogram",
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=ct.target.macOS15,
        skip_model_load=True,
    )
    part = sizes_dir / f".lama_{h}x{w}.part.mlpackage"
    ml.save(str(part))
    part.rename(target)
    print(f"{h}x{w} converted in {time.time() - t0:.0f}s", flush=True)
    return target


if only:
    h, w = (int(v) for v in only.split("x"))
    convert(h, w)
    sys.exit(0)

packages = {size: convert(*size) for size in BUCKETS}
desc = ct.utils.MultiFunctionDescriptor()
for (h, w), path in packages.items():
    desc.add_function(str(path), src_function_name="main", target_function_name=function_name(h, w))
desc.default_function_name = function_name(512, 512)
merged = out / "lama_fill.mlpackage"
t0 = time.time()
ct.utils.save_multifunction(desc, str(merged))
print(f"merged {len(packages)} sizes in {time.time() - t0:.0f}s -> {merged}", flush=True)
