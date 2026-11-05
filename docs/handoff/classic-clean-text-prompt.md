# Classic lane prompt: Clean and text removal

Date: 2026-11-05
Source: Studio `studio` branch, `7cbc267`
Target: Classic lane, `classic` branch
Companion: `clean-fill-revision-plan.md`, `classic-studio-matrix.md`

This file is a direction and a ready-to-use prompt. Studio is the source of
truth for behaviour. Classic adapts it, because Classic has no timeline.

---

## 0. Rule

Copy behaviour, not gating.

Studio still carries the Rights gate from R1. The founder has decided to remove
it. Do **not** copy the gate into Classic. Copy the Clean behaviour only:
detection, one row per text, AI fill, Blur, crop guard, preview, render.

Two more rules:

- Classic owns its own Python copies after the port. Do not make Classic import
  Studio UI or Studio page code.
- The Classic worktree has uncommitted AI-fill work. Reconcile it before any
  copy. Do not overwrite it.

---

## 1. What Studio has today

### Clean model

One Edit per story/aspect. Clean is a list of layers in `edit.clean[]`.

Supported kinds in `edits.CLEAN_KINDS`:

```
crop_guard, blur, plate, mask, mosaic, delogo, fill
```

The product surface uses only:

| Surface kind | What it does |
|---|---|
| `fill` | AI text fill. `method` is `lama` or `sttn`. LaMa is default. |
| `blur` | Blur the box for its time ranges. |
| `crop_guard` | Keep the box out of the crop. |

`cover`/`plate` is removed from the UI. Users add an effect instead.

Layer fields:

```json
{
  "id": "cl01",
  "kind": "fill",
  "method": "lama",
  "box": {"x": 0.10, "y": 0.72, "w": 0.80, "h": 0.14},
  "mask": {"space": "source", "strokes": [{"id": "st_1", "r": 0.025, "points": [{"x": 0.2, "y": 0.8}]}]},
  "ranges": [{"start": 12.4, "end": 18.9}],
  "z": 0,
  "color": "#000000",
  "opacity": 1.0,
  "radius": 24,
  "label": "Found text",
  "tracklet_id": "t_...",
  "tracklet_kind": "subtitle",
  "text_key": "8f3a1c02"
}
```

Rules:

- Clean boxes are in **source** coordinates.
- One layer per found text. Repeated readings of the same text in the same area
  merge into one row.
- `ranges` drive when the layer applies.
- A mask narrows the fill to painted pixels. Without a mask, the whole box is
  filled.
- Same text in the same area is one layer. Overlaps are allowed in the data, but
  the UI must show one lane per text.

### Detection

Check produces `SourceReport` tracklets:

```json
{"id": "...", "kind": "subtitle", "box": {"x": 0, "y": 0, "w": 1, "h": 1},
 "ranges": [{"start": 1.2, "end": 4.8}], "text_sample": "...", "confidence": 0.8}
```

Kinds:

```
subtitle, title, lower_third, handle_or_logo, watermark, credit, screen_text
```

`screen_text` is dense UI/document text. Studio never pre-fills it. That rule
is removed with the gate. In the new direction, every kind is cleanable.

### Endpoints

```
POST /api/jobs/{id}/cleanup/plan        plan only, no render
POST /api/jobs/{id}/cleanup/layers      turn Check tracklets into Clean layers
POST /api/jobs/{id}/cleanup/residual    OCR the cleaned output
GET  /api/fill/status                   which engines are ready
POST /api/jobs/{id}/edits/{edit_id}/fill-estimate
POST /api/jobs/{id}/edits/{edit_id}/fill-sample
POST /api/jobs/{id}/edits/{edit_id}/fill-sample/cancel
POST /api/jobs/{id}/edits/{edit_id}/fill-preview
```

### Render

- Fill pre-pass runs only for beats that carry a fill layer.
- Each beat is cut as its own segment; results are cached by source, span,
  layers, engine and model.
- LaMa is default (`textfill.DEFAULT_METHOD = "lama"`).
- Missing model pack disables AI fill only. Clean still opens and Blur still
  works.
- `render_reel` returns per-stage timings (`fill`, `segments`, `concat`,
  `layers`, `captions`, `audio`, `mux`, `poster`, `total`).

### UI

- Icon rail; Clean is one panel.
- "Scan video" and "Check this scene" fill the found-text list.
- One row per found text: time, kind, sample, method, include tick.
- Row click seeks to the text's first range.
- Per-row method: AI fill or Blur.
- Brush creates or reuses a mask on the row.
- Before/After compares one frame.
- Row states: allowed, excluded, outside the cut.

