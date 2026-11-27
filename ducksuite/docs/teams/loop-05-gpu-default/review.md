# GPU default, CPU as an optional pack

Date: 2026-11-11 · Request: REQ-20261111-07 · Follows `docs/teams/loop-04-gpu-engine/review.md`.

## Brief

Ship v1 GPU-first. The bundle carries torch and `big-lama.pt` only. CPU fill becomes a Settings
download. Kokoro stays an optional pack but is removed from this Mac. onnxruntime stays for both
packs.

## What changed

- **Bundle**: 1.2 GB → **981 MB**. `lama_fp32.onnx` no longer copied; `big-lama.pt` only.
- **Pack**: new `fill-lama-cpu`, 208,044,816 bytes, Apache-2.0, SHA-256
  `1faef530…68d6`, URL `huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx`, installs into
  `models/fill` (not `models/packs`). Downloads now verify SHA-256 when a pack declares one.
- **Seeding**: `seed_models` hardlinks the bundle model into `models/fill` at sidecar start, so the
  GPU model and a downloaded CPU model live in one folder. `models_dir` prefers app data.
- **Readiness**: `device_problem` per chip; `engine.fill` reports `cpu_ready` and `gpu_ready`.
  Fill is ready if either can run. `DEFAULT_DEVICE` is now `gpu`.
- **UI**: CPU/GPU control in **Render settings** and **Clean Focus**. CPU is disabled until the pack
  is installed, with “CPU engine is optional · Download in Settings”.
- **Removed check**: `prepare_span` demanded the ONNX file before choosing a device; it now validates
  the chosen device only. This was blocking GPU fill in the previous bundle.

## Local cleanup

| Removed | Size |
|---|---|
| Kokoro pack | 337 MB |
| CPU ONNX (bundle + lane) | 396 MB |
| STTN + MI-GAN weights | 89 MB |
| CPU fill caches (3 projects) | 370 MB |

Kept: `big-lama.pt`, Whisper 1.5 GB, torch, imports. ≈ 1.2 GB freed.

## Acceptance

| Check | Result |
|---|---|
| GPU is the default | pass: `fill_device` gpu, GPU active in both screens |
| CPU disabled until installed | pass: button disabled, pack row present in Settings |
| Bundle has no ONNX / no Kokoro | pass: 981 MB, `base-models` holds `big-lama.pt` only |
| GPU render from the final bundle | pass: 1 s clip in **9.4 s**, no text on frame 0 (OCR) |
| CPU pack install path | pass: unit test writes into `models/fill`; remove keeps other files |
| Suite | pass: **101 tests**, `node --check` clean |

## Not tested

- A real CPU-pack download and CPU fill on a clean machine (the download is 198 MB; URL length and
  hash match the local file that was removed).
- Kokoro re-download after removing the local copy.
- GPU variance and heat after a long render.

## Next

Loop 4: one full render with GPU selected. The estimate is a first guess until that run records a
measured rate.
