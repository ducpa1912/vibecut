# Loop 3C review — Core ML independent review and fix attempt

**Verdict: Core ML is not promotable; PyTorch stays the default.** The code defects that could be fixed without a working coremltools install are fixed. The native abort, drift and speed gates are not met.

## Evidence (from the recorded runs, re-read this session)

| Gate | Measured | Source |
|---|---|---|
| Native abort | SIGABRT `shape.count = 0 != strides.count = 4` after **8** completed bucket calls, on the **9th** function (512×256); **one run only**, no repeat/per-bucket isolation | `build/coreml-lama/evidence/coreml-memory.log`; `review.md:52-57` |
| Drift, exact buckets | **5–19/255**; all 11 exceed 3/255 (best 5 at 64×512 and 128×512, worst 19 at 512×512) | `buckets-safe.json` |
| Drift, coarse padding | up to **169/255**, mean hole 11.57; the gate now refuses those sizes | `measurements.md:19-29`; `review.md:58-61` |
| Warm speed | 0.57×–7.76× PyTorch; slower at 512×384 (0.57×), 384×512 (0.66×), 512×512 (0.83×) | `buckets-safe.json` |
| Cold / cached load | **32.362 s / 3.500 s** Core ML vs 2.801 / 2.395 s PyTorch | `buckets-safe.json` |
| Peak RSS | **854,654,976 B** vs 402,718,720 B PyTorch | `coreml-memory.json`, `pytorch-memory.json` |
| Real span | 15 frames, crop 540×240: Core ML **fell back**; the equal pixels are PyTorch's; 21.613 vs 13.737 s, load 52.968 vs 3.136 s | `real-span.json` |
| Coverage | **9 of 42** review layers run Core ML; 33 fall back. Of 896 fitted sizes, **160** run, 736 fall back | computed from `fit`/`bucket` |
| Swap | not recorded in any Core ML evidence file | grep; only historical 4–9 GB |

The abort could not be reproduced this session: `python3 -c "import coremltools"` is missing and `build/coreml-lama/venv` is gone; the handoff's bench command cannot run. The recorded run remains the only abort evidence.

## Fixes made

- **VERSION 17.** `textfill.VERSION = 17` again. The default GPU output is still PyTorch's and is unchanged; a Core ML clip already carries a separate `:coreml-gpu` stamp (`method_stamp`), so every existing fill cache stays valid. If Core ML is promoted later, the version must move to 18 with the pixel change.
- **A fallback span is now ephemeral.** `prepare_span` marks a fallback/mixed clip `ephemeral`; `render_frame` and `render_edit` delete it after the encoder has read it. It no longer leaves `.fallback-<uuid>.mp4` files in the fill directory forever.
- **Unknown GPU engine names no longer enable Core ML.** Only `DUCK_FILL_GPU_ENGINE=coreml` selects it; `onnx`/any other value falls back to PyTorch. `GPU_ENGINES` is now the validated set.
- **Compile destination and fallback-cache identity** were already correct in `02d04a3` (`.mlmodelc` temp path; `cache_valid`; primary-key rejection) and were re-read here.

## 3C acceptance

| Item | Result |
|---|---|
| 1. Reproduce abort, find trigger | **Fail/partial.** One recorded abort at the 9th function; no repeat, no per-bucket isolation, no working coremltools to rerun. Trigger unknown. |
| 2. FLOAT32 for worst buckets; 57 exact shapes | **Fail/not done.** Converter is FLOAT16 only; 11 buckets remain; drift stays 5–19/255. |
| 3. Promote only on all gates | **Fail.** Abort ×3, ≤3/255, real-span parity, faster cold and warm are not met. PyTorch remains default. |
| 4. VERSION decision | **Pass.** 17; default pixels unchanged; Core ML stamp separates. |
| 5. Rebuild and founder test | **Blocked.** `founder-test.md` still says blocked; no real-app Core ML check. |

## What got worse

- The 112 MiB Core ML package remains in the bundle while unused by default; it adds ship size and per-start seed hashing.
- A Core ML attempt can still abort the process natively; Python cannot catch it, so a render would die.
- The gate refuses most real boxes, so Core ML is slower once fallback is counted.

## Not tested

- Any real Core ML load/run this session (no coremltools, no venv).
- FLOAT32 conversion, 57-shape package size/time, swap use.
- The founder hand test.
