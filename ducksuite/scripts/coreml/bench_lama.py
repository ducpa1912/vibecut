"""REQ-20261116-01: Core ML LaMa against PyTorch MPS LaMa, same inputs.

Usage: python bench.py <big-lama.pt> <model.mlpackage> [runs]
Synthetic structured pictures only (gradients, bars, letters drawn in numpy); no media.
"""
import sys
import time
import warnings

import coremltools as ct
import numpy as np
import torch

pt_path, ml_path = sys.argv[1], sys.argv[2]
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 10
H = W = 512


def picture(seed: int):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    img = np.stack([x / W, y / H, 0.5 + 0.5 * np.sin((x + y) / 37.0)], 0)
    for _ in range(12):  # coloured blocks as "scenery"
        a, b = rng.integers(0, H - 64, 2)
        img[:, a:a + rng.integers(16, 64), b:b + rng.integers(16, 128)] = rng.random((3, 1, 1))
    img += rng.normal(0, 0.02, img.shape).astype(np.float32)
    mask = np.zeros((1, H, W), np.float32)
    mask[:, 300:340, 60:450] = 1.0  # one caption-shaped hole
    mask[:, 100:120, 200:330] = 1.0
    return np.clip(img, 0, 1)[None].astype(np.float32), mask[None]


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    torch_model = torch.jit.load(pt_path, map_location="cpu").to("mps").eval()


def run_torch(img, mask):
    with torch.no_grad():
        out = torch_model(torch.from_numpy(img).to("mps"), torch.from_numpy(mask).to("mps"))
        return out.clamp(0, 1).mul(255).cpu().numpy()


inputs = [picture(s) for s in range(3)]
run_torch(*inputs[0])  # warm
t0 = time.perf_counter()
for i in range(runs):
    ref = run_torch(*inputs[i % 3])
torch.mps.synchronize()
t_torch = (time.perf_counter() - t0) / runs
print(f"pytorch mps       : {t_torch * 1000:7.1f} ms / 512x512 run", flush=True)

refs = [run_torch(*p) for p in inputs]
for name, unit in [("all", ct.ComputeUnit.ALL), ("cpu+gpu", ct.ComputeUnit.CPU_AND_GPU),
                   ("cpu+neural engine", ct.ComputeUnit.CPU_AND_NE)]:
    t0 = time.perf_counter()
    ml = ct.models.MLModel(ml_path, compute_units=unit)
    load = time.perf_counter() - t0
    feed = lambda p: {"image": p[0], "mask": p[1]}
    ml.predict(feed(inputs[0]))  # warm
    t0 = time.perf_counter()
    for i in range(runs):
        ml.predict(feed(inputs[i % 3]))
    t_ml = (time.perf_counter() - t0) / runs
    diffs, hole_diffs, over2 = [], [], []
    for p, r in zip(inputs, refs):
        out = np.clip(ml.predict(feed(p))["output"], 0, 1) * 255
        d = np.abs(np.round(out) - np.round(r))
        hole = np.broadcast_to(p[1] > 0, d.shape)
        diffs.append(d.max()); hole_diffs.append(d[hole].mean()); over2.append((d[hole] > 2).mean())
    print(f"coreml {name:<11}: {t_ml * 1000:7.1f} ms / run  ({t_torch / t_ml:4.2f}x pytorch)  "
          f"load {load:5.1f}s  max diff {max(diffs):.0f}  mean in hole {np.mean(hole_diffs):.2f}  "
          f"hole px >2 off {100 * np.mean(over2):.2f}%", flush=True)
