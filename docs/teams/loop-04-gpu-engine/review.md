# GPU fill engine — three dev loops

Date: 2026-11-11 · Request: REQ-20261111-06 · Builds on PLAN loop 3 (`docs/duck/gpu-fill-bench.md`).

Founder decision: bundle the GPU path, keep both CPU and GPU, CPU stays the default.
Team: product owner brief, engineer, tester, creator. Each loop: build → tests → review → commit.

## Brief

LaMa runs on the CPU at 5–7 s a fill, and the review project needs ~28 min of fill. MPS measured
4.6× faster. Ship it without hiding the cost: torch (587 MB) and `big-lama.pt` (196 MB) in the
bundle, a CPU/GPU choice in Render settings, and an estimate that follows the chosen chip.

## Dev loop 1 — the choice

| Item | Result |
|---|---|
| Setting | `fill_device` (`cpu` default, `gpu`), validated in `app_settings.update` |
| Render | `render_edit` and `render_frame` resolve the device once and pass it to `prepare_span` |
| Estimate | `estimate_edit` passes the device, so the number matches the chip |
| UI | Render → **AI fill engine** segmented control; GPU disabled with the real reason |
| Cache | `method_stamp` already adds `:gpu`; GPU and CPU fills cannot collide |
| Tests | `tests/test_fill_device.py` — default, validation, fallback, estimate device |

Found while testing: `SettingsPatch` dropped `fill_device`, so the PATCH returned `cpu` silently.
Fixed. A stale `fill_rates.json` from before the median rule also poisoned the estimate (20.4 s a
unit, 1 h 36 min). `fill_rate` now trusts only entries with samples, and the old file was removed.

## Dev loop 2 — the bundle

| Item | Result |
|---|---|
| Requirements | `torch>=2.4`; venv resolves 2.15.0, MPS available |
| PyInstaller | `--collect-all torch`; torch lands under `_internal/torch` (565 MB) |
| Model | `build-duck-dev.sh` copies `big-lama.pt` to `Resources/base-models` |
| Bundle | 377 MB → **1.2 GB** (torch 565 MB, model 196 MB, rest unchanged) |
| Signature | ad-hoc sign still passes; sandbox entitlements intact |
| Engine | bundled core reports `gpu_ready: true`, empty `gpu_problem` |

## Dev loop 3 — the proof

Real render through the **bundled** sidecar, 1 s clip of `prj_e95348a97316`, fill device `gpu`:

| Check | Result |
|---|---|
| Render | done in **10.9 s**, 1.02 s output, 1080×1920 |
| Which chip | the fill cache holds the `big-lama.pt:…:gpu` key and not the CPU key |
| Output | OCR on frame 0: no text |
| CPU comparison | clip 1, 4.75 s: 93–232 s CPU vs 28.6 s MPS in the earlier span test |
| Estimate | with the stale rate gone: **19 min, first guess**; labelled as a guess |

## Acceptance

- [x] Both chips selectable; CPU default.
- [x] GPU unavailable is explained, never a fake toggle.
- [x] Device in the estimate and in the cache key.
- [x] Torch and the GPU model in the bundle; 1.2 GB.
- [x] A real GPU render from the bundle, OCR clean.
- [x] 98 tests pass.

## Not tested

- GPU memory outside process RSS (the bench reports RSS only).
- Long GPU renders and thermal throttling on an 8 GB M1.
- MPS variance: one span run, one render.
- Notarization with the torch dylibs (App Store is paused).

## Next

Loop 4: full render of the review project, now a founder choice of chip. CPU estimate ~19 min
(seed) to ~28 min (measured average); GPU measured 4.6× faster on a span.
