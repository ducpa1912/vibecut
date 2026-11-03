# Studio features embedded in Classic

Status: plan, C0 built. Base: `origin/studio` at `8457728`; Classic at `193b60e`.

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

C2 also needs a model-pack prerequisite before AI fill is offered:

- `sttn_infer_model.pth` and `lama_fp32.onnx`
- size and SHA-256 in the release notes
- install path under `~/vibecut-lanes/classic/models/fill`
- license notices for STTN and LaMa
- a missing-model state that falls back to Blur/Cover

Until the model pack and frame route exist, C2 stays at Blur/Cover.

**Done when:** the founder removes every subtitle in a moment with Blur or
Cover and the rights gate refuses watermarks and screen UI.

### C2b — AI fill

**Goal:** add AI fill to C2a.

- Engine status and missing-model note.
- Single-frame LaMa preview with before/after slider.
- `textfill` port and render hook.
- Model pack, license notices and cache keys.

**Done when:** the model pack is installed, the founder sees the AI-fill
preview, and the full render fills every frame. Until then, C2 stays at Blur
and Cover.

### C3 — Polish

- Spacing/type scale.
- One icon set.
- Layer colours.
- Keyboard shortcuts and `?` sheet.
- Undo/redo.
- Empty-state actions.

### C4 — Import, Moments, Finish

- Shared app bar.
- Rights tick beside Start.
- Recent videos first.
- Moments text-scan state/action.
- Finish fixed frame and Back to Edit.

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
