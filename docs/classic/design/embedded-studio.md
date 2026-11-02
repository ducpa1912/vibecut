# Studio features embedded in Classic

Status: plan. Base: `origin/studio` at `8457728`; Classic at `ba31215`.

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

### C1 — Layers and boxes

**Goal:** the founder can see and edit every Clean box without number fields.

- Layers panel grouped in timeline order.
- Clean boxes on the Classic preview.
- Draw box, move, resize, delete.
- Selecting a row, timeline bar or box selects the same layer.
- `+` on every group; eye toggle; warnings for boxes outside the crop.

**Backend:** a Classic preview/frame route for the current cut, or reuse an
existing frame endpoint if it can address the cut time and shape.

**Done when:** the founder adds, moves and deletes a Remove-text box without
typing a percentage.

### C2 — Found text and AI fill

**Goal:** remove old text from the regions Check actually found.

- Found-text list with thumbnails, words, time and ticks.
- Watermarks and screen UI greyed with the server reason; never tickable.
- Method picker: AI fill, Blur, Cover.
- AI-fill engine status and missing-model note.
- Single-frame LaMa preview with before/after slider.
- Rights gate and Clean layer storage on the server.
- AI-fill render pre-pass and cache keys.

**Backend:** port/share `edits.py` Clean layers, `textfill`, `compose_render`
Clean compilation and the render hook. This is the largest phase.

**Done when:** the founder removes every subtitle in a moment and sees an AI
fill preview before rendering.

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
