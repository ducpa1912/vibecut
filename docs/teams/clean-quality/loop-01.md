# Clean Quality — Loop 1 baseline

Date: 2026-11-07  
Fixture: `check-smoke`, project `prj_9542d62ce105`, 45.833 s, 1080 × 1080, 24 fps  
Edit: `ed_093ff8d3935c`, 80 clean layers (all `fill`), 35 caption cues, caption burn off  
Source: `/Users/happynghia/vibecut-lanes/ducksuite/imports/4f5eb64dd156/source.mp4`  
Scope: Loop 1 only. No product code or plan changed.

## 1. Verdict

**BASELINE COMPLETE** for the P0 scope: scene 01, scene 07, and the scan cadence. The full 12-scene baseline is listed as an open item.

- The P0 proof/render mismatch is reproduced at scene 01.
- The exact pipeline difference is identified: the proof uses the raw OCR box and a whole-box LaMa hole; the render uses a padded box and a per-frame text mask.
- Scene 01 and scene 07 are measured.
- The scan is audited. Actual text pass is 4 fps. The docstring still says 2 fps, and `extract_text_frames` silently clamps every request above 4 fps to 4 fps.
- Loop 2 cannot pass yet. The proof is still dirty, and the render itself still leaves a small dark artifact at 1.8 s.

## 2. Test method and timings

Environment: dev core `http://127.0.0.1:8797`, bearer token `review-token`. Health reported data root `/Users/happynghia/vibecut-lanes/ducksuite`. Vision helper and LaMa model were available.

Read-only test method. No product source or edit JSON was changed. Proof JPGs and the two short render MP4s are runtime artifacts under the project data directory.

1. Read the edit JSON, `check/source_report.json`, and the clean/fill code paths.
2. Pulled source frames with `GET /api/projects/prj_9542d62ce105/frame?time=...&t=review-token`.
3. Generated proofs with `GET /api/projects/prj_9542d62ce105/edits/ed_093ff8d3935c/clean/preview?time=...&t=review-token`.
4. Ran short renders through the real `duckcore.render.render_edit` with an in-memory copy of the edit clipped to scene 01 (`0.0–3.625`) and scene 07 (`23.25–28.5`). The saved edit was not modified.
5. Extracted frames from the short renders with ffmpeg.
6. Measured mask geometry with `duckcore.engine.textfill.mask`, OCR with `duckcore.engine.vision.probe_images`, dark components with `scipy.ndimage.label`, and color/edge deltas with NumPy/Pillow.
7. Ran the text pass at 1 / 2 / 4 / 8 fps with `pipeline.read_text_samples` on the full fixture. A true 8 fps run on the scene 01 and scene 07 windows used direct ffmpeg extraction because the product function clamps to 4 fps.

Timings:

| Action | Observed |
|---|---:|
| Fresh proof at 0.84 s (2 active layers) | 13.46 s |
| Fresh proof at 1.8 s (5 active layers) | 33.20 s |
| Fresh proof at 25.88 s (2 active layers) | 6.91 s |
| Cached proof at 0.83 / 1.47 / 25.875 s | 0.01–0.02 s |
| Short render, scene 01 clip 0.0–3.625 s | 1.28 s, fill cache hit, 87 frames |
| Short render, scene 07 clip 23.25–28.5 s | 75.70 s, cold fill, 126 frames |
| Text pass 1 fps, full fixture | 13.2 s, 46 frames, 37 tracklets |
| Text pass 2 fps, full fixture | 20.7 s, 92 frames, 63 tracklets |
| Text pass 4 fps, full fixture | 38.5 s, 183 frames, 80 tracklets |
| Text pass 8 fps request, full fixture | 36.5 s, 183 frames, 80 tracklets — clamped to 4 fps |
| True 8 fps OCR, scene 01 window | 9.64 s, 29 frames |
| True 8 fps OCR, scene 07 window | 6.05 s, 42 frames |

The short renders are diagnostic artifacts, not queue jobs:

- `/Users/happynghia/vibecut-lanes/ducksuite/projects/prj_9542d62ce105/renders/ed_093ff8d3935c_20261107-232703.mp4` (scene 01 clip)
- `/Users/happynghia/vibecut-lanes/ducksuite/projects/prj_9542d62ce105/renders/ed_093ff8d3935c_20261107-232800.mp4` (scene 07 clip)

