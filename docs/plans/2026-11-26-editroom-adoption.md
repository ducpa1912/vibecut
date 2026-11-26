# What to take from Editroom (REQ-20261126-01)

Founder, 2026-11-26: learn from Editroom (MIT) and adopt its scene layout, timeline, icons, sound
waveform, and colour grading with LUTs.

Source: `github.com/robbietilton/Editroom` at `e0cbfd2`, read only. Nothing was built or run.
- Its MIT licence is © 2026 Wonder Assembly LLC.
- The repo also ships an FFmpeg binary and Sparkle. We take neither.
- No `.cube` file is in the repo: its looks are written as code.

## What Editroom is
A native macOS editor: SwiftUI for the panes, and AppKit drawing for the timeline. It has about
128 files, and the app is 7.5 MB. Its layout has four parts:
- a **Media** bin on the left;
- the **viewer** in the middle;
- the **inspector** on the right: fades, then Grade;
- the **timeline** below: V1/V2 and A1/A2 tracks with headers, a toolbar, and the ruler.

DuckSuite is a web UI inside WKWebView, with a Python core and FFmpeg render. So most of Editroom
can't be copied file for file. What we take is the method, and in two places the maths.

## What DuckSuite has today, and the gap

| Area | Editroom | DuckSuite today | Gap |
|---|---|---|---|
| Scenes | Bin grid: thumbnail, duration badge, name; search | Scene strip in Check; one "Full video" block on the timeline | The timeline doesn't show clips as pictures |
| Timeline | Filmstrip per clip, name tag, graded thumbnails; track headers (eye, lock, M/S, level dB); select and blade tools; Split, Delete, Snap | DOM lanes: video block, scene lane, script lane, audio stack | No filmstrip, no track headers, no tool modes. Split, reorder and remove-silence are P-D |
| Waveform | Average loudness (RMS) computed once, smoothed over 5 samples, lifted ×2 with 8% headroom, clip gain applied, drawn as a filled shape. Its design notes compare 5 styles and pick loudness over peaks | The browser decodes the whole audio file (`decodeAudioData`) and draws up to 64 peak bars as `<i>` elements | Peaks hide verses and builds. Decoding in the browser costs memory on long sources. There is no level data the core can reuse |
| Colour | One grade = look + strength + exposure, contrast, saturation, temperature, tint + three wheels. **It is baked into one 32³ colour cube, and the viewer, the thumbnails and the export all use that same cube.** It loads user `.cube` files and has 8 built-in looks | Four sliders. Preview uses CSS filters (`gradeFilter`, `app.js:1675`). Render uses FFmpeg `exposure`/`eq`/`colorbalance` (`render.py:242`) | **The preview doesn't match the render** (below). No looks, no LUTs, no tint, no wheels |
| Icons | SF Symbols (chevrons, warnings, `waveform`, `camera.filters` …), plus custom-drawn fade-curve icons | Our own inline SVG set (`icon()` in `app.js`) | Style only. See the icons section |

### Preview and render don't match today
Same saved grade, two different formulas:

| Slider at +50 | Preview (CSS) | Render (FFmpeg) |
|---|---|---|
| Exposure | brightness ×1.25 | +1 stop, ×2.0 |
| Temperature | `sepia(0.225)` | `colorbalance` red +0.075, blue −0.075 |

Contrast and saturation are close, but not equal. This breaks rule 3, "do not hide a limit": the
creator grades by eye on a picture the render won't produce. Editroom's one-cube method fixes
exactly this.

## How we adopt it

### G1 · One grade, one cube (Codex; first, because it fixes a bug)
1. **Bake.** `duckcore/grade.py` (new) bakes the edit's grade into one 33³ `.cube`:
   look, then look strength, then adjustments, then wheels.
   - Port Editroom's `GradeRecipe.apply` order and its 8 built-in looks from `ColorGrade.swift`.
     That is MIT code, so keep the copyright notice in `Licenses/` and in the R3 notice list.
   - Add tint now. Wheels can come later.
2. **Render.** Render applies the cube with FFmpeg `lut3d`, replacing `exposure`, `eq` and
   `colorbalance`.
   - Check that `lut3d` is enabled in our LGPL FFmpeg build (`scripts/build-ffmpeg-lgpl.sh`).
   - The render cache key changes, so the **next render of a graded edit is cold**. Warn about it.
     Fill output doesn't change, so no `textfill.VERSION` bump.
