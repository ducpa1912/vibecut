# LaMa GPU plan

Status: **measured 2026-11-11, see `gpu-fill-bench.md`.** MPS is 4.6× faster than CPU on a real span;
CoreML EP is 32× slower and is closed; torch is 587 MB here, not 2–3 GB; the cache key already
separates devices. Packaging decision is open. The text below is the plan as written before the
measurement.

Fill runs on the CPU today. The GPU path exists in code but cannot run in a shipped
build. This file records what is there, what to measure, and the order to change it.

## Today

| Path | Engine | File | State |
|---|---|---|---|
| CPU (default) | ONNX Runtime, CPU EP | `lama_fp32.onnx`, bundled | Works. 5–7 s per fill in the benchmark |
| GPU, local | PyTorch `torch.jit` on MPS | `big-lama.pt` | Code exists (`LamaGpuFiller`), not shipped: torch and the `.pt` file are absent |
| GPU, local, cheap | ONNX Runtime CoreML EP | `lama_fp32.onnx` | Opt-in via `VIBECUT_FILL_LAMA_PROVIDER=coreml`. CoreML takes the graph apart, ~585 partitions, so it is not expected to win |
| Cloud GPU | User-supplied endpoint | — | Not built. Cost model assumes a T4 at $288/month |

Relevant code: `duckcore/engine/textfill/lama.py` (providers), `torch_fill.py` (`LamaGpuFiller`,
`gpu_possible`, `gpu_problem`), `__init__.py` (`chosen_device`, `SEED_GPU_RATES`).
`gpu_problem()` already returns the honest reason when torch or the model is missing.

Current rates: CPU seed 4.0 s per unit, GPU seed 0.8 s. Both are estimates, not measured here.

## What blocks the GPU today

1. **Torch is not in the bundle.** PyInstaller ships onnxruntime, not torch. Bundling torch adds
   roughly 2–3 GB and nested dylibs to sign.
2. **`big-lama.pt` is not shipped.** Only the ONNX file is in `Resources/base-models`.
3. **No benchmark.** Nobody has measured MPS against CPU on this machine, at this image size.
4. **Cache key does not include the device.** A fill made on CPU and one made on GPU would collide
   unless `span_key` carries the device; the code passes `device` into `_rate_key` but not into the
   fill key. Check before enabling.

Downloads cannot solve 1: torch is executable code, and the product promise is no downloaded
executable code. A GPU path is therefore a packaging decision, not a toggle.

## Order of work

### Step 1 — measure before choosing (no product change)

- Extend `scripts/bench_fill.py` with `--device cpu|gpu` and `--model`.
- Put `big-lama.pt` and torch on this Mac only (dev machine), run 10 frames.
- Record: seconds per fill, PSNR/SSIM against CPU, peak memory, first-run load time, thermal drop.
- Also measure the CoreML EP on the same frames. It needs no torch; if it is within 1.5× of CPU,
  the whole packaging problem disappears.
- Output: `docs/duck/gpu-fill-bench.md` with the table. No code shipped.

Acceptance: a table with CPU, CoreML, MPS on the same 10 frames and the same model.

### Step 2 — decide the packaging

| Option | Cost | Verdict rule |
|---|---|---|
| CoreML EP, existing ONNX | none | Use if ≥1.5× CPU and no artefacts |
| Bundle torch + `big-lama.pt` | +2–3 GB app, nested signing | Use if MPS is ≥3× CPU and memory stays under 8 GB |
| Separate "GPU pack" that downloads torch | breaks the promise | Only if the promise is renegotiated with the user |
| Cloud GPU endpoint, user key | upload of frames | Last resort; BYOK slot, never default |

### Step 3 — wire the choice

- `span_key` includes `device` and the model stamp; bump `textfill.VERSION`.
- `chosen_device` already falls back to CPU when `gpu_problem` is non-empty. Keep it.
- Settings shows one row: `AI fill · CPU` or `AI fill · GPU (M1, 4× faster)`, with the real reason
  when the GPU is unavailable. No fake toggle.
- Render progress uses the measured rate for the chosen device, not the seed.

### Step 4 — cloud, only if asked

- A fill endpoint is a BYOK slot: user URL, user key, no default, no proxy.
- The consent dialog must say frames leave the Mac. That is the strongest promise the product makes.

## Acceptance for the loop

- Benchmark numbers for CPU, CoreML and MPS on the same frames and machine.
- GPU result within 0.2 dB PSNR of CPU, or the difference is stated.
- Peak memory under 8 GB on an M1 8 GB Mac; no swap storm.
- Cache invalidates when the device changes.
- A missing torch or model produces the existing honest message, not a crash.
- If no option clears the bar, the doc records that and the default stays CPU.