The scene 01 clip hit fill cache key `4eb2ca8dddb5247a5012`, computed from the current 80-layer edit. The scene 07 clip wrote key `61229d184b335647601a` after a cold fill. This confirms the scene 01 render used the current layer set, not an old cache.

## 3. Proof/render mismatch

**Reproduced.** Same source, same 80-layer clean set, same time. The `/frame` endpoint returns the source frame with text present; it is the reference input, not a clean output. The disagreement is between the clean preview endpoint (`render_clean_preview`) and the render path (`render_edit` / `prepare_span`).

| Time | Proof | Render | Result |
|---:|---|---|---|
| 0.83 / 0.84 s | Large black “if” blob in the top-left; smeared sky | Clean top-left; no black component | P0 mismatch |
| 1.47 s | Same black “if” blob | Clean top-left | P0 mismatch |
| 1.80 s | Black “if” blob, 4,931 px; smeared mountain | Clean of the “if” glyph, but a 242 px dark pill at (195, 336)–(216, 348) | Mismatch plus render P1 |
| 25.875 s | Clean; faint smudge where “obviously” was | Clean | Control holds |

Images:

- Proof, scene 01, 0.83 s: `/Users/happynghia/vibecut-lanes/ducksuite/projects/prj_9542d62ce105/previews/ed_093ff8d3935c_830.jpg`
- Proof, scene 01, 1.813 s: `/Users/happynghia/vibecut-lanes/ducksuite/projects/prj_9542d62ce105/previews/ed_093ff8d3935c_1813.jpg`
- Proof, scene 01, 1.47 s: `/Users/happynghia/vibecut-lanes/ducksuite/projects/prj_9542d62ce105/previews/ed_093ff8d3935c_1470.jpg`
- Proof, scene 07, 25.875 s: `/Users/happynghia/vibecut-lanes/ducksuite/projects/prj_9542d62ce105/previews/ed_093ff8d3935c_25875.jpg`
- Render frame, scene 01, 0.83 s: `/private/var/folders/m_/jn7hsp456dvff8hrf0lmtgqm0000gn/T/opencode/cq-loop01/render_0.83.png`
- Render frame, scene 01, 1.8 s: `/private/var/folders/m_/jn7hsp456dvff8hrf0lmtgqm0000gn/T/opencode/cq-loop01/render_1.8.png`
- Render frame, scene 07, 25.875 s: `/private/var/folders/m_/jn7hsp456dvff8hrf0lmtgqm0000gn/T/opencode/cq-loop01/render_25.875.png`
- Source frame, scene 01, 1.8 s: `/private/var/folders/m_/jn7hsp456dvff8hrf0lmtgqm0000gn/T/opencode/cq-loop01/source_1.8.png`

Freshness check: a new proof at 1.8 s took 33.20 s and was byte-identical (MD5) to the cached `1813.jpg`. A new proof at 0.84 s took 13.46 s and reproduced the same black blob as `830.jpg`. The mismatch is not explained by a stale preview cache on this run.

Pixel difference at the same time:

| Time | Mean abs difference | 99th percentile | Pixels within 10 levels |
|---:|---:|---:|---:|
| 0.84 s | 8.08 | 76 | 80.0% |
| 1.47 s | 12.97 | 76 | 60.4% |
| 1.80 s | 12.44 | 73 | 60.0% |
| 25.875 s | 6.35 | 35 | 84.3% |

## 4. Root cause

### 4.1 Proof uses the raw OCR box, with no padding and no text mask

`duckcore/preview.py:26-39` (`_pixel_box`) converts the layer box directly to pixels. It does not call `duckcore.engine.textfill.mask.layer_rect`, so it applies none of the padding the render uses:

- `PAD_RATIO = 0.06` of box height
- `TEXT_SHADOW_RATIO = 0.18` of box height, minimum 6 px, for tracklet layers

