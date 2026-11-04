# Clean and AI fill: revision plan

Date: 2026-11-04. Code reviewed: `studio` at `e274b45`.

Status: revision 5. M0, R0 and R1 built; R2 to R5 not started.

**Rule for this work:** audit from code and tests. Do not open the founder's projects to see what they did unless they say so. Layers found in a project may just be the founder testing, so they are not bug reports.

The automated suite is green (2055 passed, 11 skipped), yet the problems below are real. The tests use fake fillers and mocked routes, so they prove the plumbing and say nothing about the picture. That gap is itself a finding (R4).

## 1. Evidence

**Real fills inspected:** job `8eab6fa1c6a9` in `~/vibecut-lanes/studio`, seven STTN clips compared with the source frame by frame.

**Live editor inspected:** job `6bfd353dcc03` on 8795 at 1280x720, read-only.

### What works

- Text is gone in every sampled frame of the seven clips.
- Frames outside the band look unchanged.
- No colour shift: raw Y, U and V stay within about 1 level of the source on six of the seven clips. The seventh aligned too poorly to judge. This footage has low saturation, so a saturated clip should be checked too.
- Cancel, cache keys and model release from `be2f909` and `7ce8dcf` read correctly in the code. The founder has not exercised them on a long render as far as I can tell.

### Problems, most severe first

| # | Finding | Proof | Severity |
|---|---|---|---|
| 1 | **A large drawn box can streak the whole story.** The Draw box tool makes a `delogo` layer with no time range and no size limit, and `delogo` smears large areas. | `manualLayer` in `clean.js`. A `delogo` box over 43% of the frame returned a streaked picture from the frame route. | High |
| 2 | **AI fill damages things that are not text.** The whole rectangle is repainted for the whole range, so a cat bed's edge, feet and floor grain smear. | Side-by-side strips. Roughly 44 to 77% of changed pixels sit outside the text on six clips. Rough estimate: glyphs taken as luma above 205, dilated 3 px, in a fixed band. | High |
| 3 | **Render cost is hidden and very large.** 4.6 s per frame on the real run, and it multiplies by strip count. | Layers of `6bfd353dcc03`: 621 frames become 1,589 strip-frames, about 122 minutes if the rate holds per strip. Nothing warns first. The only hint is "It can take minutes per beat." | High |
| 4 | **Top and bottom text multiply that cost.** `sttn_strips` covers the union of all rects, including the empty space between them. | Text at top and bottom of a 1280 frame gives 8 strips. Real beats reach 6. | High |
| 5 | **One brush click shrinks the whole fill to a dot.** Any mask replaces the box entirely. The panel says the box "stays as a fallback and as the layer bounds", which is untrue. | `layer_rects`: a 1-point mask gives a 25x25 rect against the 638x68 box. Real edits on `8eab6fa1c6a9` carry a single-point mask. | High |
| 6 | **The row's brush button adds layers silently.** `startPaintRow` reuses a layer only when it already has points. Each click that paints nothing adds another full-box STTN layer. | Read from `startPaintRow`. Not reproduced by clicking. | High |
| 7 | **The server is not running as the lane.** No `VIBECUT_DATA` or `VIBECUT_EDITION`, so it reads the worktree's `data/` rather than `~/vibecut-lanes/studio`. | Process environment on 8795: 4 jobs in `data/`, 2 in the lane folder. The real fill clips are in the lane folder and not visible in the app. | High |
| 8 | **The preview does not show what the render does.** Default engine is STTN, but Before/After always runs LaMa. STTN has no preview at all. | `fill_preview` refuses anything but `lama`. | Medium |
| 9 | **The preview route has no guard.** It takes no fill lock and never frees LaMa, so it can load a second model during a render. Cancel only stops the browser request. | `fill_preview` and `fill_frame`. | Medium |
| 10 | **Beat selection ignores the time margin.** `_active_window` uses plain ranges while `layer_windows` adds 1 s. Text just outside a detected range is left in on a neighbouring beat. The comment says ranges are known to about 2 s, but the margin is 1 s. | Code. Not yet measured on a real clip. | Medium |
| 11 | **Output-space masks drift.** Points are mapped through each beat's crop when compiled. A layer crossing beats, or a reframe change at the same aspect, moves the mask with no warning. Only an aspect change is caught. | `source_mask` in `_fill_plan`. | Medium |
| 12 | **"Ready" can be false.** Status checks the model file only. `torch` and `onnxruntime` are in no requirements file, so a fresh install says ready and fails at render. | `/api/fill/status`, `requirements*.txt`. | Medium |
| 13 | **The layer list is unreadable at volume.** 30 rows, 11 with the same name, and 16 outside the trimmed story. | Live: the layers panel scrolls 1339 px inside 465 px. | Medium |
| 14 | **Clean's own lane starts off-screen.** The timeline shows 75 px at 1280x720. The Clean lane sits at y 681, against a visible bottom of 677. | Live measurements. | Medium |
| 15 | **Text is too small.** 159 visible text nodes under 11 px, going down to 8 px. | Live measurements. | Medium |
| 16 | **Brush strokes are stamps.** Points are not joined, and each becomes a square, so fast drags leave gaps. | `layer_rects`, `preview.js`. | Low |
| 17 | **Copy and docs contradict the product.** `cleanup.py` says there is "no inpainting" or temporal reconstruction, and `edits.py` says inpainting is "not supported" while Studio ships it. | Source text. | Low |
| 18 | **Killed renders leave `.part` files.** One 1.1 MB file remains from a render that stopped at 20:04. | `jobs/8eab6fa1c6a9/fill`. | Low |
| 19 | **Rescanning creates duplicate layers.** The same text in the same area gets a second layer when its id changes and its box shifts slightly. | Plain-data run of `build_tracklets` and `merge_auto_clean_layers`: 1 layer added for text already covered. | High |
| 20 | **Rescanning can skip new text.** Ids are just a counter (`trk_0001`), so the same id can name different text after a rescan. The new text is refused as "already has a Clean layer" and stays on screen. | Same run: 0 layers added for different text. | High |
| 21 | **Returning text becomes a second row.** The same text in the same area, more than 4.5 s after it last appeared, becomes a separate tracklet. | Same run: 2 tracklets for one text at 10 s and 30 s. | Medium |

