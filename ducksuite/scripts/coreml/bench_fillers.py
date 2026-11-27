"""REQ-20261116-01: the app's two GPU fillers on the same areas, end to end.

Usage: python bench_fillers.py <big-lama.pt> <lama_fill.mlpackage> [runs]
Synthetic pictures drawn in numpy (no media). Each area shape is one kind of
caption box; the fillers pad it their own way (PyTorch to a multiple of 16, Core
ML to a bucket), so the diff includes that padding.
"""
import sys
import tempfile
import time
import json
import resource
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from duckcore.engine.textfill.coreml_fill import LamaCoreMLFiller, bucket, BUCKETS  # noqa: E402
from duckcore.engine.textfill.lama import fit, input_size  # noqa: E402
from duckcore.engine.textfill.torch_fill import LamaGpuFiller  # noqa: E402
from duckcore.engine.textfill import _GpuOrCpu  # noqa: E402

pt_path, ml_path = Path(sys.argv[1]), Path(sys.argv[2])
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
# (height, width) of a work area around text: thin caption, two lines, a sign, a square.
SHAPES = list(BUCKETS) + [(512, s) for s in (40, 65, 129, 193, 257, 385)] + [(s, 512) for s in (40, 65, 129, 193, 257, 385)]
records = []
report_path = Path(sys.argv[4]) if len(sys.argv) > 4 else ml_path.parent / 'benchmark.json'


def area(h, w, seed):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.stack([x / w, y / h, 0.5 + 0.5 * np.sin((x + y) / 23.0)], -1) * 255
    for _ in range(8):
        a, b = rng.integers(0, max(1, h - 8)), rng.integers(0, max(1, w - 8))
        img[a:a + rng.integers(4, max(5, h // 3)), b:b + rng.integers(8, max(9, w // 3))] = rng.random(3) * 255
    hole = np.zeros((h, w), bool)
    hole[h // 4: h - h // 4, w // 8: w - w // 8] = True
    return np.clip(img, 0, 255).astype(np.uint8), hole


t0 = time.perf_counter()
torch_filler = LamaGpuFiller(pt_path)
loads = {'pytorch_load_s': time.perf_counter() - t0}
print(f"pytorch load {loads['pytorch_load_s']:.1f}s", flush=True)
with tempfile.TemporaryDirectory() as cache:
    for label in ("first", "second"):
        if label == 'second':
            del coreml
            __import__('gc').collect()
        t0 = time.perf_counter()
        coreml = LamaCoreMLFiller(ml_path, cache=Path(cache) if label == "first" else Path(cache))
        loads[label + '_load_s'] = time.perf_counter() - t0
        print(f"coreml load ({label}, compile cached={label == 'second'}) {loads[label + '_load_s']:.1f}s",
              flush=True)
    print(f"{'area':>9} {'pytorch run':>12} {'coreml run':>11} {'pt ms':>7} {'ml ms':>7} "
          f"{'speed':>6} {'max':>4} {'mean hole':>9} {'>2 off':>7}")
    for h, w in SHAPES:
        safe_coreml = _GpuOrCpu(lambda: coreml, lambda: torch_filler)
        fh, fw = fit(h, w)
        if input_size(fh, fw, True) not in BUCKETS:
            # The padding gate is geometric: avoid loading an unsupported function.
            safe_coreml._to_cpu()
        cases = [area(h, w, s) for s in range(3)]
        torch_filler.fill(*cases[0])
        t0 = time.perf_counter()
        safe_coreml.fill(*cases[0])  # first call of this size loads its function
        first = time.perf_counter() - t0
        timings = {}
        outs = {}
        for name, filler in (("pt", torch_filler), ("ml", safe_coreml)):
            t0 = time.perf_counter()
            for i in range(runs):
                filler.fill(*cases[i % 3])
            timings[name] = (time.perf_counter() - t0) / runs
            outs[name] = [filler.fill(*c).astype(np.int16) for c in cases]
        diffs = [np.abs(a - b) for a, b in zip(outs["pt"], outs["ml"])]
        holes = [d[c[1]] for d, c in zip(diffs, cases)]
        fh, fw = fit(h, w)
        records.append({'area': [h,w], 'bucket': list(bucket(fh,fw)), 'pt_ms': timings['pt']*1000,
                        'ml_ms': timings['ml']*1000, 'speedup': timings['pt']/timings['ml'],
                        'max_diff': max(int(d.max()) for d in diffs),
                        'mean_hole': float(np.mean([x.mean() for x in holes])),
                        'fell_back': not safe_coreml.cache_valid,
                        'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
        report_path.write_text(json.dumps({'loads': loads, 'cases': records}, indent=2))
        print(f"{h:>4}x{w:<4} {'%dx%d' % input_size(fh, fw, True):>12} {'%dx%d' % bucket(fh, fw):>11} "
              f"{timings['pt'] * 1000:7.1f} {timings['ml'] * 1000:7.1f} {timings['pt'] / timings['ml']:5.2f}x "
              f"{max(int(d.max()) for d in diffs):4d} {np.mean([x.mean() for x in holes]):9.2f} "
              f"{100 * np.mean([(x > 2).mean() for x in holes]):6.2f}%  (first {first:.1f}s)", flush=True)
