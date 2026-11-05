# Studio features embedded in Classic

Status: C0–C4 and AI fill built, none founder-passed. Base: `origin/studio`
at `8457728`; Classic at `18b46ac`.

Classic is not an iframe around Studio. The goal is to bring the interaction
patterns that fixed Studio's editor into Classic, while keeping Classic's page,
state and lane ownership independent.

## Studio review

| Phase | Feature | What Classic should take |
|---|---|---|
| P0 | Fixed editor frame, compact toolbar, one scroll per panel, Find text on screen, scan progress/cancel | The frame and the scan flow. Classic currently has no in-Editor text scan. |
| P1 | Layers panel, boxes drawn on the preview, draw/move/resize/delete, selection shared with timeline | The Layers panel and box editing. Classic has no equivalent. |
| P2 | Found-text list with thumbnails/ticks, AI fill / Blur / Cover, single-frame LaMa preview | The whole flow, but this is a backend port: Classic has only work-file Clean, not Studio's Clean text layers. |
| P3 | Spacing/type scale, icon set, layer colours, shortcuts, undo/redo, empty-state actions | The design system and keyboard model, adapted to Classic. |
| P4 | Shared app bar, Import/Moments/Finish frames, recent-first Import, scan state in Moments | The app bar and the Finish/Import/Moments layout rules. |

## What Classic already has

- Ingest, progress, moments, Smart Cut, Edit cards, sound, texts, captions,
  Creator, history and render.
- A work-file Clean profile (`Work files`, `Renders`, `All but source`).
- Hook/scene thumbnails with per-shape crops.
- A render pipeline that consumes Classic text layers and effects on 9:16 and
  4:5.

## What Classic does not have

- Studio's Edit document and Clean text-layer model.
- Clean boxes on a preview.
- A frame/proxy preview route for an edited cut.
- The `textfill` AI-fill pre-pass and model status.
- Studio's Layers/Inspector/Timeline component model.

Those are real ports, not CSS copies.

## Independence rules

- Classic may use shared **pure** modules under `static/shared/**`.
- Classic must not import `static/studio/edit/**` or Studio state.
- Studio must not import `static/classic/app.js`.
- New backend routes for Classic go in `routes_classic.py`.
- Shared backend changes stay additive and are tested from Classic.

Extract these pure helpers first:

- box/crop geometry (`canvas-tools.js` pattern)
- source-time ↔ cut-time mapping
- render-signature helpers
- platform capability helpers
- i18n key/glossary helpers

## Phases

### C0 — Frame and scan

**Goal:** Classic Edit fits one screen and can start a text scan from the
editor.

- Fixed Classic result/Edit frame with one scrolling panel per area.
- Compact app bar/toolbar; no sticky bar over content.
- `Find text on screen` when Check has no finished pass.
- Progress, cancel and retry in the panel.
- Empty states with actions.

**Files:** `static/classic/index.html`, `static/classic/app.js`,
`static/classic/style.css`, `routes_classic.py`.

**Done when:** at 1280×720 and 1024×680 the preview, timeline and settings are
visible without page scroll; the founder can start and cancel a text scan from
Edit.

**Status:** built, not founder-passed. From 1000px up `#result-view` is one
grid — compact `.result-top`, then `.editor-pane-preview`,
`.editor-pane-timeline` and `.editor-pane-settings`, each scrolling on its own
while the page does not. Below 1000px the three wrappers are
`display: contents`, so a narrow screen keeps the single column it had. The
scan card sits above Copy/sound/text and drives the shared
`POST/GET /api/jobs/{id}/check` routes; Classic added no scan route of its own.

Evidence: `tests/test_classic_frame.py` and
`tests/browser/classic_frame.spec.mjs` run on a fixture job at 1280×720 and
1024×680 — no page scroll, all three panes visible, scan idle → running →
cancelled → ready. Check is stubbed in that spec, so a live scan on a real job
still belongs to the founder pass.

### C1 — Layers and boxes

**Goal:** the founder can see and edit every Clean box without number fields.

- Layers panel grouped in timeline order.
- Clean boxes on the Classic preview.
- Draw box, move, resize, delete.
- Selecting a row, timeline bar or box selects the same layer.
- `+` on every group; eye toggle; warnings for boxes outside the crop.

**Backend:** add a Classic frame/proxy route for the current cut. There is no
existing Classic frame endpoint that can address the cut time and shape.

