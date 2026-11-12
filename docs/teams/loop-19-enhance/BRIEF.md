# Loop 19 brief — Enhance, phase 3

Request: **REQ-20261112-04** (revision: Cut phase 3).

> "enhance quality so 360p can be select to expand to 1080p here."

## What must exist

1. Cut → Enhance names the source and output size and whether an upscale is added.
2. A small source gets a **Lanczos upscale** toggle and a **Sharpen** slider (0–100).
3. The render uses `flags=lanczos+accurate_rnd` and `unsharp` only when the output is larger than the
   source.
4. The UI states plainly: **no new detail**.
5. A 1080p source shows no controls and says no upscale is added.

## Not in this phase

A CoreML super-resolution pack. Research only (licence + M1/8 GB benchmark) before any offer.

## Acceptance

| Probe | Pass |
|---|---|
| 640×360 project | text `640×360 → 1920×1080`; two controls |
| Toggle + Sharpen 60 | saved as `{enabled: true, sharpen: 60}` |
| Proof frame | 1920×1080; sharpness rises vs enhance off |
| 1920×1080 project | no controls; “No upscale is added” |
| Neutral / disabled | chain unchanged |