`duckcore/preview.py:78-83` then calls `textfill.fill_frame(frame, [box], ...)` with no `tight_rects`. In `duckcore/engine/textfill/__init__.py:1261-1270`, missing `tight_rects` means the hole is the entire raw rectangle (`rasterize(local)`), not the text pixels.

Consequence at scene 01, first layer `cl_23e5d8ca97` (OCR sample `iivoutre the`; visually “if you’re the”):

- Raw box: `(68, 79) – (643, 254)`
- Render padded box: `(36, 47) – (675, 286)`
- The “if” ascender starts at about y = 57, 22 px above the raw box.
- Proof dark component: 6,010 px, bbox `(71, 57) – (162, 147)`, mean luma 3.4.
- Above the raw box (y 57–79): proof is 97.2% identical to source and 69.8% black. The glyph top is literally untouched.
- Inside the raw box (y 79–147): proof is still 69.8% black and 49.9% identical to source. The fill did not remove the glyph; it kept or reconstructed it. The un-masked glyph top directly above the hole is the likely continuation cue.
- Render at the same bbox: 0% black above and inside; the padded hole and text mask remove it.

This is the P0. The proof’s hole is too small and too rectangular.

### 4.2 Proof fills the whole rectangle; render fills text pixels

`fill_frame` uses `hole = rasterize(local)` when no `tight_rects` are passed. For scene 01’s large title box (864 × 295 px), LaMa receives a hole covering the entire title block, including sky and mountain. The proof visibly smears the mountain and sky. The render’s `TextMasks` narrows the hole to detected text pixels plus growth, so it preserves most background texture.

### 4.3 Proof fills layers one by one; render combines them

`duckcore/preview.py:66-83` loops active layers and calls `fill_frame` once per layer. Each call starts from the already-filled frame. The render builds one per-frame rect table (`mask.frame_rects`), removes contained rects, merges overlapping work areas (`mask.without_contained`, `mask.lama_areas`), and runs LaMa once per area.

Scene 01 has overlapping and duplicate layers:

- `cl_b8f8fc3e4b` (“person.”) overlaps `cl_10c3e80bb0` (large title).
- `cl_b0ea203c4c` (“inthe”) is contained inside the large title.
- The large title is split into “Smartest” plus “you’re … room”, with a separate “person.” layer.

The proof double-fills the overlap. The render drops the contained “inthe” rect. That is another source of different pixels and smears.

### 4.4 Proof runs one fill; render uses keyed temporal blending

`fill_frames_lama` / `_fill_frames_by_runs` (`duckcore/engine/textfill/__init__.py:876-1148`) runs LaMa on key frames, unions holes across the run, blends with `LAMA_CARRY = 0.3`, and blends between key fills. The proof runs one plain `filler.fill` at one frame. Even with identical masks, a preview frame is not the render’s frame at that time.

### 4.5 The scan’s fill plan is not persisted

`duckcore/clean.py:25-68` (`layers_from_report`) copies `box`, `ranges`, `kind`, `tracklet_id`, text and confidence. It drops `tracklet["fill_plan"]`. The edit layers therefore have no `fill_keys`.

`duckcore/engine/textfill/mask.py:155` reads `layer.get("fill_keys")`; `textfill/__init__.py:639-662` then falls back to the default key cadence (3 fills/s) for every scan layer. The motion plan computed by `detect.plan_fills` is ignored. This does not cause the P0 blob directly, but it makes render behavior differ from the per-tracklet plan and can add smears or unnecessary model runs.

### 4.6 The render has its own mask-coverage defect

At 1.8 s, the render’s 242 px dark pill comes from the “person.” layer `cl_b8f8fc3e4b`, not from the preview path.

- Raw box `(84, 332) – (567, 446)`, padded `(63, 311) – (588, 466)`.
- `text_in_region` detects only 15,453 text pixels; the source has 30,294 black pixels in the padded box.
- The enlarged hole covers 98.53% of those black pixels. 444 black pixels remain; the largest connected remainder is the 242 px pill at `(195, 336) – (216, 348)`.
- `text_in_region` uses `limit = max(36, 2.5 × percentile(contrast, 30))` (`mask.py:398-401`). Large dense display text raises the percentile and suppresses real glyph strokes. The 98% coverage target is met by this black-pixel proxy, but a 1.5% miss on a huge solid glyph is still visible.