3. **Preview.** Preview uses the **same cube**: a small WebGL pass over the `<video>` frame
   (3D texture, or a 2D atlas on WebGL1). If WebGL is missing, preview shows a still frame that
   the core graded with the same cube, and says so. Never CSS filters.
   - Proof: for 3 test grades on a synthetic colour chart, the preview pixel and the render pixel
     differ by ≤ 2/255. That's a number in the review.
4. **User LUTs.** The creator can pick their own `.cube` file (a local file, like the
   translation folder).
   - Parse it with limits: 3D only, size ≤ 65, and every value finite.
   - Copy it into the data root. Show its name, never a model name.
   - Ship no LUT files of our own beyond the looks written as code.
5. **Inspector.** Look menu, strength, then the sliders, laid out the way Editroom does it: an
   icon, a label, a slider, a number field. Copy grade / paste grade between clips.

### W1 · Loudness waveform from the core (folded into P-D, founder yes 2026-11-26)
1. The core computes RMS levels once per source: 100 per second, mono, from FFmpeg into NumPy.
   It caches them next to the check data and serves them as JSON.
2. P-D's remove-silence reads **the same levels**. Then the quiet spans the creator sees are the
   ones the cutter uses.
3. The timeline draws Editroom's chosen style on a `<canvas>` per lane: RMS, a 5-sample
   smoothing, a ×2 lift, 8% headroom, clip gain applied, a filled shape. Quiet stretches show as
   a thin line.
4. The browser no longer decodes the whole file to draw the waveform. Measure memory and time on
   the 160 s project before and after.

### T1 · Timeline that shows the picture (OpenCode, after P-E)
1. **Filmstrip.** One thumbnail tile per clip, using Editroom's rule: the source seconds per tile
   is the smallest power of two that keeps a tile at least one thumbnail wide. Zooming reuses
   cached frames instead of asking for new ones.
   - Frames come from the existing frame route, with the grade applied by the G1 cube once G1
     merges.
2. **Clip name tag** on each clip.
3. **Track headers:** show/hide and lock for video. Mute, solo and level in dB for audio (the
   mixer already has solo: `audibleRows`).
4. **Tool modes:** select, and blade (click to split). They sit next to P-D's Split.
5. **Scene bin:** the Check scene strip becomes a grid with a duration badge and the scene name,
   searchable by transcript text. The transcript already exists.

### Icons: copy the style, not the glyphs
- Editroom uses Apple's SF Symbols. Their licence lets apps on Apple platforms use them through
  Apple's own APIs. Copying their shapes into our web SVG set is not something I'd risk in a paid
  App Store app.
- So in the web UI we keep our own SVG set and match the style:
  - one stroke weight (1.5 px at 18 px, 1.25 px at 14 px), monochrome, `currentColor`;
  - an icon before every inspector row label;
  - small curve icons for fade shapes, which are our own drawings.
- SF Symbols come in only with the native UI (N1–N8), through `Image(systemName:)`.

### Native UI, if the founder picks it
Editroom shows the recommended native UI route working:
- the timeline is one AppKit `NSView` drawn with `CGContext` (`TimelineCanvas.swift`, about
  2,200 lines);
- the panes and inspector are SwiftUI;
- the grade goes through `CIColorCube` with the same baked cube.

It's the best reference for N3/N4/N5 if the founder takes that decision. Nothing to build now.

## Not taken
- **Magic with Claude or ChatGPT, and MCP:** both send data out, which breaks "local only".
- **Sparkle self-update:** not allowed in the Mac App Store.
- **Their FFmpeg binary:** we build our own (R1).
- **Their release scripts:** Developer ID, notarised DMG. The App Store route is R6.
- **The AppIcon or other artwork:** that's their brand.

## Order with what's already queued
`app.js` stays with one owner at a time:

| Order | Loop | Owner |
|---|---|---|
| 1 | P-B | Codex (now; no `app.js`) |
| 2 | P-D, with W1 folded in | Codex |
| 3 | P-E | OpenCode |
| 4 | G1 | Codex |
| 5 | T1 | OpenCode |

G1's core half (bake, render, LUT parsing, tests) has no `app.js` work. It can run in parallel
with P-E, and its preview half lands after P-E.

## Not checked yet
- Editroom's speed and how its colours look: I didn't build or run it.
- Whether our LGPL FFmpeg has `lut3d`.
- How fast WebGL preview is in WKWebView on an M1 with 8 GB.
