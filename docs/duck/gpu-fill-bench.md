# LaMa fill speed — measured

Date: 2026-11-11 · `PLAN.md` loop 3 · REQ-20261111-04 · Mac: M1, 8 GB, macOS 26.7.2.

**Conditions.** The Mac was busy during every run: load average 8–20, 10.9 GB of 12 GB swap in use
(CapCut, a browser and other apps open). Numbers are what a creator's Mac gives, not a quiet lab.
torch 2.14.1 and `big-lama.pt` were already on this Mac; nothing was downloaded.

## 1. Model only — 10 frames, ground truth

`python3 scripts/bench_fill.py --project prj_e95348a97316 --frames 10 --device <d>`, one device per
process. A caption is painted on text-free frames, filled, and scored against the untouched frame.

| Device | Engine, file | Load | First fill | Steady fill | Peak RSS | PSNR | SSIM |
|---|---|---:|---:|---:|---:|---:|---:|
| `cpu` (shipped) | ONNX Runtime CPU, `lama_fp32.onnx` | 6.7 s | 1.2 s | **2.09 s** | 621 MB | 24.87 | 0.7653 |
| `coreml` | ONNX Runtime CoreML EP, same file | 35.8 s | 12.1 s | **67.88 s** | 664 MB | 24.87 | 0.7653 |
| `gpu` | PyTorch MPS, `big-lama.pt` | 2.8 s | 4.4 s | **0.74 s** | 675 MB | 24.87 | 0.7653 |

RSS does not count memory the GPU holds outside the process.

## 2. Real span — clip 1 of the review project, cold

0–4.75 s, 143 frames, 61 model runs, 38.4 units, through `textfill.prepare_span` with an empty
cache. This is what a render pays.

| Run | Seconds | Per frame | Load average at start |
|---|---:|---:|---|
| CPU, scan plan | 189 | 1.33 | (loop 2 render, whole clip incl. encode) |
| CPU, scan plan | 262 | 1.83 | ~20 |
| CPU, scan plan | 864 | 6.04 | ~20 |
| CPU, scan plan | 670 | 4.68 | ~20 |
| CPU, scan plan | 232 | 1.62 | 8 |
| **MPS, scan plan** | **50** | **0.35** | 10 |
| CPU, flat 3 fills/s (`VIBECUT_FILL_LAMA_KEYS=3`) | 376 | 2.63 | 11 |

- **The same CPU job took 189 s to 864 s.** On a busy 8 GB Mac the CPU fill time swings 4.6×. This,
  not the model, explains the old "25 s slice ran 42 min" and the 35 s-per-unit rate.
- **MPS: 50 s.** 4.6× faster than the best comparable CPU run (232 s), more against the others. One
  MPS run only; its variance is not measured.
- **MPS output matches CPU**: PSNR 57.9 dB between the two filled clips (min 52.2). OCR on all 143
  frames of the MPS clip: no subtitle left.
- **A flat 3 fills/s is slower, not faster**: 121 runs against the scan plan's 61. The plan already
  skips runs on still lines. The "6/s vs 3/s" idea is closed; no change.

## 3. Corrections to `GPU-FILL-PLAN.md`

- torch on this Mac is **587 MB** on disk, not 2–3 GB. With `big-lama.pt` (206 MB) the bundle would
  grow by about 0.8 GB, from 377 MB to about 1.15 GB. PyInstaller's real cut is not measured.
- The cache key **already separates devices**: `method_stamp` returns the GPU model's stamp with
  `:gpu`, and `span_key` includes it. No key change or `VERSION` bump is needed for that.
- CoreML EP is not a cheap win. It is 32× slower than CPU here. Closed.
- `render_edit` does not pass a `device` to `prepare_span`. That is the wiring still missing.

## 4. Decision

By the plan's own rule ("bundle torch if MPS is ≥3× CPU and memory stays under 8 GB") MPS
qualifies: 4.6× on a real span. Shipping it costs about +0.8 GB of bundle and nested dylibs to sign.
That is a product call and is **left to the founder**. Until then the default stays CPU. Nothing in
this loop changes fill output; `textfill.VERSION` stays 12.

## 5. The estimate

`fill_rates.json` held 35 s a unit from an earlier starved run, and a running average kept it. Real
rates here: 5.6 and 6.4 s a unit on CPU, 0.95 on MPS. The stored rate is now the middle of the last
three fills. Whole review project, 283 units:

| | Rate | AI fill time |
|---|---:|---:|
| Loop 1 reading | 35 s | 2 h 45 min |
| CPU, measured | ~6 s | ~28 min, up to ~2 h when the Mac is busy |
| MPS, measured once | ~0.95 s | ~4.5 min |