**Done when:** the founder adds, moves and deletes a Remove-text box without
typing a percentage.

**Status:** built, not founder-passed. The preview is a real render, not a CSS
approximation: `POST /api/classic/jobs/{id}/frame` compiles the cut on screen —
unsaved boxes included — through the same `compose_render` graph the reel uses
and returns one JPEG from `render.render_story_frame` (`no-store`, draft size,
cached by compiled hash). A box therefore cannot look right in the preview and
wrong in the export. Boxes are stored on the cut
(`job["classic_text"]["cuts"][clips_hash]["clean"]`) beside overlays and
effects, so one save carries all three; `_build_classic_edit` maps Classic
`method` to the Edit kind (`blur→blur`, `cover→plate`, `crop→crop_guard`) and
`prepare_classic_render` treats a cut with only Clean boxes as a real Edit.
Gestures: drag to draw, drag to move, corner pulls to resize, `Del`, arrow
nudges, `⌘Z`/`⇧⌘Z`, eye toggle, per-row method chips. The canvas is measured
from the preview pane, so its corner handles stay on screen at 1024×680.

Evidence: `tests/test_classic_clean.py` (format, compile, rights, frame route,
fill status) and `tests/browser/classic_clean.spec.mjs` at 1280×720 and
1024×680 — draw, move, retag, hide, reload, undo, delete. The spec runs on a
real fixture video, so the JPEG it asserts is a real ffmpeg frame.

### C2a — Found text, Blur and Cover

**Goal:** remove old text from the regions Check actually found with Blur or
Cover. AI fill follows in C2b.

- Found-text list with thumbnails, words, time and ticks.
- Watermarks and screen UI greyed with the server reason; never tickable.
- Method picker: Blur and Cover in C2a; AI fill joins in C2b.
- Rights gate and Clean layer storage on the server.

**Backend:** do not import Studio's `routes_studio.py`. Extract or fork the
Clean/Edit schema, Clean compilation, rights gate and Check contract into
`edit_contract.py` with a versioned API and Classic tests.

**Decision:** `edit_contract.py` was not written, because the contract already
exists as edition-neutral shared code — `edits.normalize_clean`/`build_edit`,
`compose_render._clean_filters`, `rights`, `detect.clean_prefill` and the Check
report. Forking them into a second schema would be the duplication the rule
exists to prevent. Classic adds only its own layer fields (method, scan source,
eye) in `routes_classic.py` and validates through `edits.normalize_clean`, so a
Classic box can never be a shape the renderer does not understand. If Studio
later needs a different schema, that is when an `edit_contract.py` earns its
keep.

C2 also needs a model-pack prerequisite before AI fill is offered:

- `sttn_infer_model.pth` and `lama_fp32.onnx`
- size and SHA-256 in the release notes
- install path under `~/vibecut-lanes/classic/models/fill`
- license notices for STTN and LaMa
- a missing-model state that falls back to Blur/Cover

Until the model pack and frame route exist, C2 stays at Blur/Cover.

**Done when:** the founder removes every subtitle in a moment with Blur or
Cover and the rights gate refuses watermarks and screen UI.

**Status:** built, not founder-passed. The found-text list reads Check's own
`clean_prefill`: thumbnail from the nearest scene still cropped by CSS to the
found box, kind and server reason. Rows are ticked, then one "Remove ticked"
removes them all with one method (Blur, Cover, or AI fill), in one undo step. Watermark and screen-UI rows are greyed with the
server's reason and have no tick. Scan ranges are source time and boxes are
translated clip by clip; text no clip carries says "not in this cut" instead of
becoming a box that never appears. The rights gate is enforced on the server as
well: `PUT /api/classic/jobs/{id}/text` refuses a blocked kind with `409`, and
the rights lock refuses any box until the import carries the own-footage tick.
Proven in `tests/test_classic_clean.py::test_the_server_refuses_a_box_the_policy_blocks`
and `test_the_rights_lock_refuses_clean_without_the_tick`.

### C2b — AI fill

**Port notes:** [ai-fill-clean-learnings.md](ai-fill-clean-learnings.md).

**Goal:** add AI fill to C2a.

- Engine status and missing-model note.
- Single-frame LaMa preview with before/after slider.
- `textfill` port and render hook.
- Model pack, license notices and cache keys.