## 2. Plan

Each phase ends with a founder test on real video. Later phases do not start until it passes.

### M0: move the jobs into the lane folder

Founder decision: move the jobs. This comes first, because every later founder test should run on the lane's own data. It is not a code change, but it does stop the server, so it waits for the founder's go-ahead like the rest of this plan.

`scripts/serve.sh` will not do this by itself: its one-time move runs only when the lane folder is empty, and it is not.

| Item in `data/` | Lane folder today | Plan |
|---|---|---|
| `jobs/`: 4 jobs (`0b5a6be91e3e`, `2f83536b1e22`, `63d5d6763667`, `6bfd353dcc03`), 127 MB | 2 other jobs, no clash | Copy across |
| `sources/`: 4 entries | `86188847d713e1af` exists in both | Copy 3, then read the source store code and merge the fourth. `gc_sources` deletes entries it thinks are unused, so this needs care |
| `story_queues/`: 1 file | 4 other files | Copy across |
| `cache/` | Separate cache | Do not copy. It rebuilds |
| `admin/`: settings database, newer than the lane's | Own database | Do not merge blindly. Compare what differs without printing keys, and report it to the founder first |

Steps, in this order:

1. Founder approves. Stop the server on 8795, by process id only.
2. Copy, do not move. `data/` stays untouched as the backup.
3. Start with `scripts/serve.sh`. The server now uses `~/vibecut-lanes/studio`, with `VIBECUT_EDITION=all` and `VIBECUT_FEATURES=voice_room`.
4. Check all 6 jobs open with no "Original file missing". `_relocate_source` should repair the old absolute paths; this is the first real test of it for these 4 jobs.
5. The founder confirms the videos and renders are there. Only then ask about deleting `data/`.