So the render is not yet clean either. This is a distinct P1 from the proof P0.

### 4.7 Cache and time extraction

`duckcore/main.py:518` accepts a cached proof if `st_mtime >= edit.updated - 1.0`. The UI sends `v=cleanVersion`, but the endpoint does not read it. A proof generated up to one second before an edit can be reused. This is a real parity risk for rapid edits (matches the P2 in `user-test-01.md`), but it is not the cause of this P0: fresh 0.84 s and 1.8 s proofs reproduced the same damage.

The proof extracts a frame at `when` via `media.extract_frame`; the render consumes frames from the clip start at the source fps. The proof is not asserted to be the same decoded frame as the render. At this fixture’s midpoint the two happen to match closely, but the code does not guarantee it.

### 4.8 Blur is not implemented in the render path

`duckcore/render.py:55-61` (`_fill_layers`) returns only `kind == "fill"`. `render_edit` never applies a `kind == "blur"` layer. `preview.render_clean_preview` does apply a Gaussian blur for blur layers. This edit has 80 fill layers and 0 blur layers, so it did not affect these measurements, but any user who chooses Blur gets a proof/render disagreement.

## 5. Metrics

Method: “text pixels” are contrast-detected pixels inside the padded layer box using the product’s `text_in_region`; preview coverage is the share inside the raw preview box; render coverage is the share inside the render’s `TextMasks` hole. “Largest dark component” is the largest connected `luma < 40` component inside the padded union, using 4-connectivity. “Outside delta” is the mean max-channel difference outside the padded union. “Halo edge” is the mean gradient in the 6 px ring outside the padded union, relative to source. The proof is JPEG quality 90 and the render is H.264, so outside-delta values include codec noise; they are not pure color-shift measurements.

### Scene 01, 0.83 s

Active layers: 2.

| Metric | Proof | Render |
|---|---:|---:|
| Black ratio in raw union | 1.828% | 0.000% |
| Dark vs 35% ring median | 2.032% | 0.000% |
| Largest dark component | 6,010 px, `(71,57)–(162,147)`, mean luma 3.4 | none |
| Full-frame OCR | 0 lines | 0 lines |
| Source OCR | 2 low-confidence lines, 0.3 | — |
| Preview text coverage, first layer | 78.97% | 100% of same detector |
| Preview text coverage, “Smartest” | 81.68% | 100% of same detector |
| Outside mean abs delta | 2.91 | 6.03 |
| Halo edge ratio | 1.041 | 0.430 |
| Halo luma delta | +0.03 | −3.06 |

Proof/render MAD: 7.97; 80.3% of pixels within 10 levels.

### Scene 01, 1.80 s

Active layers: 5.

| Metric | Proof | Render |
|---|---:|---:|
| Black ratio in raw union | 0.572% | 0.040% |
| Dark vs 35% ring median | 2.512% | 0.459% |
| Largest dark component | 4,931 px, `(71,57)–(162,132)`, mean luma 2.9 | 242 px, `(195,336)–(216,348)`, mean luma 2.9 |
| Full-frame OCR | 0 lines | 0 lines |
| Preview text coverage, first layer | 78.97% | 100% of same detector |
| Preview text coverage, “Smartest” | 81.23% | 100% of same detector |
| Preview text coverage, “person.” | 82.07% | 100% of same detector |
| Preview text coverage, large title | 67.67% | 100% of same detector |
| Preview text coverage, “inthe” | 71.03% | 100% of same detector |
| Render hole vs source black pixels, first layer | — | 100.00% |
| Render hole vs source black pixels, “Smartest” | — | 99.88% |
| Render hole vs source black pixels, large title | — | 99.67% |
| Render hole vs source black pixels, “person.” | — | 98.53% (444 px uncovered) |
| Outside mean abs delta | 3.59 | 6.41 |
| Halo edge ratio | 1.017 | 0.779 |
| Halo luma delta | +0.02 | −1.18 |

Proof/render MAD: 12.44; 60.0% of pixels within 10 levels.