---

## 2. Studio work that must happen before the Classic port

These are founder decisions, not parity items. Build them in Studio first, then
port the finished behaviour.

### 2.1 Remove the Rights gate

"Nothing is locked."

Remove:

- `rights.py` as a gate, and `rights_router`.
- Import confirmation in `app.py` and `routes_batches.py`.
- `_require_clean_rights` in `routes_edits.py`.
- Rights checks in `cleanup.py`, `detect.py`, `routes_cleanup.py`.
- Per-video attestation tick and `settings.rights.lock`.
- Watermark refusal, handle/logo tick, `screen_text` refusal.
- Rights copy in the UI.

Keep:

- A plain notice that the user is responsible for the footage they clean.
- The existing forbidden-word check on labels, if it guards filenames only.

Every detected kind becomes cleanable: subtitle, title, lower third, handle or
logo, watermark, credit, screen text, UI.

### 2.2 One lane per found text, no overlap

Today the timeline has one Clean lane and pushes found-text markers into it.

New behaviour:

- Every distinct found text gets **its own lane**.
- A lane holds that text's ranges only.
- Lanes stack in first-appearance order.
- Lane height is fixed and readable; text is at least 11 px.
- No two lanes may render over each other. If ranges would collide, assign a
  new lane instead of stacking bars in the same row.
- Drawn boxes get their own lane too, one per box.
- Hiding or excluding a row hides its lane; it does not renumber the others.

### 2.3 Click found text goes to the exact moment

Studio already seeks on row click. Harden it:

- Click seeks to the first range start, minus 0.5 s of context.
- The matching box is highlighted.
- If the text is outside the current cut, the row says "Not in this cut" and
  does not seek.
- Clicking a lane bar seeks to that bar's start.
- Double-click opens the row's full detail.

### 2.4 Simple Clean-only preview panel

"Just focus on cleaning the text."

Build a dedicated panel or mode:

- Preview shows the video frame only. No captions, text, effects or graphics.
- The Clean overlay shows boxes and brush masks only.
- Header: source time, scene or moment, fill engine, estimated time.
- Controls: Before/After, Play 1 s, Fill this text, Blur this text, Exclude.
- Below: one row per text, one lane per text, same order as the timeline.
- Click row or lane: seek to that moment and highlight.
- Empty state: "Scan this video", with Scan scene and Scan video.
- No other Edit panels in this mode.

### 2.5 Clean and text removal improvements

Carry every known fix:

1. Cap a drawn box. A huge `delogo` box must not streak the frame.
2. Fill only text pixels. Use the mask when present; never repaint 44–77 % of
   pixels outside the glyphs.
3. Show cost before a fill. Estimate per strip-frame, multiplied by strips and
   beats. Warn when it is minutes, not seconds.
4. Do not union top and bottom rects into one strip pass. Fill each band.
5. Brush and box combine. One brush click must not shrink the fill to 25×25.
6. The row brush button must not add duplicate layers when nothing is painted.
7. Preview must use the same engine as render. LaMa is default for both.
8. Preview takes the fill lock and releases the model when done.
9. Ranges include the ±1 s margin used by the fill.
10. Masks stay in source space across beats and crop changes.
11. Fill status checks model file **and** runtime package (`torch`,
    `onnxruntime`).
12. Group duplicates in the list; hide layers outside the story behind a
    toggle.
13. Keep the Clean lane visible at 1280×720.
14. Minimum readable text size, 11 px or more.
15. Brush strokes join points; no dotted stamps on fast drags.
16. Delete `.part` files when a fill or render is killed.
17. Docs and comments must say that AI fill exists.

---

## 3. Classic adaptation

Classic has **no timeline**. It has scenes and moments.

Mapping:

| Studio | Classic |
|---|---|
| Timeline lane | One row in the Clean list, with a mini range bar |
| Row click seeks timeline | Row click opens the moment, then seeks |
| Found text lane | One Clean row per text |
| Play 1 s | Play the moment from the text start |
| Scene/moment strip | Moment cards |

Click behaviour in Classic:

1. Read `tracklet.ranges[0].start`.
2. Find the moment or scene whose source range contains it.
3. Select that moment.
4. Seek to `start - 0.5 s`.
5. Highlight the box on the preview.
6. If no moment contains it, show "Not in this cut" and stay put.