Known result: the same video will appear twice in Recent videos, `6bfd353dcc03` and `8eab6fa1c6a9`, because it was imported once into each folder. Both are kept.

**M0 log (2026-11-04), waiting on step 5, the founder's check:**

- Stopped PID 42835. Copied 4 jobs, 3 source entries and 1 queue to the lane folder. `diff -rq` shows only `job.json` differs, where `source.path` now points at the lane copy. Each copied source is hard-linked to the lane's source store. `data/` is untouched.
- Admin not merged: the two databases differ only in `pipeline_events` (4 rows against 2), which is a log. No users, sessions, settings or secrets files differ.
- First start blocked: OpenCode session `ses_e7cbc45efffetnXc3Kv7TCcOod` started its own server on 8795 (PID 61657) with no `VIBECUT_DATA`, so `scripts/serve.sh` could not bind. This is the likely source of finding 7. The founder stopped it.
- Compared again after it stopped: jobs unchanged apart from `source.path`. The queue differed only in its `updated` time, which a server rewrites at startup.
- Server now runs from `scripts/serve.sh` in the founder's Terminal panel (PID 62803), with `VIBECUT_DATA=~/vibecut-lanes/studio`.
- Checked through the API: all 6 jobs return with `source_missing` false, and clip sets and thumbnails load. On disk, all 6 `source.path` values are in the lane folder and the files exist. Fill status: STTN and LaMa ready. The server has no files open in `data/`.
- Not checked: playing or rendering in the app. `data/` stays until the founder confirms.

### R0: stop the damage

Small, safe fixes.

- **Draw box (1):** founder decision: Draw box is a Clean tool, and each box has its own setting. One box can be AI fill and the next Blur.
  - Draw a box, and a small `AI fill | Blur` switch appears on it. The same switch is in its layer row. Changing it affects that box only.
  - A new box starts with the last choice used. The first ever is AI fill if an engine is ready, else Blur. AI fill is greyed out with the reason when no engine is ready.
  - Each box on the picture shows which method it uses. This matters because Blur shows on the frame straight away, while AI fill appears only in Before/After and the render.
  - The two methods already work together on one beat: fill runs first, then Blur on top, per the compile code. Add a test on a beat with both.
  - The range starts at the current beat and can be changed, so a box no longer applies to the whole story without anyone choosing that.
  - Saved `delogo` boxes over about 10% of the frame get a warning in the panel. Saved layers are not rewritten.
  - Engine limit: STTN and LaMa boxes on one beat still run as one engine. Show the existing `fill_method_mixed` warning in the panel. Running both engines in one beat is not in this plan.
- **Clean has two methods:** founder decision: Clean is AI fill and Blur, everywhere, for drawn boxes and scan results alike. Cover is removed: someone who wants a cover adds an effect.
  - Remove Cover, `Remove (interpolate)`, Mask, Mosaic and Keep out of crop from the Clean choices, plus the timeline's Mosaic button. Only Cover was named explicitly; the rest follow from "AI fill or Blur". This removes finding 1 at its source.
  - Scan results default to AI fill when ready, else Blur, instead of `delogo`. The auto-clean route stops accepting `cover`.
  - Remove the automatic "Mid-frame caption cover" under Blur. Its job was to stop old text showing through, so Blur on mid-frame text may now leave it readable. Say so on that row and suggest AI fill.
  - Keep the old kinds in the Edit format, so saved projects still open and render the same, showing their old name with a switch to AI fill or Blur.
  - `cleanup.py` is shared with Classic, so make these changes in Studio's route and panel. Keep Classic's tests passing.
  - No rectangle effect will be added (founder decision). Effects stay arrow, circle, underline, progress bar and sticker, and Text with a solid background is the closest thing to a cover.
