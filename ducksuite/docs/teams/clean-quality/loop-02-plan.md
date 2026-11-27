# Loop 2 — Mask and tracklet: implementation plan

Date: 2026-11-07, revised 2026-11-08 after Loop 1 baseline  
Owner: Clean Quality / Engineer (implementation), Tester (harness), Product (gate)  
Status: **plan only; baseline reconciled**  
Fixture: `prj_9542d62ce105`, full edit `ed_093ff8d3935c`, 45.833 s, 1080 × 1080, 24 fps, 12 scenes.  
Torture case: scene 01, `0.000 – 3.625 s`.  
Control: scene 07, `23.250 – 28.500 s`; “obviously” at `25.875 s`.

Baseline: `docs/teams/clean-quality/loop-01.md` (BASELINE COMPLETE) was read before this revision. This plan is reconciled to it. It remains a plan, not a quality claim. The baseline owns the measurements and the P0 root-cause record.

This session writes only this file. No product code, tests, UI, or baseline report is edited here.

## 0. Baseline findings adopted

Do not repeat the baseline measurements. Loop 2 uses these findings:

- **P0 proof/render mismatch.** The proof uses the raw OCR box and a whole-box LaMa hole; the render uses a padded box plus per-frame `TextMasks`. The proof fills layers one at a time with one plain `fill_frame`; the render uses a combined rect table, `without_contained`, `lama_areas`, and keyed `fill_frames_lama` with carry/blend. This is structural, not a stale cache. (loop-01 §3–4, §7 #1)
- **Render P1 at 1.8 s.** The render leaves a 242 px dark pill from the “person.” layer because `text_in_region` misses dense glyph pixels. The old 98% coverage target passed a visibly damaged frame; the largest dark component is the better gate. (loop-01 §4.6, §5)
- **Fill plan is dropped.** `clean.layers_from_report` does not persist `fill_plan` / `fill_keys`; the render ignores the scan’s motion plan and uses the default key cadence. (loop-01 §4.5)
- **8 fps is clamped to 4 fps.** `pipeline.extract_text_frames` caps cadence at 4.0. A true 8 fps pass fragments scene 01 into disjoint ranges unless clustering and per-sample boxes are fixed. (loop-01 §6)
- **Blur is not implemented in render.** `render._fill_layers` returns only `kind == "fill"`; the preview does apply a Gaussian blur. A Blur selection currently produces a proof/render disagreement. (loop-01 §4.8)
- **Proof cache can be stale.** The endpoint does not read `v`, and it accepts a proof with `st_mtime >= edit.updated - 1.0`. (loop-01 §4.7)
- **OCR alone cannot pass the gate.** Apple Vision returned zero lines even on the visibly damaged proof; the dark-component and coverage gates must stand beside OCR. (loop-01 §5)
- **Scene 07 holds.** It is the control. The full 12-scene baseline is still open; Loop 2 uses scenes 01, 04, 07, and 08. (loop-01 §8)

## 0.1 Claim rule

No one may say clean quality improved unless all of these exist for the same fixture:

1. before / proof / render images for scene 01, scenes 04 and 08, and the scene 07 control;
2. a metric table produced by the same harness and thresholds for before and after;
3. proof/render parity evidence at first, midpoint, last, and largest-mask frames;
4. Product visual approval at full size;
5. Loop 1 baseline accepted as the before state.

A clean export at one time is not proof of a clean scene. A clean proof at one midpoint is not proof of a tracklet. Scene 01 is the torture case; scene 07 is the control. If scene 07 regresses, Loop 2 fails even if scene 01 improves.

## 1. Fixture evidence used to size the work

Plan-time read of `projects/prj_9542d62ce105/check.json` and the full edit:

| Item | Value |
|---|---|
| Scene 01 | `0.000 – 3.625 s`, mid `1.812 s` |
| Scene 01 clean layers | 8 fill layers |
| Scene 04 | `10.125 – 13.750 s`; “unchallenged” `10.875 – 11.875 s` |
| Scene 07 | `23.250 – 28.500 s`, mid `25.875 s` |
| Scene 07 control layer | `trk_e21ea85078`, “obviousty”, `25.875 – 26.375 s` |
| Scene 08 | `28.500 – 31.125 s` |
| Whole edit | 80 clean layers, 35 caption cues |

Largest scene 01 tracklets:

| Tracklet | Kind | Text sample | Box (x, y, w, h) | Range | Samples |
|---|---|---|---|---|---|
| `trk_d26d1da3cb` | screen_text | `iivoutre the box` | `0.063, 0.073, 0.532, 0.162` | `0.375 – 3.625` | 2 |
| `trk_c534cfee69` | screen_text | `Smartest` | `0.229, 0.175, 0.650, 0.146` | `0.375 – 3.625` | 2 |
| `trk_b8f8fc3e4b` | screen_text | `person.` | `0.078, 0.307, 0.447, 0.105` | `0.875 – 3.625` | 2 |
| `trk_913e4081d0` | title | `youre Ia the room` | `0.146, 0.375, 0.800, 0.273` | `1.375 – 3.625` | 3 |

The title box is 295 px tall and covers 21.8% of the frame. These are not subtitles; they are display type. That distinction drives the large-title path below.

Control tracklet:

| Tracklet | Kind | Text sample | Box (x, y, w, h) | Range | Fill plan |
|---|---|---|---|---|---|
| `trk_e21ea85078` | title | `obviousty` | `0.287, 0.448, 0.431, 0.109` | `25.875 – 26.375` | keys 0, still |

The baseline’s scene 01 proof/render pair and the 1.8 s render pill are the reference failure images. Loop 2 does not re-measure them before coding; it uses them as the before state and the harness reproduces them only as a control run.

## 2. Current code path and the Loop 2 gap

This is not a competing diagnosis. It records which functions Loop 2 replaces so the implementation is exact.

| Stage | Current path | Loop 2 gap |
|---|---|---|
| Proof | `main.clean_preview` → `preview.render_clean_preview` → `textfill.fill_frame` per layer | Uses the raw OCR box, with no `mask.layer_rect` padding and no `TextMasks`; the hole is the whole rectangle. Layers are filled one at a time, with one plain fill and no key/carry blend. The proof is a different algorithm from the export. |
| Render | `render.render_edit` → `textfill.prepare_span` → `mask.frame_rects` → `TextMasks` → `fill_frames_lama` | Uses per-frame text masks inside a **static union box**, fixed 4 fps time margins, and keyed runs. No per-frame track geometry. |
| Detection | `detect.build_tracklets` | Keeps `box` as the union of every observation and drops the observations. A moving or scaling title has one box for its whole life. |
| Ranges | `detect._run_range`, `_merge_ranges(..., max_gap=4.5)`, `_line_runs` | Sampled range edges are half a sample; `TRACKLET_MAX_GAP` can join two distant appearances into one track with one union box, and the first/last frames are not frame-accurate. |
| Classification | `detect._mark_screen_frame`, `classify` | A text-heavy title frame can mark every block as `screen_text` before the large-title rule runs. Large display type has no dedicated path. |
| Mask geometry | `mask.layer_rect`, `TextMasks._measure` | Padding and glyph growth scale with box height: `0.18 × h` capped only in one place and `0.18 × h × 0.7` uncapped. A 400 px box grows the glyph mask by up to 50 px. |
| Work areas | `mask.lama_area`, `lama_areas` | Context is `0.5 × h` with a 96 px floor; areas merge when their **context** overlaps. Scene 01’s title plus lower lines becomes one near-frame-sized area. |
| Model input | `lama.fit`, `prepare_feed` | Long side is capped at 512. A 970 px wide title crop is downscaled to 512 px, losing glyph edges before LaMa sees them. |
| Proof gate | `main.clean_preview`, `app.js` | A generated JPEG is treated as a proof. No metric checks it. A failed fill is not distinguished from a bad fill. The cache ignores `v` and tolerates `edit.updated - 1.0`. |
| Fill plan | `clean.layers_from_report`, `mask.frame_keys` | `fill_plan` / `fill_keys` is dropped, so the render uses the default key cadence instead of the scan’s motion plan. |
| Blur | `render._fill_layers`, `render_edit` | Blur layers are not applied in the export; the preview applies a Gaussian blur. Proof/render parity is false for Blur. |
| Scan cadence | `pipeline.extract_text_frames` | Hard cap at 4 fps; a request for 8 fps silently returns 4 fps. True 8 fps fragments scene 01 without stable clustering. |

Baseline fix-list mapping:

| Baseline item | Loop 2 section |
|---|---|
| §7 #1 shared proof/render path | §3.1 |
| §7 #2 glyph-complete mask | §3.3 |
| §7 #3 blur parity | §3.1, §3.7, §4 |
| §7 #4 persist fill plan | §3.2.1–3.2.2 |
| §7 #5 per-sample boxes / propagation | §3.2 |
| §7 #6 frame-accurate ranges / no fragmentation | §3.2, §3.6 |
| §7 #7 remove 4 fps cap / refinement | §3.6 |
| §7 #8 higher-resolution large crop | §3.5 |
| §7 #9 proof cache | §3.1, §5 |
| §7 #10 multi-frame proof | §3.1, §3.7 |
| §7 #11 harness metrics | §6.3 |
| §7 #12 stricter proof gate | §3.7, §9 |

## 3. Loop 2 design

Implementation order is deliberate:

1. **Exact shared proof/render path and frame selector** — first, because it is the measurement instrument and the known P0.
2. **Fill-keys persistence + per-sample boxes + stable range edges** — second, because the mask and key plan need the right geometry per frame.
3. **Glyph-complete mask + large-title 768 crop** — third, because that closes the render P1 and the scene 01 artifact.
4. **Blur parity** — fourth, because a shipped Blur action must agree with its proof or be refused.
5. **Range-limited refinement cadence** — fifth, because 8 fps is clamped and true 8 fps fragments scene 01 until the clustering is stable.

Do not tune mask constants against the old proof. Tune them against render frames and the baseline’s 1.8 s render pill.

### 3.1 Exact shared proof/render path

The proof must be a decoded frame from the same clip pipeline that the exporter uses. It must not be a per-layer `fill_frame` loop, a raw-box pass, or a second mask implementation.

Shared path:

```text
render_edit(clip)                         render_frame(when)
  prepare_span(start, duration, layers)     prepare_span(start, duration, layers)  # same cache key
  filled clip or source clip                filled clip or source clip
  explicit blur pass (if any)               explicit blur pass (if any)
  scale/pad/setsar/fps filter               scale/pad/setsar/fps filter
  encode every frame                        extract frame_index
```

Implementation:

- Add `render.render_frame(project, edit, data_root, when, output)`.
- Find the clip that contains `when`, exactly as `render_edit` does. Use that clip’s real `start` and `duration`.
- Call `textfill.prepare_span` with the same `layers = _fill_layers(edit)`, the same cache directory (`projects/<id>/fill`), the same method/device/follow defaults, the same combined `mask.frame_rects` table, `without_contained`, `lama_areas`, `TextMasks`, `fill_frames_lama`, key plan, and carry state. The proof and a later export share one cached filled clip.
- Add one frame selector shared by proof and render:
  ```python
  target_fps = 24 if abs(source_fps - 24.0) < 0.6 else 30
  def frame_index(when: float, clip_start: float, target_fps: float) -> int:
      return max(0, int(round((when - clip_start) * target_fps)))
  ```
  `prepare_span` still fills at source fps. The `scale/pad/setsar/fps` filter converts to `target_fps`; the proof extracts the same target index from that filtered stream. Both use the same clip start and target fps. Do not re-extract the source with `media.extract_frame` at a rounded time; that is how the baseline proof and render ended up on different decoded frames.
- Apply the same `scale`, `pad`, `setsar`, and `fps` filter that `render_edit` applies. `render_frame` extracts `frame_index` from the filtered frame stream. The proof and the export therefore share the frame, not just the timestamp.
- `render_frame` writes PNG when the output suffix is `.png` and JPEG quality 92 when it is `.jpg`. The endpoint keeps `.jpg`; the test harness asks for `.png` for lossless parity measurement.
- `preview.render_clean_preview` becomes a thin wrapper around `render.render_frame`. Its old `textfill.fill_frame` loop and `_pixel_box` path are removed.
- `main.clean_preview` passes the project to the helper and quantizes `when` to `frame_index` before building the cache path. The response shape does not change; no UI change.
- Proof cache: key on `(edit_hash, frame_index, method, model_stamp)`. `edit_hash` is a stable hash of the clean layers, ranges, track, fill_keys, and blur settings. Read the UI’s `v` when present; remove the `edit.updated - 1.0` tolerance. A proof older than the current edit hash is stale and must be regenerated.
- On fill failure, return an error / `Failed` state. Never substitute a blur, a lower-quality fit, or the source frame and call it clean.

Why the full clip span: a short proof span changes keyframe phase and blend boundaries. Even with identical masks, the pixels differ from the export. Using the clip span costs more on the first proof, but it prewarms the render cache and makes the parity claim true. Target: proof time ≤ 2× the baseline proof time for the same frame (`loop-01` §2). If it exceeds that, prewarm after edit save or get Product sign-off before shipping. The harness records the cost against the baseline times.

Proof/render parity gate:

- no dark component > 20 px in a title region;
- no visible glyph and no halo inside the mask;
- outside-mask MAD ≤ the scene 07 control’s proof/render MAD + 1.0 level; p99 ≤ control p99 + 5 levels. This is the production encode floor on the same fixture, not a new invented threshold;
- `PSNR`/`SSIM` recorded as diagnostics, not the only gate.

#### 3.1.1 Blur parity

Blur is an explicit user choice, never a fill fallback.

- Add one shared effect path in `render.py`: decode the filled/source clip at source size, for each active `kind == "blur"` layer crop its `mask.layer_rect` box, apply `PIL.ImageFilter.GaussianBlur(radius=18)`, paste it back, and write an intermediate clip. The proof extracts its frame from that same intermediate clip.
- `render_edit` uses the intermediate clip before the `scale/pad/fps` filter, so the proof and export see the same blur at the same resolution.
- If the shared pass is too slow or cannot be made to match, `render_edit` must refuse an active Blur layer with a clear `RenderError`; the preview shows `Failed`. Product then marks the layer Blur/Off and does not claim it clean. Never silently leave the source text.
- Radius 18 and the layer box are the current preview contract; do not invent a new blur style.

The UI still requests one frame per scene. Loop 2 does not add a multi-proof UI. The acceptance gate samples first, midpoint, last, and largest-mask-area frames through the harness. A single midpoint frame is not accepted as proof of a tracklet. If Product wants the `Proof` chip itself to mean all four frames, that is a later UI decision.

### 3.2 Per-frame tracklet and propagation

#### 3.2.1 Data contract

Add optional fields to a tracklet and to its clean layer. Old reports and old edits keep working because every new field is optional.

```json
{
  "tracklet_id": "trk_913e4081d0",
  "box": {"x": 0.145587, "y": 0.374503, "w": 0.800247, "h": 0.272724},
  "track": [
    {"t": 1.375, "box": {"x": 0.145587, "y": 0.374503, "w": 0.800247, "h": 0.272724}},
    {"t": 1.625, "box": {"x": 0.148000, "y": 0.372000, "w": 0.796000, "h": 0.279000}}
  ],
  "large": true,
  "sample_fps": 4.0,
  "fill_keys": 4.8
}
```

Rules:

- `track` times are absolute source seconds, sorted ascending.
- Boxes are source-normalized, top-left origin, already validated with `normalize_box`.
- One sample per OCR read; deduplicate samples closer than 0.02 s. Cap at 600 samples per tracklet; keep first and last when downsampling.
- `box` stays the union. The UI and old code keep using it.
- `large` is a detection fact, not a UI mode.
- `fill_keys` is `tracklet.fill_plan.keys`. `0` means one fill for the whole line; a missing value means the default plan. The render must not silently ignore a present value.

#### 3.2.2 Detection changes

`detect.build_tracklets` must keep the readings it currently throws away.

- Add `_track_samples(values)` returning `[{"t": start, "box": box}]` from the observations. Use observation `start`, because that is when the OCR frame was read.
- In `_line_tracklets`, attach the samples from that line’s runs to the line tracklet. A repeated line keeps all its samples; its ranges split at the gap.
- Add `_large_text(box)`:
  - `h >= 0.12`, or
  - `h >= 0.09 and w >= 0.50`, or
  - `area >= 0.10`.
  - At 1080 px this is roughly 130 px tall, or 97 px tall and half the frame wide, or 10% of the frame.
  - Scene 01 title, top line, and “Smartest” qualify. Scene 07 “obviously” does not (h 0.109, w 0.431).
- `classify`: after watermark/handle checks, a large block with letters and no corner returns `title` before `_word_pop` and before `screen_frame`. Large display type is a title even when a frame has many lines.
- `_mark_screen_frame`: do not mark a block as screen UI when it is large. Only mark blocks with `h <= 0.08` and `area <= 0.04`. A text-heavy title frame is not a screen recording.
- Persist the scan’s fill plan. `detect.plan_fills` already writes `tracklet["fill_plan"]`; `clean.layers_from_report` must copy `fill_plan.keys` to `layer["fill_keys"]` and keep the plan metadata for diagnostics. This is the baseline P0 #4 fix.
- Keep `TRACKLET_MAX_GAP` for association, but stop using it to merge the parent tracklet’s display range and duration. Add `RANGE_MERGE_GAP = 0.5` s for the parent merge. `_line_tracklets` already emits separate line ranges; the parent union box and parent duration must not treat two appearances 4.5 s apart as one continuous appearance.
- For refinement ranges, bridge gaps inside one line rather than starting a new run on every small box change. `_line_runs` uses `max(1.5 × window, 0.35)` s; `_line_tracklets` merges adjacent runs of the same text with `RANGE_MERGE_GAP`. The 8 fps pass must not turn `Smartest` into six disjoint ranges or `person.` into four.
- `_run_range` for a sampled run:
  - `window = run[0]["end"] - run[0]["start"]`;
  - `start = max(0, run[0]["start"] - window)`;
  - `end = min(duration, run[-1]["end"])`.
  - This covers the first and last sampled frames. It does not add the old half-window on top.
  - Scene-only approximate observations keep their existing 4 s window.
- Add `sample_fps` from the report engine to the tracklet/layer. It is used for margins, not for a new scan.

Expected effect: scene 01’s eight layers keep their union boxes for UI, but each layer carries where its text actually was at each read. The first/last frame is covered by construction, not by a fixed 0.25 s guess.

#### 3.2.3 Frame resolution

`mask.frame_rects` must resolve a layer’s geometry per frame, not once per layer.

```python
def layer_rects_at(layer, at, width, height):
    track = valid_track(layer)          # sorted, normalized, optional
    if not track:
        return layer_rects(layer, width, height)   # old behaviour
    prev = last sample with t <= at
    nxt  = first sample with t >= at
    if prev and nxt and nxt.t - prev.t <= TRACK_HOLD:
        return [union(padded(prev.box), padded(nxt.box))]
    if prev and at - prev.t <= TRACK_HOLD:
        return [padded(prev.box)]
    if nxt and nxt.t - at <= TRACK_HOLD:
        return [padded(nxt.box)]
    return []                            # text is not there
```

- `TRACK_HOLD = 0.6` s. A gap longer than that is absence, not motion.
- Union the two bracketing boxes so a moving or scaling title is covered between reads. The text mask still narrows the hole to actual glyphs.
- `padded()` uses the new capped pad from §3.3, not the current 18%-of-height pad.
- If a layer has a user brush mask, keep `layer_rects` and ignore `track`. A user edit is exact.
- Cache per `(layer id, frame index, width, height)` for the span. The table is built once per `prepare_span`.

`mask.layer_windows` should not add another fixed 0.25 s when `_run_range` already covers the sample window. Use:
- sampled track: `margin = 0.0` (the range already includes the read window);
- scene-only approximate: keep `0.25` s;
- if `sample_fps` is present, never use less than `0.5 / sample_fps`.

#### 3.2.4 Run grouping

Per-frame boxes must not make LaMa run on every frame. Current `_fill_frames_by_runs` stops a run when the exact rect tuple changes. A title moving 20 px/s changes a 2 px signature 10 times a second.

- Add `mask.rect_signature(rects)` that quantizes each edge to 2 px and returns a sorted tuple.
- Add a minimum run length of `ceil(fps / 6)` frames. A run continues until its signature changes **and** the minimum length is met, or the picture moves, or the text leaves.
- The hole is still computed per frame from `TextMasks`. The run’s work area uses the union of the run’s rects.
- The model still runs on the scan’s key count (`fill_plan.keys`) or at most `LAMA_UNPLANNED_KEYS` when there is no plan. A moving large title is capped at 4 model runs a second; other text at 6.
- If the signature never changes, a still line keeps its one fill, as today.

This preserves the existing keyed-fill design and prevents the time blow-up that a naive per-frame box would cause.

#### 3.2.5 Jitter

OCR boxes jitter by a few pixels even when the text is static. Do not let the hole breathe.

- In `_track_samples`, keep a sample only if its center moved more than 2 px or its size changed more than 2% from the previous kept sample.
- Always keep the first and last sample.
- Do not smooth a real large motion away; the 2 px threshold is below a glyph stroke.

### 3.3 Mask expansion and glyph-edge handling

#### 3.3.1 Constants

Current values and Loop 2 values:

| Constant | Current | Loop 2 | Reason |
|---|---:|---:|---|
| `PAD_RATIO` | 0.06 | 0.06 | Base box pad stays. |
| `PAD_MAX_PX` | none | 24 | A 400 px box must not get a 24 px+ pad. |
| `PAD_MIN_PX` | 3 | 3 | Keep. |
| `TEXT_SHADOW_RATIO` | 0.18 | 0.12 | Shadow is not 18% of a display glyph’s height. |
| `TEXT_SHADOW_MIN_PX` | 6 | 4 | Keep close detail. |
| `TEXT_SHADOW_MAX_PX` | none | 20 | Hard cap. |
| `TEXT_GROW_RATIO` | 0.006 × width | 0.004 × width | 4.3 px at 1080, not 6.5 px. |
| `TEXT_GROW_MIN_PX` | 3 | 2 | Antialias needs 2 px. |
| `TEXT_GROW_MAX_PX` | none | 10 | Hard cap for the glyph mask. |
| `TEXT_CONTRAST_LARGE_MAX` | none | 64 | Dense display glyphs must not be suppressed by a high percentile limit. |
| `TEXT_CONTRAST_LARGE_FACTOR` | 2.5 | 1.5 | Lower the large-text contrast floor; 30% percentile no longer dominates. |
| `TEXT_UNCOVERED_MAX_PX` | none | 20 | A single uncovered component above this fails the mask. |
| `TextMasks._measure` grow | `0.18 × h × 0.7` | `min(12, max(self.grow, round(0.04 × h)))` | 12 px cap instead of 37–50 px. |
| `FEATHER_PX` | 3 | 3 normal, 4–6 large | Large fills need a softer edge, not a bigger mask. |

The caps matter more than the ratios. A 295 px title box must not produce a 53 px shadow pad or a 50 px glyph dilation.

#### 3.3.2 Glyph mask algorithm

Replace the box-mean growth with an explicit, glyph-complete, bounded expansion. The baseline’s 1.8 s pill is the test: the old 98.53% coverage and 98% target passed it.

1. Compute `strong`: local contrast against a local mean, majority filter, share between 0.2% and 50% (60% for large text). For large/dense text, lower the contrast limit:
   ```text
   limit = max(TEXT_CONTRAST, min(TEXT_CONTRAST_LARGE_MAX, TEXT_CONTRAST_LARGE_FACTOR × p30))
   ```
   The normal path keeps `max(TEXT_CONTRAST, 2.5 × p30)`. This is the baseline §4.6 fix.
2. Recover solid glyph interiors with hysteresis:
   - `weak = contrast > TEXT_WEAK_CONTRAST`;
   - `seeded = weak & dilate(strong, 2)`;
   - `strong |= seeded`;
   - label the `strong` components and fill enclosed holes (union-find or an equivalent numpy pass; no new runtime dependency). A solid display glyph is a filled component, not just an edge.
3. Add antialias: `ring = dilate(strong, 1) & weak`, then `strong |= ring`.
4. Estimate stroke width from `strong`:
   - erode with a 4-neighbour kernel until empty;
   - `stroke_px = 2 × iterations`, capped at 32.
5. Expand: `grow = clamp(round(0.35 × stroke_px) + 2, 2, 10)` for normal text, `clamp(round(0.35 × stroke_px) + 2, 2, 12)` for large text.
6. Use binary dilation by `grow` px. Every pixel within `grow` of a glyph pixel is in the hole.
7. Union the hole over `TextMasks.WINDOW = 2` frames before and after. Text fading in or out stays covered.
8. Post-hole self-check: `uncovered = text_proxy & ~hole`. If the largest uncovered component is above `TEXT_UNCOVERED_MAX_PX = 20`, expand the hole by 2 px and retry once. If it is still above 20 px, mark the layer `unreliable` and let the proof fail. Do not accept a ratio-only pass.
9. Paste with alpha 1 inside the hole and a 3 px (normal) or 4–6 px (large) feather outside. Pixels with alpha 0 must be bit-identical to the source; `mask.paste` already enforces this.

#### 3.3.3 Failure policy

- `text_in_region` returns `None` when the box is too busy. For a normal subtitle, fill the tight box and mark the layer `unreliable`.
- For a large title, do **not** fill the whole box. Use the tight layer box, mark `unreliable`, and let the proof fail. A visible word is a P1; a dark rectangle is a P1. The app must not choose the dark rectangle silently.
- `TextMasks` carries a `reliable` map. `prepare_span` returns `unreliable: true` when any active layer used a fallback. The proof endpoint treats that as failed. No new UI; the existing `Failed` chip is enough.
- A layer with `kind == "blur"` is explicit user choice. It is not a fill fallback.

### 3.4 Large-title path

Large titles are a separate path because they fail differently from subtitles: bigger holes, bigger masks, bigger downscale, longer on screen.

Detection and layer:

- `detect._large_text` as in §3.2.2; persisted as `large`.
- `classify` returns `title` for a large block before `screen_frame` and `_word_pop`.
- `clean.layers_from_report` copies `large`, `track`, `sample_fps`, and `fill_keys` to the layer. `merge_layers` preserves the fields; a user-edited layer may drop `track`.

Work area:

- `lama_area` for a large rect uses context `clamp(0.30 × h, 48, 96)` px, not `max(96, 0.5 × h)`.
- `lama_areas` merges two areas only when their **text rects** overlap or are within `AREA_MERGE_GAP = 24` px. Context overlap alone no longer merges. This keeps scene 01’s title and the lower line as two runs instead of one near-frame-sized run.
- `without_contained` still drops a smaller text box wholly inside a larger one. The contained text is part of the title, not a second fill.

Fill:

- Large text uses the 768 px padded crop in §3.5. Native 512 tiles are only the measured escalation.
- The scan’s `fill_plan.keys` still controls run frequency. A still large title gets one fill; a moving one gets at most 4 runs/s.
- The large-title mask uses the 60% max share and the 12 px grow cap. If isolation fails, the proof fails; no whole-box fill.

Scene 07 is the control. It is not large by the thresholds above, so it stays on the normal path. If a mask change makes scene 07 worse, revert the mask constants before touching the large path.

### 3.5 Higher-resolution padded crop

Current `lama.fit` caps the long side at 512. For a 970 × 400 title crop that is a 0.53× downscale before the model sees the glyphs.

Primary path: raise the large-text crop to 768, one model run per keyframe.

- Add `LAMA_LARGE_SIDE = 768`; `lama.fit`/`prepare_feed` accept a max side instead of the hard 512.
- The 768 path requires the free-input ONNX model (`LamaFiller.flexible`). If the fallback fixed-512 session is in use, keep 512 and mark the large layer `unreliable`; the tiling escalation is the only native alternative. Do not feed a 768 crop to a fixed-512 session.
- A 970 × 400 title crop becomes 768 × 317 (0.79×). A 1080 × 527 crop becomes 768 × 375 (0.71×). A 20 px stroke stays 14–16 px, not 10 px.
- Large-text keys are capped at 4 per second (`min(fill_plan.keys, 4.0)`). Scene 01’s title plan is 4.8, so it drops to 4.0. A still large title still gets one fill. Target: large-title fill ≤ 2× the current proof time.
- `run_units` uses 768² as 2.25× a 512² run, so the estimate tells the truth.
- If the crop’s long side is at most 768, it is a single run with no downscale.

Escalation only if 768 fails the §3.7 gate: native-resolution tiling at 512. This is not the first move because it multiplies runs and risks the time gate.

- `LAMA_TILE = 512`, `LAMA_OVERLAP = 96` px where the crop allows it.
- Tile origins, greedy and clipped:
  ```text
  step = 512 - 96 = 416
  origins = [0]
  while origins[-1] < length - 512:
      origins.append(min(origins[-1] + step, length - 512))
  ```
- Each tile is a 512 × 512 (or shorter at the frame edge) RGB crop. The hole is the same per-frame text mask restricted to the tile.
- A tile with no mask pixels is not run; the source pixels are copied.
- Fill every tile, then composite with a weight map: weight 1 in the core, cosine ramp to 0 over the overlap, accumulate `result × weight` and `weight`, divide at the end. Pixels outside all tiles keep the source exactly.
- Tiling is behind `DUCK_FILL_TILE=1`, capped at `LAMA_TILE_MAX = 4` tile runs per area and 3 keys/s. It needs measured Product sign-off before it can ship. If a crop needs more than 4 tiles, keep the 768 run and let the gate fail; do not silently add work.
- `estimate_span`, `_planned_units`, `run_units`, and `_CountedFiller` must count whichever path runs, not the old one-run area. Otherwise the render ETA becomes false.

Normal text keeps the existing single-run 512 path. The 768 path is for `large` areas only; tiling is the escalation.

### 3.6 Refinement cadence

Baseline: the full-file pass is 4 fps, an 8 fps request is clamped to 4 fps, and a true 8 fps pass fragments scene 01. Loop 2 does not lower the global cadence; it adds a range-limited refinement pass.

- Keep 4 fps discovery for this 46 s fixture. Never use a global 1 fps pass.
- Only refine when discovery Vision is available and the discovery pass ran. No OCR means `blocked`, not “no text” and not “clean.”
- `pipeline.extract_text_frames`: remove the hard `4.0` clamp; accept `fps` up to 12 and keep `start` / `end` / `max_frames`. Frame times must come from the actual cadence, not the requested one.
- `pipeline.read_text_samples`: pass the refinement fps and range through; return the used fps explicitly. For a scoped window, compute fps from the window span, not the full duration.
- `detect.run_check`: after the 4 fps discovery observations, build a preliminary `build_tracklets` pass to get the refinement windows, then merge the refined observations and call `build_report` once:
  - merge ranges within `0.5 s`;
  - pad each window by one discovery sample;
  - run `8 fps` inside each window only; never the whole file;
  - use a separate `out_dir=job_dir/check/refine` so the discovery frames and motion maps are not deleted;
  - add the first and last frame of each window;
  - merge refined observations into the same tracklet ids by text and geometry; new text gets a new stable id, never forced into a wrong tracklet.
- `duckcore/check.py`: call discovery and refinement as one Check, with a progress stage. Record `discovery_fps`, `refine_fps`, `refined_windows`, and a fragmentation count in the report.
- `detect._line_runs` / `_line_tracklets`: bridge gaps inside one line and do not start a new run on a small box change. Use `max(1.5 × window, 0.35) s` for the run gap and `RANGE_MERGE_GAP` for adjacent runs. If a line produces more than 2 ranges per second or more than 4 ranges for a line shorter than 2 s, merge the adjacent ranges or fall back to the 4 fps samples for that line and record it. Do not ship a fragmented title.
- Time budget: run refinement only inside text ranges. The baseline’s true 8 fps windows took 9.64 s (scene 01) and 6.05 s (scene 07); the total Check must stay within the `≤ 2×` gate or run refinement in the background. Measure on the same fixture.

This closes the baseline’s “8 fps is not available” finding without turning the whole file into an 8 fps scan. Global adaptive policy and long-source cadence tuning stay Loop 3.

### 3.7 Quality gate metrics

The harness computes these on the same fixture and writes them to `docs/teams/clean-quality/loop-02/metrics.json` and `metrics.md` during implementation. Thresholds come from `CLEAN-QUALITY-PLAN.md`; Product approves them before coding.

Let `t` be a sample time. Let `B` be the union of active layer boxes at `t`, dilated by 8 px. Let `H` be the union of actual fill holes at `t`, dilated by 4 px. Let `R` be a ring around `B`, with outer margin `0.5 × B.height`, minus `B`. Let `L` be Rec. 709 luminance.

| Metric | Definition | Target | Fail action |
|---|---|---|---|
| Residual text | OCR on the cleaned frame; count lines with confidence ≥ 0.4 whose box intersects `B` by ≥ 5% | 0, but OCR alone cannot pass | P1, loop fails |
| Largest dark component | largest 4-connected component of `L[B] < 40` that is not present in the source frame at the same location (or grows by > 20 px), in pixels | ≤ 20 px in a title/large region; no uncovered glyph fragment | P1; the baseline’s 242 px pill fails |
| Dark artifact ratio | `mean(L[B] < 16)` | ≤ 2% (secondary to the component gate) | P1 |
| Mask luminance ratio | `mean(L[B]) / mean(L[R])` | ≥ 0.35 | P1 |
| Mask coverage | `abs(G ∩ H) / abs(G)`, where `G` is the source glyph proxy plus the hand annotation | ≥ 99.9% for title/large; ≥ 99% for subtitle; zero uncovered component > 20 px | P1 |
| Color shift outside fill | `SSIM(L outside B)`; mean and p99 ΔE00 on `R` | SSIM ≥ 0.98; mean ΔE ≤ 2; p99 ΔE ≤ 6 | P1 if visible |
| Temporal flicker | `mean(abs(L_t − L_{t−1}))` in `B` vs the same in `R` | ≤ 1.25 × ring + 1 level | P1 |
| Proof/render parity | proof PNG and decoded export frame at the same `frame_index` | no dark component > 20 px, no visible glyph, no halo; outside-mask MAD ≤ scene 07 control MAD + 1.0; p99 ≤ control p99 + 5; record PSNR/SSIM | P0 |
| Blur parity | explicit Blur proof vs export with the same box and radius | same blur; if Blur is not shipped in render, the action is refused or Product marks it Blur/Off | P0 |
| Silent fallback | proof on a forced fill error | error / `Failed`; no blur, no source-frame “clean” | P0 |
| Refinement | 4 fps discovery; 8 fps only inside text ranges | no global 1 fps; scene 01 does not fragment; `refine_fps` recorded | P1 |
| Time | Check, proof, and render stage times | ≤ 2× baseline per stage (loop-01 §2); > 3× needs Product sign-off | P1 if unexplained |

The glyph proxy `G` is not a substitute for a human annotation. The harness must store hand-drawn glyph masks for scene 01 at `0.83`, `1.47`, `1.80`, and `3.50` s, scene 04 at `10.875` and `11.40` s, scene 07 at `25.875` and `26.30` s, and scene 08 at `29.812` s. Those masks are the independent coverage check. If they disagree with `G`, the lower number wins.

Sample times:

- Scene 01: `0.40, 0.83, 1.47, 1.80, 2.50, 3.50` (first text, early proof, mid title, largest-mask frame, late, last).
- Scene 04: `10.50, 10.875, 11.40, 11.875, 13.50` (residual-text regression; “unchallenged”).
- Scene 07: `25.875, 26.00, 26.30` (first frame of control text, mid, last).
- Scene 08: `28.60, 29.812, 31.00` (residual-text regression from user-test-01; verify “was” at `29.812`).

## 4. Exact files and functions

Implementation-phase changes. No change to `static/duck/app.js` or the screen flow.

| File | Function / area | Change |
|---|---|---|
| `duckcore/engine/detect.py` | `build_tracklets` (line ~1056) | Keep per-observation `track` samples; attach `large`; use `RANGE_MERGE_GAP`, not 4.5 s, for the parent range and duration. |
| `duckcore/engine/detect.py` | `_line_tracklets` (~887) | Filter samples per line run; preserve first/last; cap 600. |
| `duckcore/engine/detect.py` | `_run_range` (~870) | Full sample window at the edges; no half-window guess. |
| `duckcore/engine/detect.py` | `_merge_ranges` (~455) | Add a caller-supplied gap; tracklet ranges use 0.5 s. |
| `duckcore/engine/detect.py` | `_mark_screen_frame` (~425) | Exclude large blocks from the screen-UI mark. |
| `duckcore/engine/detect.py` | `classify` (~613) | Large block → `title` before `screen_frame` / `_word_pop`; add `large` helper. |
| `duckcore/engine/detect.py` | `plan_fills` (~1004) | Cap a large tracklet’s `fill_keys` at 4.0/s so the 768 crop stays near the time budget. |
| `duckcore/engine/detect.py` | `run_check` (~2027) | Add the range-limited 8 fps refinement pass and merge refined observations; record `refine_fps` and fragmentation. |
| `duckcore/engine/pipeline.py` | `extract_text_frames` (~851) | Remove the hard 4.0 clamp; accept refinement fps up to 12 with `start` / `end`; fix the stale 2 fps docstring. |
| `duckcore/engine/pipeline.py` | `read_text_samples` (~961) | Pass refinement fps/range through; return the actual cadence. |
| `duckcore/check.py` | `_run` (~94) | Run discovery at 4 fps, then refinement inside text ranges before the report is finalized; report the cadence. |
| `duckcore/clean.py` | `layers_from_report` (~25) | Copy `track`, `large`, `sample_fps`, and `fill_plan.keys` → `fill_keys`; validate samples; keep old reports working. |
| `duckcore/clean.py` | `merge_layers` (~71) | Preserve new fields; drop `track` if the user has an exact brush/box edit. |
| `duckcore/engine/textfill/mask.py` | constants (~18–44) | New caps and `large` thresholds from §3.3.1. |
| `duckcore/engine/textfill/mask.py` | `layer_rect` / `layer_rects` (~49–132) | Capped pad; large path; keep brush masks exact. |
| `duckcore/engine/textfill/mask.py` | `layer_windows`, `frame_rects` (~160–199) | Track-aware per-frame geometry; no double time margin. |
| `duckcore/engine/textfill/mask.py` | `lama_area`, `lama_areas` (~214–270) | Large context; merge by text gap, not context overlap. |
| `duckcore/engine/textfill/mask.py` | `text_in_region` (~384) | Dense-glyph contrast cap; hysteresis component recovery; bounded stroke/antialias growth; large `max_share`; reliability result. |
| `duckcore/engine/textfill/mask.py` | `TextMasks` (~416) | Per-frame track rects; grow cap; `reliable` map; window union; uncovered-component check. |
| `duckcore/engine/textfill/mask.py` | `frame_keys` (~135) | Read the persisted `fill_keys` and keep the scan plan; do not fall back when a plan exists. |
| `duckcore/engine/textfill/mask.py` | `feather` (~329) | Optional radius; large text 4–6 px. |
| `duckcore/engine/textfill/lama.py` | `fit`, `prepare_feed`, `run_units` (~149–196) | Accept a max side; 768 primary; 512 tiles only in the escalation. |
| `duckcore/engine/textfill/lama.py` | `LamaFiller.fill` (~226) | Use 768 only when `flexible`; optional tiled fill with 1:1 tiles and weight composite fallback. |
| `duckcore/engine/textfill/__init__.py` | `VERSION` / `LAMA_RUN_RULE` (~41, ~61) | `VERSION = 5`; `LAMA_RUN_RULE = 4`; invalidate old span clips. |
| `duckcore/engine/textfill/__init__.py` | `span_key` (~428) | Include `track`, `large`, and `sample_fps`. |
| `duckcore/engine/textfill/__init__.py` | `prepare_span` (~1284) | Track-aware rect table; large/tile filler; return `unreliable`; same cache. |
| `duckcore/engine/textfill/__init__.py` | `_fill_frames_by_runs` (~876) | Minimum run length; signature changes; union holes; no per-frame model call. |
| `duckcore/engine/textfill/__init__.py` | `lama_plan`, `_planned_units`, `estimate_span` (~259–329, ~639) | Count 768/tiled runs; cap large-text keys at 4/s; keep key plan. |
| `duckcore/engine/textfill/__init__.py` | `fill_frame` (~1229) | Keep for compatibility; add `tight_rects`/track support; proof no longer uses it. |
| `duckcore/render.py` | `render_edit` (~64), `_fill_layers` (~55) | Extract the shared `scale/pad/fps` filter and `frame_index`; add `render_frame`; apply explicit blur layers through the shared pass. |
| `duckcore/render.py` | new `apply_blur_clip` / `apply_blur_frame` | Same box and Gaussian radius 18 for proof and export; no silent blur fallback. |
| `duckcore/preview.py` | `render_clean_preview` (~42) | Delegate to `render.render_frame`; remove the independent per-layer fill loop and `_pixel_box`. |
| `duckcore/main.py` | `clean_preview` (~503) | Pass the project; use `frame_index`; key the cache on the edit hash and `v`; remove the `-1.0` tolerance. |
| `tests/test_duckcore.py` | `_write_fake_check` (~103) | Add a `track`/`large`/`fill_keys` fixture and assert the layer carries them. |
| `tests/test_clean_quality.py` | new | Unit and integration tests from §6.1–6.2. |
| `scripts/clean-quality-eval.py` | new | Same-fixture evaluator from §6.3. |

Also fix the stale “2 fps” comments in `pipeline.extract_text_frames`, `detect.py`, and `textfill/mask.py`; they are documentation only and must not change behaviour.

No frontend change is required. The existing proof URL, `Failed` chip, and Clean/Preview flow stay.

## 5. Cache, versioning, and compatibility

- `textfill.VERSION` 4 → 5. `LAMA_RUN_RULE` 3 → 4. Old filled clips and saved fills are not reused for a changed run rule.
- `span_key` adds `track`, `large`, `sample_fps`, and `fill_keys`; two edits with the same union box but different tracks or key plans must not share a clip.
- Preview cache key: `sha1(edit_hash + frame_index + method + model_stamp)`. `edit_hash` covers clean layers, ranges, track, `fill_keys`, and blur settings. Read `v` when present. Remove `edit.updated - 1.0`; a proof older than the current edit hash is stale.
- Blur intermediate clip key: `sha1(edit_hash + filled_clip_key + blur_boxes + radius)`; cached beside the filled clip. Proof and export must use the same intermediate file when the key matches.
- New fields are optional and additive. Old `check.json` files load; old edits render with the old static box and default key plan.
- No database migration. No new project state. No new UI mode.
- If a layer has no `track`, it behaves exactly as today. This is the compatibility and rollback path.

## 6. Test harness

Only the plan exists now. The implementation adds the tests and the script below.

### 6.1 Unit tests (`tests/test_clean_quality.py`)

Use synthetic frames and a deterministic fake filler. No model file and no fixture video needed.

1. `test_tracklet_keeps_samples` — three observations with moving boxes produce `track` length 3, sorted, normalized; `box` stays the union.
2. `test_distant_same_text_keeps_separate_ranges_and_track` — observations at 0 s and 10 s with the same words produce two line ranges and a `track` with the two appearances separated, not one continuous display range.
3. `test_range_covers_first_and_last_frame` — a 4 fps sample at `t` is active at `t` and `t + 0.25 - ε`, not at `t + 0.30`.
4. `test_frame_rects_follow_track` — at `0.1 s` the rect is the first sample’s padded box; at `1.0 s` it is the union of the bracketing boxes; at `2.0 s` outside the hold it is empty.
5. `test_static_box_still_works` — no `track` returns the old `layer_rects` result.
6. `test_pad_is_capped` — a 400 px box gets `PAD_MAX_PX`, not `0.18 × 400`.
7. `test_glyph_grow_is_capped` — a 400 px box with 8 px strokes gets ≤ 12 px grow, not 50 px.
8. `test_antialias_is_covered` — a feathered synthetic glyph; every pixel with contrast above the weak threshold is inside the hole.
9. `test_large_title_not_whole_box` — a large title on a sky background; hole share of the layer box is ≤ 35%, and the sky outside glyphs is untouched.
10. `test_areas_not_merged_by_context_only` — two text lines 56 px apart with 90 px context return two `lama_areas`.
11. `test_feather_leaves_outside_untouched` — `mask.paste` output equals the source exactly where alpha is 0.
12. `test_large_crop_is_768_first` — a 970 × 400 area runs once at a 768 px long side, not at 512, and the run-unit estimate is 2.25×.
13. `test_tiled_fill_is_one_to_one` — with `DUCK_FILL_TILE=1`, a 970 × 400 area produces at most 4 tiles, every tile ≤ 512 px on its long side, the mask is fully filled, and a gradient background has no seam above 1 level.
14. `test_proof_uses_render_frame` — monkeypatch `render.render_frame`; `preview.render_clean_preview` calls it and does not call `textfill.fill_frame`.
15. `test_no_blur_fallback` — a filler that raises `FillError` makes the proof fail; no blur is written and the layer kind stays `fill`.
16. `test_cache_key_changes_with_track` — two layers with the same box but different `track` produce different `span_key`s.
17. `test_fill_keys_persisted` — a tracklet with `fill_plan.keys = 4.8` produces a layer with `fill_keys = 4.8`; a missing plan stays missing.
18. `test_dense_glyph_interior_covered` — a solid 21 × 12 glyph pill inside a dark display word is fully inside the hole; the baseline pill case has no uncovered component above 20 px.
19. `test_uncovered_component_fails` — an uncovered synthetic component above 20 px marks the layer `unreliable` and fails the proof.
20. `test_proof_frame_index_matches_render` — proof and export use the same `frame_index` for the same `when`, clip start, and fps.
21. `test_cache_key_uses_v_and_edit_hash` — a one-second-old but different-edit proof is not served; `v` and the edit hash change the key.
22. `test_blur_parity` — an explicit Blur layer has the same box and Gaussian radius in the proof and export; a missing blur path is a failure, not a silent source frame.
23. `test_refine_fps_not_clamped` — `extract_text_frames(fps=8)` returns the 8 fps frame count, not the 4 fps count.
24. `test_refinement_range_only_and_no_fragmentation` — refinement runs only inside a text window; scene 01’s synthetic `Smartest` line is not split into six ranges.

### 6.2 Integration tests with a fake filler

- Build a 1 s, 24 fps synthetic clip with a large moving title, a small static subtitle, a solid glyph interior, and an explicit Blur layer.
- Run `prepare_span` through the real mask code with a fake filler that returns the local median color.
- Assert: the large title hole is glyph-shaped, the solid interior is covered, the subtitle hole is small, the first and last frames are filled, and no frame uses a whole-box hole.
- Assert proof/render parity: `preview` path and `render.render_frame` produce the same array for the same `frame_index` when the fake filler is deterministic.
- Assert Blur: proof and export apply the same box and radius; no silent source frame.
- Assert `fill_keys`: the fake filler sees the scan’s key cadence, not the default 3/s.

### 6.3 UAT on the same fixture

Script: `scripts/clean-quality-eval.py` (implementation phase).

```text
python3 scripts/clean-quality-eval.py \
  --project prj_9542d62ce105 \
  --edit ed_093ff8d3935c \
  --torture-scene 0 --control-scene 6 --quality-scenes 0,3,6,7 \
  --times 0.40,0.83,1.47,1.80,2.50,3.50 \
  --control-times 25.875,26.00,26.30 \
  --regression-times 10.50,10.875,11.40,11.875,13.50,28.60,29.812,31.00 \
  --proof-frames first,mid,last,largest-mask \
  --out docs/teams/clean-quality/loop-02
```

The script:

1. Asserts the project metadata: 45.833 s, 1080 × 1080, 24 fps, same source fingerprint.
2. Generates proof frames at first, midpoint, last, and largest-mask frame through the API/`preview` path.
3. Renders a short segment containing each proof time through `render_edit`; extracts the same `frame_index`, not just the same timestamp.
4. Checks the proof cache: a changed `v` / edit hash never serves the old frame; no `-1.0` tolerance.
5. Computes every metric in §3.7, including the largest dark component, uncovered components, proof/render parity, and Blur parity.
6. Runs the refinement pass and records `refine_fps`, `refined_windows`, and fragmentation for scenes 01 and 07.
7. Writes `before_*.png`, `proof_*.png`, `render_*.png`, `diff_*.png`, `metrics.json`, `metrics.md`.
8. Exits non-zero if any P0/P1 gate fails. It never writes a pass when OCR or the model is unavailable; it writes `blocked`.

UAT steps:

1. Open the same project and edit; do not re-check.
2. Scene 01: compare Before / proof / render at `0.83`, `1.47`, `1.80`, `3.50`; include the largest-mask frame.
3. Scene 04 and scene 08: check the residual “unchallenged” and “was” areas at the times above.
4. Scene 07: compare Before / proof / render at `25.875` and `26.30`.
5. Confirm no black blob, no visible glyph, no halo, no uncovered dark component above 20 px, no unnatural fill at full size.
6. Confirm the proof and the exported frame are the same `frame_index` and look the same.
7. Toggle Blur on one layer: proof and export must show the same blur, or the render must refuse Blur explicitly. No silent source frame.
8. Confirm a forced fill error shows `Failed`, not a blur and not a false `Clean`.
9. Confirm the Check record shows 4 fps discovery and 8 fps refinement inside text ranges; scene 01 did not fragment.
10. Record Check time, proof time, and render time.

Product gate: scene 01 accepted at full size; scenes 04 and 08 have no residual text; scene 07 no worse than baseline; no P1 on the fixture; proof/render parity accepted; Blur parity accepted or Blur explicitly marked off; refinement does not fragment scene 01. This is the baseline §9 gate, not a new one.

## 7. Risks and rollback

| Risk | Likelihood | Impact | Mitigation | Rollback |
|---|---|---|---|---|
| Proof becomes slow because it prepares the real clip span | High | P1 UX | Shared render cache; prewarm after edit save; measure; Product sign-off if > 3× | `DUCK_PROOF_RENDER=0` returns the old preview path |
| Tiling escalation shows seams or ghosting | Low | P1 | Tiles off by default; 96 px overlap; cosine weights; synthetic seam test; visual gate | Keep `DUCK_FILL_TILE=0` and the one 768 px run; if that fails, old 512 path |
| Per-frame track causes too many model runs | Medium | P1 time | 2 px signature, minimum run length, 6 keys/s cap, scan plan | `DUCK_FILL_TRACK=0` uses the static union box |
| Mask expansion removes real background or a face | Medium | P1 | Caps at 12 px; stroke-based growth; Product review; no full-box large fallback | Revert mask constants first |
| Track jitter makes the hole breathe | Medium | P1 flicker | 2 px hysteresis; temporal window; still-line single fill | Keep `track` for geometry but disable hole growth changes |
| Range split changes layer count and user edits | Medium | P2 | Stable tracklet ids; `merge_layers` preserves kind/enabled; test scene count | Revert `RANGE_MERGE_GAP` to 4.5 s for the parent display only |
| Large-title isolation fails on a busy frame | Medium | P1 | Mark `unreliable`; proof `Failed`; no whole-box fill | Product can set the layer to Blur/Off explicitly; no silent fallback |
| Scene 07 regresses | Low | P1 | Normal path unchanged; control test at 3 times | Revert mask/large changes; keep proof parity |
| Old cached fills are reused with new masks | Low | P0 | `VERSION` and `LAMA_RUN_RULE` bump; `span_key` includes track and fill_keys | Delete `projects/*/fill` and re-render |
| Proof cache serves a stale frame | Low | P0 | Edit hash + `v`; remove `-1.0` tolerance; test | Delete `projects/*/previews` |
| 8 fps refinement fragments scene 01 again | High | P1 | Per-sample boxes; gap bridge; range merge; fallback to 4 fps for that line | `DUCK_REFINE_FPS=4` disables refinement |
| Blur parity pass is slow or shows a different radius | Medium | P1 | One shared clip pass; same box/radius; synthetic test | Render refuses Blur explicitly; Product marks it Blur/Off |
| 99.9% title coverage is hard on stylised type | Medium | P1 | Dense-glyph hysteresis; component fill; mark `unreliable`; no fake pass | Keep the layer on Fill with a failed proof; Product chooses Blur/Off |
| M1 8 GB memory pressure from the 768 crop or tiles | Medium | P1 | One fill at a time; `release_fillers()`; max 4 tiles only in the escalation | Use one 512 run; mark `unreliable` if quality fails |

Rollback order:

1. Disable refinement (`DUCK_REFINE_FPS=4`); keep discovery and proof parity.
2. Disable tiling/large path (`DUCK_FILL_TILE=0`, `DUCK_FILL_LARGE=0`); keep track and proof parity.
3. Disable track (`DUCK_FILL_TRACK=0`); keep proof parity.
4. Revert mask constants to current values; keep proof parity.
5. Revert Blur only if it cannot match; then make the render refuse Blur rather than silently leaving text.
6. Revert `preview.py`/`render_frame` last. Proof parity is the P0 fix; do not give it up to save a cosmetic change.

No database rollback. No migration. Old clips are ignored by the version bump; the source and edits are untouched.

## 8. Out of scope

- Loop 3 global adaptive discovery policy, long-source cadence tuning, and the 1/2/4/8/12 fps benchmark sweep. Loop 2 only adds the bounded range-limited 8 fps refinement.
- Loop 4 reject/retry path, feather/blend polish beyond the bounded mask feather, and temporal smoothing beyond the existing carry.
- Loop 5 release proof, 20-clip run, App Store screenshots.
- Any new screen, mode, button, or copy.
- Any silent blur or source-frame fallback.
- Captions, queue, Fine trim, and the other user-test P1s.

If scene 01 still shows residual text outside the detected tracklets, that is a Loop 3 recall issue, not a Loop 2 pass. Record it and do not claim the scene is fixed.

## 9. Product gate and exit checklist

Product gate, adopted from baseline §9:

1. The scene 01 proof is an actual render frame from the same all-fill-layer pipeline, at first, midpoint, last, and largest-mask frames.
2. Scene 01 at `0.83`, `1.8`, and `3.6 s` shows no black blob, no visible glyph, no smeared sky/mountain, and no halo at full size.
3. The render at `1.8 s` has no dark component above 20 px and no residual glyph fragment.
4. Proof and render at the same `frame_index` agree structurally inside the mask; outside-mask MAD is at production encode noise.
5. Coverage is ≥99.9% for title/large text and ≥99% for subtitles, with zero uncovered component above 20 px.
6. Residual OCR is zero, backed by the dark-component and coverage gates; “OCR 0” alone does not pass.
7. Scene 07 remains the clean control: no dark component, no residual text, no visible smudge beyond the current acceptable level.
8. No P1 remains on the fixture; the scene 01 proof blob and the 1.8 s render pill are both closed.
9. Scan stays at 4 fps discovery or a documented adaptive equivalent, never global 1 fps; the 8 fps range refinement exists and does not fragment scene 01.
10. Blur proof and export match, or Product marks Blur/Off and does not claim it clean. Fill has no silent fallback.
11. Loop 1 is accepted: the P0 is owned, the harness produces the same metrics, and Product accepts the pass/fail language.

Exit checklist:

- [ ] `docs/teams/clean-quality/loop-01.md` read; baseline accepted as the before state.
- [ ] Product accepts the §3.7 thresholds and the baseline §9 product gate.
- [ ] Proof path is `render.render_frame`; same clip span, `frame_index`, masks, key plan, and carry state as the export. No per-layer `fill_frame` proof.
- [ ] `fill_keys` is persisted and visible in the layer; the render uses the scan plan, not the default 3/s.
- [ ] Scene 01 has per-sample boxes and exact first/last range edges.
- [ ] Glyph mask is glyph-complete: 99.9% title / 99% subtitle coverage, zero uncovered component > 20 px, largest dark component ≤ 20 px. The baseline 242 px pill is gone.
- [ ] Large title is `large`, uses the 768 px crop, and is not merged by context. Tiling is off unless the measured escalation is signed off.
- [ ] Proof cache uses the edit hash and `v`; no `-1.0` tolerance.
- [ ] Blur proof and export match with the same box and radius, or Blur is explicitly refused and Product marks it Blur/Off.
- [ ] Refinement records 4 fps discovery + 8 fps range passes; no global 1 fps; scene 01 does not fragment.
- [ ] Scenes 01, 04, 07, and 08 pass the harness, including residual “unchallenged” and “was”.
- [ ] Unit tests pass.
- [ ] UAT harness writes same-video evidence and exits 0.
- [ ] No P0/P1 on the fixture; no silent blur fallback.
- [ ] Product signs the scene 01, 04, 07, and 08 proofs at full size.

## 10. Handoff to Loop 3

Loop 3 starts only after this checklist passes. It owns global adaptive discovery, long-source cadence, and the 1/2/4/8/12 fps sweep. It must not use Loop 2’s mask constants to hide missed text. The Loop 2 report must state the measured residual text outside detected tracklets, so Loop 3 knows what recall work remains.