**Done when:** the model pack is installed, the founder sees the AI-fill
preview, and the full render fills every frame. Until then, C2 stays at Blur
and Cover.

**Status:** built, models available, not founder-passed. The shared model
cache at `~/.cache/vibecut/models/fill` has both `sttn_infer_model.pth` and
`lama_fp32.onnx`; `lane-env.sh` points `VIBECUT_FILL_MODELS` there. The two
files match the hashes in the Studio fill test plan. The runtime packages
(`torch` for STTN, `onnxruntime` for LaMa) are present on the machine.

`textfill/` is a byte-identical copy of Studio `7ce8dcf`; the Edit schema
accepts `kind: "fill"` with `method: "sttn"|"lama"`; the render holds
`render.FILL_LOCK`, fills each segment with a fill plan before encoding and
releases the models afterwards; the cache key carries the model stamp and the
layer signature. Classic keeps its own `method` (blur/cover/crop/fill) and adds
`engine` on fill layers only.

`GET /api/classic/fill` answers per engine, not one flag: `ready` means the
model file **and** its runtime package are present, and each engine carries its
own reason. STTN installed without LaMa still fills subtitles; only the
one-frame preview needs LaMa, because STTN needs neighbouring frames.
`POST /api/classic/jobs/{id}/fill/preview` compiles the unsaved boxes, reads
the source frame at the right source time, fills it with LaMa, burns overlays
and returns before/after JPEGs cached by edit, frame and model; it answers
`409 fill_running` while a render holds the fill lock. The preview now runs
the same rights gate as save/render, so a watermark or un-attested box is
refused before any pixels change. The panel shows what is ready and what is
missing, the cost per engine, an engine picker per fill layer, and only enables
Preview when LaMa is ready. The render progress already reads server progress,
so a fill render says `Filling text, beat i/n` and the existing Cancel stops
it. No real full fill render has been verified in Classic yet; that is the
founder's test.

### C3 — Polish

- Spacing/type scale.
- One icon set.
- Layer colours.
- Keyboard shortcuts and `?` sheet.
- Undo/redo.
- Empty-state actions.

**Status:** built, not founder-passed. The stage and panel use the page's
existing scale (`--mono` kickers at 10-11px, 13px labels, 12px hints) instead of
new one-off sizes. The toolbar uses one glyph set (`＋ ↶ ↷ ↻`) and drops its
words below 1180px, where the column cannot hold them; every glyph keeps its
`title` and `aria-label`. Layer colours come from the method (accent for Blur,
blue for Cover, dashed for Crop) so the frame and the row agree. Keys: `B` draw,
`Del`, arrows, `Shift`+arrows, `Esc`, `⌘Z`/`⇧⌘Z`, `?` for the sheet (Chromium on
macOS reports Shift+/ as `/`, so both open it). Undo/redo is one stack over
text, effects and boxes, capped at 40. Empty states: the panel says there are no
boxes and offers both routes (scan or draw).

### C4 — Import, Moments, Finish

- Shared app bar.
- Rights tick beside Start.
- Recent videos first.
- Moments text-scan state/action.
- Finish fixed frame and Back to Edit.

**Status:** built, not founder-passed. The rights tick is a checkbox beside
Dissect video, shown only when Setup's lock asks for one; a start that skips it
reveals and highlights the tick instead of a blocking `window.confirm`. The
Moments head carries the scan state as one chip (`Find text on screen ›`,
`scanning text…`, `text scanned ✓`, `… failed`) that starts a scan when there is
none and jumps to the card otherwise. Finish is one fixed frame: the edit panes
step aside, the player and Render/Download take the page, and the same button
returns as `Back to edit` with every box intact. Recent cuts were already
newest-first through `GET /api/jobs`, so C4 changed nothing there.
**Not taken:** Classic keeps its own top bar rather than importing Studio's
shared app bar. Classic owns its page, and the shared bar is Studio's component;
copying it would be the CSS-only port this document rules out.

## Order and gates

1. C0 ships and is founder-tested.
2. C1 ships; boxes are usable.
3. C2 ships behind the existing rights gate; real-video fill test required.
4. C3 and C4 ship together only after C1/C2 are stable.

Every phase gets:

- senior dev build;
- QA full relevant tests;
- QC live browser pass at 1280×720 and 1024×680;
- tester founder flow;
- product + principle-engineer co-sign;
- signed commit.