The proof fails the plan’s dark-artifact target (2.512% > 2%). The render passes the 2% ratio, but the 242 px solid pill is visible and must be treated as P1. The ratio-only gate is too loose for large flat regions; the largest-component size is the better gate.

### Scene 07, 25.875 s

Active layers: 2 (`was`, `obviously`).

| Metric | Proof | Render |
|---|---:|---:|
| Black ratio in raw union | 0.000% | 0.000% |
| Largest dark component | none | none |
| Full-frame OCR | 0 lines | 0 lines |
| Source OCR | `obviousty`, 0.3 | — |
| Preview text coverage, “obviously” | 89.94% | 100% of bright text pixels |
| Preview text coverage, “was” | 82.11% | 100% of bright text pixels |
| Render hole vs source bright pixels (>235) | — | 100.00% (20,495 px) |
| Outside mean abs delta | 2.55 | 5.11 |
| Halo edge ratio | 1.010 | 0.776 |
| Halo luma delta | −0.04 | −1.01 |

Proof/render MAD: 6.35; 84.3% of pixels within 10 levels.

Scene 07 remains the control: no dark component, no residual OCR, no visible text. The proof is slightly smoother than the render on the mountain, but both pass the product’s plain-language test.

### Residual-text metric limitation

Apple Vision found zero text lines on every cleaned frame, including the proof with the obvious 6,010 px black “if” blob. It also read the source title poorly: 0.3 confidence, `iyoure te`, `Srartest`, `OeSOn`. OCR at 1080 px is not a reliable gate for this stylised display type. The dark-component metric caught the failure; OCR did not. Loop 2 must keep both, and must not accept “OCR 0” alone.

## 6. Scan-density finding

Actual full-file text pass:

| Requested fps | Frames | Tracklets | Scene 01 tracklets | Scene 07 tracklets | Notes |
|---:|---:|---:|---:|---:|---|
| 1 | 46 | 37 | 6 | 4 | Merged lines; misses most short words |
| 2 | 92 | 63 | 9 | 8 | Misses `me` and `obviously` in scene 07 |
| 4 | 183 | 80 | 8 | 10 | Baseline; matches `source_report.json` |
| 8 | 183 | 80 | 8 | 10 | Silently clamped to 4 fps |

True 8 fps on the scene windows (direct ffmpeg, outside the product cap):

- Scene 07: 42 frames, 13 tracklets. Adds `were`, `the`, and `least` versus 4 fps. It detects `obviously` at 26.062–26.438 instead of 25.875–26.375.
- Scene 01: 29 frames, 9 tracklets, but `Smartest` is fragmented into six disjoint ranges and `person.` into four ranges. A naive 8 fps pass would leave holes between ranges.

Findings:

1. **1 fps is a regression, not a saving.** It merges scene 01 title lines into long fake tracklets (`ifyouiret Gmaferf`, `Ia the youre room`) and misses most of scene 07. Do not lower the global scan to 1 fps.
2. **2 fps already misses text on this fixture.** It misses `obviously` entirely, so the verified control would disappear at 2 fps discovery. It also misses `me`. A 1–2 fps discovery pass cannot stand alone.
3. **4 fps is the current baseline and is sufficient for this fixture at discovery level**, but it still misses the very short `were` / `the` / `least` words in scene 07 compared with true 8 fps.
4. **8 fps is not actually available.** `duckcore/engine/pipeline.py:877` caps `cadence` at `4.0`:
   `cadence = min(max(float(fps or CHECK_SAMPLE_FPS), 0.05), 4.0)`
   A request for 8 fps returns 183 frames, exactly the 4 fps count. The plan’s “8–12 fps refinement” cannot be implemented through this function without a code change.
5. **Raising fps alone fragments tracklets.** True 8 fps splits the animated scene 01 title into disjoint ranges. Refinement needs stable tracklet clustering and propagation, not just more samples.

Recommended scan design:

- Keep 4 fps discovery for short sources (this 46 s fixture).
- For long sources, use 2 fps discovery plus every scene-boundary frame, but only if every detected text region triggers an 8–12 fps refinement pass. Because 2 fps can miss a 0.5 s word entirely, add a text-change trigger or fall back to 4 fps when the source is short.
- Lift the 4 fps cap and add a separate refinement cadence argument.
- Refine 8–12 fps inside each detected text range and add the first and last frame of each range.
- Stabilise tracklets before increasing cadence: bridge short gaps, keep per-sample boxes, and do not split an animated title into six disjoint ranges.
- Never use a global 1 fps pass.