- **Layers stay attached to the video:** founder decision: Clean layers stick to and scale with the video. Zooming or expanding the video scales them. Moving the crop does not cut or change a layer; the part outside the crop is simply hidden.
  - Already true for boxes per the code: they are stored as positions on the original video, drawn clipped to the frame, and applied before the crop. Add tests to hold this.
  - Fix brush marks, which are saved on the cropped picture (finding 11). Save them on the original video, and drop the rule that discards a mask on an aspect change.
  - Convert a saved mask the next time it is opened, and keep rendering old ones as they are until then.
  - A layer fully hidden by the crop stays in Layers, marked "Hidden by crop", and can still be selected there.
  - AI fill skips a beat where the layer is fully hidden, because that work would not be seen.
  - Check that boxes follow Motion zoom on the preview. The code does not show this either way, so test it first.
- **No duplicate scan layers (19, 20, 21):** founder rule: overlapping layers are fine, but the same text in the same area must be one layer.
  - Same means: the areas match, and the text matches or the times overlap. Different text in the same area at different times stays separate.
  - Same text returning later becomes one layer with more time ranges, not a second layer or row.
  - Ids come from the text and area, not a counter, so a rescan or `Check this scene` gives the same text the same id.
  - Adding scan results compares by that identity, so a rescan adds nothing already covered and never skips new text.
  - Drawn boxes are never merged. Overlapping or repeated drawn boxes are allowed.
- **Masks (5, 16):** a mask only narrows the box. Clip it to the box, and treat a mask under a minimum area as a mistake: keep the box and say so. Join points along each stroke and rasterize circles. Correct the panel text.
- **Brush button (6):** reuse the row's unpainted layer, and remove it if the paint is cancelled with nothing drawn.
- **Status (12):** ready means the model file and its package are both present. Declare both packages in `requirements-optional.txt`.
- **Preview route (9):** take the fill lock, answer 409 while a fill runs, and release models afterwards.
- **Copy (17):** correct `cleanup.py`, `LIMITATIONS` and the `edits.py` error message. Keep the watermark refusal exactly as it is.

**Test gate:** on a real clip of the founder's choice:
1. Draw two boxes and set one to AI fill and one to Blur. The render applies each box's own method.
2. Paint a stroke and click the brush twice. No extra layers appear.
3. Move and zoom the crop. Layers stay on the text and hide at the crop edge.
4. Scan twice. The second scan adds no duplicates.

**R0 log (2026-11-04), built, not founder-tested:**

- Clean offers AI fill and Blur only. Scan results default to AI fill when ready, else Blur. The route refuses `cover`. Old kinds still render and show "(old)" with a switch.
- Each box has its own switch, on the box and in its row. New boxes start on the current beat with the last method used.
- Boxes stay on the video. Brush marks now save on the original video, old ones convert when opened, a fully hidden layer is marked "Hidden by crop", and AI fill skips it on that beat.
- Masks join, stay round and stay inside the box. One click or a tiny stroke keeps the whole box.
- Brush button reuses the row's layer. A paint layer with no stroke is removed.
- Scans: tracklet ids come from text and area, returning text is one tracklet, and adding compares text and area. Drawn boxes never merge.
- Ready means model and package. The preview refuses while a render holds the fill lock, and frees the model afterwards.
- **Not done:** boxes on the preview do not follow Motion zoom, because the preview does not show Motion at all. The render does apply it. This goes with R5.

### R1: tight masks and real cost

This is the largest quality gain, and also cuts render time.

