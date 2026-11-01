# Studio UI revamp — P0 fit and fix (2026-11-01)

Base: `88eeab9` (the UI revamp plan). Branch: `studio`.

## Summary

P0 turns Edit into one fixed screen and removes the dead end on text
scanning. At 1280x720 and 1024x680 the preview, timeline and settings are all
visible with no page scroll. The sticky step bar is gone; a compact toolbar
holds the moment, shape, undo and Finish. The settings stay on the right at
1024 and above, and both panels own their scroll with a stable gutter.

The Remove text panel now offers **Find text on screen** when Check has no
finished text pass, including the cancelled state from the founder's video.
It starts `POST /api/jobs/{id}/check`, shows progress in the panel, polls
until the report lands, and can cancel through `POST .../check/cancel`.

## What changed

- `static/studio/edit/index.js` — fixed-frame shell, one toolbar (Back,
  moment picker, shape, undo, save state, Finish), All moments moved into the
  moment picker, big page title removed, no sticky CSS injection.
- `static/studio/shell.js` — marks `main` with `data-step` so the Edit frame
  is scoped to the editor and other steps keep their page scroll.
- `static/studio/edit/edit.css` — fixed frame; preview shrinks; timeline is
  always visible and scrolls its tracks; settings panel stays on the right
  at >= 1024; one scroll per panel with `scrollbar-gutter: stable`; compact
  inspector tabs (Remove text / Text & effects / Audio).
- `static/studio/edit/layers/clean.js` — corrected Remove text copy (AI fill
  does rebuild pixels), `Find text on screen` button, progress and cancel,
  "Remove all found text", and the scan action replaces the old "Open
  Moments" dead end.
- `static/studio/edit/inspector.js` — shorter tab label that never truncates.
- Tests: `tests/test_studio_edit_p0.py`,
  `tests/browser/edit_layout.spec.mjs`, `tests/test_browser_edit_layout.py`;
  updated the old sticky-bar assertion.

## Verified

- `tests/test_studio_edit_p0.py` — fixed frame, toolbar, scroll gutters,
  1024 breakpoint, scan copy.
- Mounted Chromium at **1280x720** and **1024x680** — no page scroll,
  preview + timeline + settings inside the viewport, settings on the right,
  timeline below the preview, text scan visible in Remove text.
- Full suite: 1983 passed, 12 skipped, 1 failed
  (`test_voice_room_page.py::test_voice_room_page_in_chromium`). The same
  test fails on a clean worktree at `88eeab9`; the Voice Room page no longer
  renders the clip-finder panel the spec expects. P0 does not touch Classic
  or Voice Room.

## Not in P0

Layers list, boxes drawn on the preview, drag/resize, found-text thumbnails,
method picker and the AI-fill single-frame preview are P1 and P2 in
`docs/handoff/ui-revamp-plan.md`.