Do not copy the Studio timeline component. Build the same information as a
vertical list with a small range bar per row.

---

## 4. Copy-paste prompt for the Classic lane

```text
You are working in the Classic lane of VibeCut. Classic is a second supported
product, not a frozen beta. Studio is the source of truth for Clean behaviour.
Do not import Studio page code. Do not copy the Studio Rights gate.

Worktree: vibecut-classic, branch classic.
Warning: the worktree has uncommitted AI-fill work. Reconcile it first. Do not
overwrite it.

GOAL
Bring Classic Clean and text removal up to Studio behaviour, adapted to a
product that has scenes and moments but no timeline.

NON-GOALS
- No timeline.
- No Rights gate, no attestation, no per-video tick, no watermark refusal.
- No Cover/Plate method.
- No Studio UI imports.
- No new AI model.

BEHAVIOUR TO BUILD

1. Clean methods
   - AI fill: LaMa default, STTN optional.
   - Blur.
   - Crop guard.
   - Cover/Plate removed from the UI.
   - Missing model pack disables AI fill only; Clean and Blur still work.

2. Nothing is locked
   - subtitle, title, lower third, handle or logo, watermark, credit,
     screen text and UI are all cleanable.
   - No import confirmation, no attestation route, no settings lock.
   - Keep a plain responsibility notice.

3. Found text
   - One row per distinct found text.
   - Same text in the same area merges into one row.
   - Every row shows: time, kind, text sample, method, include tick.
   - One row per lane. Rows never overlap in time within a lane.
   - Drawn boxes get their own row.

4. Click to the exact moment
   - Click a row: open the moment that contains the text start, seek to
     start minus 0.5 s, highlight the box.
   - If the moment is not in the current cut: show "Not in this cut".
   - Double-click opens the row detail.

5. Clean-only preview panel
   - Frame only. No captions, text, effects or graphics.
   - Boxes and brush masks only.
   - Header: source time, moment, engine, estimated time.
   - Controls: Before/After, Play this text, AI fill, Blur, Exclude.
   - List of one row per text below.
   - Empty state: "Scan this moment" and "Scan video".

6. Fill quality and cost
   - Fill only text pixels when a mask exists.
   - Cap drawn boxes; never streak the frame.
   - Do not union top and bottom bands into one strip pass.
   - Show a cost estimate before fill.
   - Brush and box combine; one brush click must not shrink the fill.
   - The row brush button must not duplicate layers.
   - Preview uses the same engine as render and releases the model after.
   - Include the ±1 s range margin.
   - Keep source-space masks stable across cut and crop changes.
   - Readable type, minimum 11 px.

7. Data and API
   - Reuse the Edit clean schema: id, kind, method, box, mask, ranges, z,
     color, opacity, radius, label, tracklet_id, tracklet_kind, text_key.
   - Endpoints: cleanup plan, cleanup layers, residual, fill status,
     fill estimate, fill sample, fill cancel, fill preview.
   - Clean boxes are in source coordinates.

8. Render
   - Fill only beats that carry a fill layer.
   - Cache filled clips by source, span, layers, engine and model.
   - Keep LaMa as default.
   - Delete .part files on cancel.
   - Report per-stage timings.

ACCEPTANCE TESTS
- A job with subtitle, title, logo and watermark: every kind can be added,
  previewed and rendered. No 409 and no "needs a tick".
- Click each found text: Classic opens the right moment and seeks to it.
- A text outside the cut says "Not in this cut" and does not move.
- Two texts at different times render as two rows and two lanes; no overlap.
- AI fill with LaMa is default; STTN is selectable.
- With the model pack removed, Clean opens, Blur works, AI fill says why it
  cannot run, and nothing crashes.
- Brush then fill fills the stroke, not the whole box.
- Top and bottom text fill separately.
- Cancel mid-fill leaves no .part file.
- Full suite green.
- One real clip: before/after frames match the middleware and the render.

DO NOT
- Do not copy Studio rights code.
- Do not copy the Studio timeline.
- Do not overwrite the uncommitted Classic work.
- Do not call a phase done before the founder's real-clip test.
```

---

## 5. Order of work

1. Studio: remove the Rights gate. Land it alone.
2. Studio: one lane per text, no overlap.
3. Studio: click-to-moment hardening.
4. Studio: Clean-only preview panel.
5. Studio: the 17 clean fixes.
6. Classic: port the finished behaviour, with the prompt above.
7. Founder test on one real clip per lane.

Do not port a gate that is about to be deleted.