- **Text-shaped mask (2):** inside each box, find the text pixels per frame with local contrast, then dilate them to cover outlines and shadow. Paste back only there. If detection is unsure on a frame (coloured text, emoji, low contrast), use the full box for that frame. Keep it pure numpy in `textfill/mask.py`, and include the mask version in `span_key`.
- **Frame gating:** frames with no text are not pasted, and a chunk with no text skips the model. OCR at 0.5 fps cannot do this alone; the per-frame detector can.
- **Strip grouping (3, 4):** cover groups of nearby text instead of the union, so top and bottom text cost 2 strips rather than 8.
- **Time margin (10):** beat selection and `layer_windows` use the same margin. Measure the margin on real clips before changing its size.

The text mask is an untested idea. Build it behind a setting, compare it on the founder's clips, and drop it if it leaves halos.

**Test gate:** the founder compares old and new on the same moment. Pass marks: no smeared objects, no text ghosts.

**R1 log (2026-11-04), built, not run on real video:**

- Scan layers without a brush stroke now narrow to the text on each frame: contrast against the local average, in any colour channel, then grown to cover outlines. Each hole also covers 2 frames either side, so fades are caught and the mask stays steady.
- Frames with no text are left untouched, and a chunk with no text skips the model. A very busy box, or faint structure that may be faint text, fills the whole box instead.
- Drawn boxes and brush strokes are not narrowed, because they mean exactly that area.
- Top and bottom text cost separate strips, not the space between them. A strip with no text in a chunk skips the model.
- Beat selection uses the same 1 s margin as the fill. The margin size is unchanged.
- Setting: `VIBECUT_FILL_TEXT_MASK=off` fills whole boxes as before. On by default. Both are cached separately.
- **Unknown:** thresholds were set from reasoning and in-memory test arrays only. Halos, missed low-contrast text on busy backgrounds and real time saved are all unmeasured.

### R2: honest time and preview

- **Estimate (3):** the server computes strip-frames for the current Edit and shows it beside Render ("about 40 min on this Mac"), per engine. Label LaMa unmeasured until a real reading exists. Update the rate from finished runs on this machine.
- **STTN sample (8):** "Test 1 second" runs the real engine on about 30 frames at the playhead and shows the result in the preview. Until then, label Before/After clearly as a LaMa preview.
- **Progress:** fill takes most of the time but holds only 2 to 45% of the bar. Show frames done and time left.
- **Interrupted work (18):** sweep stale `.part` files at the next fill. Consider saving finished chunks so a 35 minute beat is not lost on Cancel.

**Test gate:** the estimate is within about 30% on a real render.

### R3: a layer list that can be read

- **Grouping (13):** one row per found text, with its time pieces inside. Layers outside the trim fold into one line.
- **Clean lane (14):** when Clean is open, the timeline shows the Clean lane without scrolling. Keep the timeline resizable.
- **Text size (15):** minimum 11 px across Clean and the timeline. Other panels follow in their own deep dives in `ui-revamp-plan.md`.

**Test gate:** the founder finds, selects and removes one subtitle without scrolling the timeline.

### R4: tests that look at the picture

- **Audit script:** `scripts/fill_audit.py` reads a finished clip and its source and reports the share of changes outside text, flicker in the band, leftover text and colour drift. It only reads existing media and generates nothing.
- **Unit tests** for each R0 and R1 fix: one-point mask, repeated brush clicks, draw defaults, strip grouping, and margin parity.
- **Docs:** update `text-fill-test-plan.md`, the `deep-open-items-plan.md` log, and `ui-revamp-plan.md`.

The audit script supports the founder's review and does not replace it. It runs only on clips the founder names.

### R5: all other layers stick to the video

Founder decision: all layers follow the rule, not only Clean. This covers Text, stickers, effects and captions. If the video is zoomed or expanded, the layer scales with it. If the crop moves, the layer is not cut or changed, and whatever falls outside the crop is hidden.

This is the largest change in the plan. R0 does the same for Clean layers, which are nearly there already. R5 is separate because these layers work differently today:

| | Clean layers | Text, stickers, effects, captions |
|---|---|---|
| Position saved on | The original video | The output picture, with an anchor and box |
| Applied | Before the crop | Burned onto the finished video, after crop and motion |
| Crop moves | Stays on the video | Stays on the screen |

