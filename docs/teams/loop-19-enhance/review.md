# Loop 19 review — Enhance

**Verdict: pass.** Request REQ-20261112-04, phase 3. CoreML super-resolution is **not** built.

## Behaviour

Cut → Enhance compares the source with the Cut output. When the output is larger, it offers
**Lanczos upscale** and **Sharpen** (0–100). The render adds `flags=lanczos+accurate_rnd` to the
scale filter and `unsharp=5:5:<amount>:5:5` after it. On a 1920×1080 source the card has no controls
and says no upscale is added.

## Probes

| Probe | Result |
|---|---|
| 640×360 project, Cut tab | text **640×360 → 1920×1080**, **2** controls |
| Toggle on, Sharpen 60 | saved `{"enabled": true, "sharpen": 60}` |
| Proof frame through the render path | **1920×1080** |
| Sharpness, enhance off → on | Laplacian variance **8.1 → 14.2** (1.75×) |
| 1920×1080 project | **0** controls; “Source is 1920×1080 … No upscale is added” |
| Disabled or source ≥ output | no `lanczos`, no `unsharp` in the chain (tests) |

## Quality benchmark, 360p → 720p against the original frame

| Upscale | PSNR | Laplacian variance |
|---|---|---|
| bicubic (old default) | 36.03 | 18.3 |
| lanczos | 36.20 | 19.5 |
| lanczos + unsharp 1.5 | **40.21** | **35.4** |
| original 720p frame | — | 40.7 |

Lanczos lifts edges; unsharp closes most of the remaining gap to the original's edge energy. It does
not recover detail — the UI says so.

## What got worse

- Enhance is one more Cut card; four controls in a 320 px inspector.
- Sharpen can halo at 100; no per-shot tuning.
- Output resolution is fixed at 1080-class; there is no 720p/4K picker.
- Lanczos costs a little more time than bicubic; not measured here.

## Not tested

- Full render with Enhance, 10-bit/HDR sources, anamorphic pixels.
- The optional CoreML pack: licence and M1/8 GB benchmark still open.
- 1280×800 capture of the 360p card.
