"""REQ-20261116-01: convert the shipped LaMa TorchScript to a Core ML package.

Usage: python convert.py <big-lama.pt> <out-dir> <precision fp16|fp32> [flex]
"""
import sys
import time
import warnings
from pathlib import Path

import coremltools as ct
import torch

src, out, precision = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
flex = len(sys.argv) > 4 and sys.argv[4] == "flex"
out.mkdir(parents=True, exist_ok=True)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    model = torch.jit.load(str(src), map_location="cpu").eval()


class Wrap(torch.nn.Module):
    def __init__(self, inner):
        super().__init__()
        self.inner = inner

    def forward(self, image, mask):
        return self.inner(image, mask)


image = torch.rand(1, 3, 512, 512)
mask = (torch.rand(1, 1, 512, 512) > 0.9).float()
t0 = time.time()
traced = torch.jit.trace(Wrap(model), (image, mask), check_trace=False)
print(f"traced in {time.time() - t0:.1f}s", flush=True)

if flex:
    # The sizes the fill really runs at: multiples of 16 from 64 to 512.
    shapes = [(h, w) for h in (64, 128, 192, 256, 384, 512) for w in (64, 128, 192, 256, 384, 512)]
    img_shape = ct.EnumeratedShapes(shapes=[(1, 3, h, w) for h, w in shapes], default=(1, 3, 512, 512))
    msk_shape = ct.EnumeratedShapes(shapes=[(1, 1, h, w) for h, w in shapes], default=(1, 1, 512, 512))
else:
    img_shape, msk_shape = (1, 3, 512, 512), (1, 1, 512, 512)

t0 = time.time()
ml = ct.convert(
    traced,
    inputs=[ct.TensorType(name="image", shape=img_shape), ct.TensorType(name="mask", shape=msk_shape)],
    outputs=[ct.TensorType(name="output")],
    convert_to="mlprogram",
    compute_precision=ct.precision.FLOAT16 if precision == "fp16" else ct.precision.FLOAT32,
    minimum_deployment_target=ct.target.macOS15,
)
name = f"lama_{precision}{'_flex' if flex else '_512'}.mlpackage"
ml.save(str(out / name))
print(f"converted in {time.time() - t0:.1f}s -> {out / name}", flush=True)