**Spike first.** Choose between two ways of building it, on one Text layer, before changing anything else:

- **A: map the position to each beat.** Keep drawing the layer at final size, moved and scaled to match each beat's crop. Text stays sharp, and the output picture clips it naturally. Motion zoom has to be copied onto the layer by matching the same moves.
- **B: draw the layer onto the video before the crop.** Crop, zoom and motion then apply on their own, so it behaves exactly as the founder described. But text takes on the source's sharpness, so it goes soft on a low-resolution or zoomed source, and every text edit re-cuts its beats.

Recommendation: A, because sharp text matters most, unless matching motion proves unreliable in the spike.

**Build:**

- Add an optional video-based position to `graphics` and captions, with size relative to the video. Layers without it keep working as they do now, which keeps Classic unchanged, since it shares `edits.py` and `compose_render.py`.
- In the compile, split a layer that crosses beats into one piece per beat with that beat's position and size. `_burn_layers` already places entries by time.
- Update the preview too: `overlay.js`, `preview.js` and the frame route must all show the same result, and dragging converts through `frameToBox`.
- `safe_zone` stops moving these layers and becomes a guide only, because moving them would break "sticks to the video".
- A layer partly or fully outside the crop stays in Layers, marked "Hidden by crop".
- Convert a saved layer when it is opened, using the crop at its start time, so it looks the same on first open. Do not rewrite saved files until the founder edits that Edit.

**Consequences of this decision, shown as warnings rather than prevented:**

1. **Layers jump at some scene cuts.** With auto reframe, each scene can have its own crop, and text crossing scenes follows the video at each cut. This shows only when the source is cropped, for example 16:9 to 9:16. A source already in the output shape has no jump.
2. **Captions can be cut off.** A zoomed caption can overflow the crop edge, and a moved crop can hide all of it, so captions may go unreadable. The layer row warns; nothing moves it back automatically.
3. **Text size follows zoom.** Zoom 2x makes text twice as big on screen.
4. **Time is unchanged.** Layers keep their current start and end times. This rule is about position and size only.

**Test gate:** on a clip of the founder's choice, with Text, a sticker, an effect and captions on it:

1. Zoom, and all of them scale with the video.
2. Move the crop, and they move with the video and hide at the edge.
3. The render matches the preview.
4. A Classic export looks the same as before.

## 3. Decisions

### Made

- **Data folder:** move the jobs (M0).
- **Draw box:** each box has its own AI fill or Blur setting (R0).
- **Clean methods:** AI fill and Blur only. Cover is removed, and users add an effect instead (R0).
- **Layers and the video:** all layers stick to and scale with the video, and hide at the crop edge without being cut. Clean layers in R0, all others in R5. This replaces the "output-space mask" line locked in `deep-open-items-plan.md`.
- **Scan duplicates:** the same text in the same area is one layer. Overlaps are fine (R0).
- **Rectangle effect:** not added. Cover is removed with no replacement effect.
- **Founder's projects:** no cleanup feature, and no looking inside them unless asked. The drawn boxes I found were the founder testing.

## 4. Out of scope

- Phases 2 to 5 of `deep-open-items-plan.md` (cross-video audio, photos, optical flow, HDR).
- Look, Elements and the other rail panels.
- New models or online services.
- Classic. Its prompt should be refreshed once R0 and R1 settle, because Classic copies `textfill/`.

## 5. Not verified

- Flicker has not been measured. Frame-to-frame spikes appeared on three clips and may be scene cuts.
- Leftover text at beat edges has not been checked across whole clips. I sampled the middle frame of each.
- The cost estimate assumes 4.6 s per strip-frame on a machine under heavy swap. It may be lower with other apps closed.
- Fill on a source whose crop changes the frame (16:9 to 9:16) has not been run on real video.
- LaMa has no real-video reading.