Stale comments to fix with the code:

- `duckcore/engine/pipeline.py:865-867` says the default is 2 fps; the constant is 4.0.
- `duckcore/engine/detect.py:47-49` says the scan reads two frames a second and edges are within a quarter second; the actual rate is 4 fps.
- `duckcore/engine/textfill/mask.py:24-26` says the scan reads two frames a second; the actual rate is 4 fps.

## 7. Loop 2 fix list

Priority P0 — required before Loop 2 can pass.

| # | File / function | Fix | Why |
|---:|---|---|---|
| 1 | `duckcore/preview.py::render_clean_preview`; `duckcore/engine/textfill/__init__.py::fill_frame` | Replace the raw-box `fill_frame` path with a shared render-frame path. Use `mask.layer_rect`, `mask.frame_rects`, `mask.TextMasks`, the combined rect table, `without_contained`, `lama_areas`, and `fill_frames_lama` with the same key/carry state. The proof must be an actual frame from the render pipeline, not a separate approximation. | Removes the P0 proof/render mismatch by construction. |
| 2 | `duckcore/engine/textfill/mask.py::layer_rect`, `TextMasks._measure`, `text_in_region` | Make the hole glyph-complete. For title/large layers, increase padding and dilation; lower the contrast limit or fall back to the full padded box when the detector cannot cover a dense glyph. Add a check that every dark/bright text component is fully inside the hole. | Fixes the render’s 242 px pill and prevents the proof’s glyph continuation. |
| 3 | `duckcore/render.py::_fill_layers` and `render_edit` | Implement `kind == "blur"` in the render path with the same box and radius as preview, or explicitly reject blur in render instead of silently leaving text. | Product P0 parity for the Blur action. Not exercised on this all-fill edit; if Blur is out of Loop 2 scope, product must mark it Blur/Off and not claim it clean. |
| 4 | `duckcore/clean.py::layers_from_report` | Persist `fill_plan` / `fill_keys`, per-sample boxes, and the sample rate on the clean layer. | The scan’s motion plan is currently dropped; render always uses the default 3 keys/s. |
| 5 | `duckcore/engine/detect.py::_line_tracklets`, `build_tracklets`; `duckcore/engine/textfill/mask.py::frame_rects` | Keep per-sample boxes and ranges; interpolate or propagate the box per frame; use the per-frame box for the hole instead of one static union box. | Fixes moving/scaling titles and the scene 01 range fragmentation. |

Priority P1 — Loop 2 quality, can land with or immediately after P0.

| # | File / function | Fix | Why |
|---:|---|---|---|
| 6 | `duckcore/engine/detect.py::_line_runs`, `_run_range`, `_line_tracklets` | Frame-accurate start/end; bridge OCR gaps inside one line; do not start a new run on every small box change. Use scene-boundary frames. | 8 fps currently fragments the scene 01 title. |
| 7 | `duckcore/engine/pipeline.py::extract_text_frames` | Remove the hard `4.0` cadence cap; add a refinement cadence and range-limited extraction. Fix the 2 fps docstring. | The planned 8–12 fps pass is impossible today. |
| 8 | `duckcore/engine/textfill/lama.py::fit` (`SIZE = 512`); `mask.lama_area` | Raise the crop resolution for large titles (for example 768 or 1024, or tile the work area) and keep enough context without downscaling the glyph block to 512 px. | Large-title fills currently run at low resolution. |
| 9 | `duckcore/main.py::clean_preview` | Key the proof cache on the edit hash or the UI’s `v` value; remove the `edit.updated - 1.0` tolerance. | Stale proof risk after rapid layer changes. |
| 10 | `duckcore/preview.py` / test harness | Sample proofs at first frame, midpoint, last frame, and the frame with the largest mask area, not only the scene midpoint. | One midpoint cannot prove a moving title. |

Priority P2 — measurement and gate.

