# Studio UI revamp — P4 other steps (2026-11-02)

Base: `1a4645a` (P3 polish). Branch: `studio`.

## Summary

P4 brings the other three steps onto the Studio frame. The app bar is a
48 px strip with the brand, four steps, video name/status and one Menu; Change
video and Voice Room now live inside that Menu. Import puts the rights gate
beside Start and shows recent videos first when there are any. Moments shows
the video's text-scan state and Scan for text action next to its title. Finish
gets the same one-screen frame as Edit: a compact head and one scrolling body
with a stable gutter, plus a Back to Edit action.

## What changed

### Shared app bar

- `static/studio/shell.js` — removed top-bar Change video and Voice Room; the
  Menu dialog now has a Workspace row with both, and Change video closes the
  menu before opening the video library.
- `static/studio/studio.css` — 48 px app bar (7 px padding, 34 px steps); the
  Workspace row; the shared panel head/action layout; Finish's fixed frame.

### Import

- `static/studio/import.js` — the rights tick moved into the Start block,
  directly above Import video. Recent videos toggle `has-recent` and become
  the first column/card when the list is not empty.
- `static/studio/studio.css` — recent-first grid, Start block spacing.

### Moments

- `static/studio/stories.js` — a header action shows the text-scan state
  ("Text not scanned", "Checking text…", "N text regions found", "No on-screen
  text", "Scan needs attention") with Scan for text / Scan again / Cancel scan.
- The existing detailed scan card stays below the moments when it has results
  or an error.

### Finish

- `static/studio/finish.js` — Back to Edit in the Finish head.
- `static/studio/studio.css` — `main[data-step="finish"]` is a fixed frame;
  the Finish panel fills it and `.st-finish-body` is the only scrolling
  surface, with `scrollbar-gutter: stable`.
- The Finish title drops to the 28 px page-title scale.

## Verified

- New source tests: app-bar actions, Import ordering/rights placement,
  Moments scan state/action, Finish fixed frame and scroll gutter.
- Mounted Chromium at 1280×720 and 1024×680:
  - app bar is compact and has one top action;
  - Finish has no page scroll and its body owns the scroll;
  - Moments shows Scan for text in the header;
  - Import has the rights tick beside Start and recent videos first.
- Full suite: **2022 passed, 12 skipped, 1 deselected** on the P4 tree;
  the deselected Voice Room browser test fails identically on `88eeab9`.

## Known limits

- Import, Moments and Finish remain page-sized forms; only Edit and Finish use
  the fully fixed one-screen frame. Import/Moments can still scroll as pages
  because their lists and forms are longer than one screen.
- The Finish head is a compact page head rather than a second toolbar row;
  step navigation stays in the shared app bar.
- Change video and Voice Room are one Menu click away instead of top-level.

## Next

The revamp plan's phases P0–P4 are complete. The remaining follow-ups are
polish items found in a real recorded run, not a new phase.