| # | File / function | Fix | Why |
|---:|---|---|---|
| 11 | New test harness under `tests/` or a script under `docs/teams/clean-quality/` | Record residual OCR, largest dark component, mask coverage, outside delta, halo edge, and proof/render MAD for scenes 01, 04, 07, 08. | Loop 2 needs the same numbers every run. |
| 12 | Proof/quality gate | Reject a proof with any dark component above 20 px in a title region, even when the black-ratio target is met. Require ≥99.9% mask coverage for title glyphs, ≥99% for subtitles, and zero uncovered components. | The current 2% ratio and 98% coverage targets passed a visibly damaged proof. |

## 8. Failures and open questions

- **Render is still dirty at 1.8 s.** The 242 px dark pill is a P1. It is not fixed by proof parity alone.
- **OCR cannot see the damaged proof.** Full-frame OCR returned zero lines on all cleaned frames. It is not a sufficient quality gate for large stylised type.
- **Only scenes 01 and 07 were measured.** The plan’s all-12-scene baseline was not run in this loop. Loop 2 should use 01/04/07/08 as planned, but the other scenes remain unmeasured.
- **8 fps is not available in the product.** The request was clamped to 4 fps. The true 8 fps result was produced with direct ffmpeg, outside the product path.
- **True 8 fps fragments scene 01.** More samples improve recall on short words but break tracklets on the animated title. Clustering must be fixed before raising the cadence.
- **Blur render path is missing.** This edit has no blur layers, so it did not affect the measured frames, but a user who selects Blur will see a proof/render mismatch.
- **Fill plan is dropped.** `clean.py` does not persist `fill_plan`; render ignores the scan’s motion plan.
- **Proof time is not frame-asserted.** A proof at time `t` and a render frame at time `t` can be different decoded frames. Parity needs one shared frame selector.
- **Proof cache can be one second stale.** Fresh proofs reproduced the P0, so this is not the current cause, but the `v` parameter is unused and the cache window is unsafe.
- **Full 46 s render was not run.** Only scene 01 and scene 07 clips were rendered. Full-edit proof parity remains unverified.
- **Layer set is noisy.** Scene 01 has 8 layers, including a contained “inthe” layer and a “person.” layer overlapping the large title. Detection/merge quality contributes to both the proof and render behavior.
- **The 1.8 s render artifact is a mask miss, not a preview differ.** It comes from `text_in_region` detecting only 15,453 of 30,294 black text pixels in the “person.” box, then relying on dilation for the rest.

## 9. Product gate: what must be true before Loop 2 can pass

1. The scene 01 proof is an actual render frame, produced by the same all-layer pipeline as the export, at the first frame, midpoint, last frame, and the frame with the largest mask area.
2. Scene 01 at 0.83 s, 1.8 s, and 3.6 s shows no black blob, no visible glyph, no smeared sky/mountain, and no halo at full size. Product reviews the images, not only the metrics.
3. The render at 1.8 s has no dark component above 20 px and no residual glyph fragment.
4. The proof and render at the same time agree structurally inside the mask: same content, no black blob, no residual glyph, no halo. The proof/render MAD outside the mask is at production encode noise, not a visible difference.
5. Mask coverage is ≥99.9% of source text pixels for title/large-text layers and ≥99% for subtitles, with zero uncovered connected components above 20 px.
6. Residual OCR is zero, but OCR is backed by the dark-component and mask-coverage gates. “OCR 0” alone does not pass.
7. Scene 07 remains the clean control: no dark component, no residual text, no visible smudge beyond the current acceptable level.
8. No P1 remains on the fixture. The render’s 1.8 s pill and the proof’s black blob are both closed.
9. The scan keeps 4 fps discovery for this fixture, or a documented adaptive equivalent, and does not downgrade to 1 fps. The 8–12 fps refinement path exists and does not fragment scene 01 tracklets.
10. If Blur remains a shipped Clean action, its render path matches the proof. If Blur is out of Loop 2 scope, product marks it Blur/Off and does not claim it clean. Fill has no silent fallback.
11. The plan’s Loop 1 requirement is met: the P0 is owned, the harness produces the same metrics, and product accepts the pass/fail language. Loop 2 starts only after this record is accepted.
