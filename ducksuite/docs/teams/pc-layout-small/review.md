# P-C · Layout at small sizes — review (loop 28, REQ-20261115-02 P2)

Owner: OpenCode · branch `oc/pc-layout-small` · port 8821 · scratch data root
`build/scratch-root` · 2026-11-26.

**Verdict: good to go for the measured screens.** Three CSS cascade defects and
the Edit frame timecode are fixed; the whole reachable set is clean at
1440×900, 1280×800, 1024×700 and 512×350. The screens that need footage are
listed for the founder's hand test, and one of them (the Edit bar inside a 9:16
stage) has a defensive rule that only the hand test can judge.

## Method

`scripts/measure-layout.mjs` drives headless Chrome over the DevTools protocol.
It measures `welcome`, `check`, `edit`, `clean`, `preview`, `render`, the
Settings modal and the import modal at four CSS viewports:

| Size | Meaning |
|---|---|
| 1440×900, 1280×800 | the sizes loop 10 measured; kept unchanged |
| 1024×700 | the smallest normal window |
| 512×350 | the CSS viewport a 1024×700 window gives at 200 % zoom |

For each screen and size it records: horizontal page scroll
(`documentElement.scrollWidth > clientWidth`), every box of a button, input,
heading or image that intersects another such box inside the same scroll
container (media chips, timecodes and badge overlays excluded as designed),
button text that clips (`scrollWidth > clientWidth`), controls past the left or
right viewport edge, text labels that clip with `nowrap`/`overflow:hidden`, and
the bottom of the content in % of the viewport. It also probes the Edit player
bar at 340 px (the 1024 landscape preview column) and at 132 px (a 9:16 stage in
that column).

No footage was used. The scratch project points at a source file that does not
exist, so project screens render their empty states. No founder project, frame
or Containers path was read, and no media was made or downloaded.

## Results (before → after)

`False` = no horizontal scroll. A % pair is content bottom before → after.
Overlap counts exclude designed media overlays.

| Screen | Size | H-scroll | Overlaps | Clipped buttons | Off-screen | Bottom |
|---|---|---|---|---|---|---|
| Welcome / projects | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 90.7% / 90.7% |
| Welcome / projects | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 89.5% / 89.5% |
| Welcome / projects | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 87.4% / 87.4% |
| Welcome / projects | 512×350 | False | 3 → 0 | 0 → 0 | 0 → 0 | 100% / 100% |
| Check | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 88.7% / 88.7% |
| Check | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 87.3% / 87.3% |
| Check | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 93% / 93% |
| Check | 512×350 | False | 5 → 0 | 0 → 0 | 0 → 0 | 100% / 100% |
| Edit (empty editor) | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 29.9% / 29.9% |
| Edit (empty editor) | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 33.6% / 33.6% |
| Edit (empty editor) | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 37.9% / 37.9% |
| Edit (empty editor) | 512×350 | False | 4 → 0 | 0 → 0 | 0 → 0 | 81.4% / 94.2% |
| Clean (no layers) | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 29.9% / 29.9% |
| Clean (no layers) | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 33.6% / 33.6% |
| Clean (no layers) | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 37.9% / 37.9% |
| Clean (no layers) | 512×350 | False | 4 → 0 | 0 → 0 | 0 → 0 | 81.4% / 94.2% |
| Preview (empty) | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 29.9% / 29.9% |
| Preview (empty) | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 33.6% / 33.6% |
| Preview (empty) | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 37.9% / 37.9% |
| Preview (empty) | 512×350 | False | 5 → 0 | 0 → 0 | 0 → 0 | 81.4% / 94.2% |
| Render queue | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 93.1% / 93.1% |
| Render queue | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 92.3% / 92.3% |
| Render queue | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 91.8% / 91.8% |
| Render queue | 512×350 | False | 5 → 0 | 0 → 0 | 0 → 0 | 100% / 100% |
| Settings → Engines (modal) | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 98.1% / 98.1% |
| Settings → Engines (modal) | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 97.9% / 97.9% |
| Settings → Engines (modal) | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 97.6% / 97.6% |
| Settings → Engines (modal) | 512×350 | False | 0 → 0 | 0 → 0 | 0 → 0 | 95.1% / 95.1% |
| Import dialog (modal) | 1440×900 | False | 0 → 0 | 0 → 0 | 0 → 0 | 65.6% / 65.6% |
| Import dialog (modal) | 1280×800 | False | 0 → 0 | 0 → 0 | 0 → 0 | 67.6% / 67.6% |
| Import dialog (modal) | 1024×700 | False | 0 → 0 | 0 → 0 | 0 → 0 | 70.1% / 70.1% |
| Import dialog (modal) | 512×350 | False | 0 → 0 | 0 → 0 | 0 → 0 | 92.3% / 92.3% |

All 512×350 rows page down (100 % = the document continues below the viewport).
That is normal vertical scrolling at 200 % zoom; no screen scrolls sideways and
no control sits past the left or right edge after the fixes. Edit, Clean and
Preview grow from 81.4 % to 94.2 % because the toolbar now takes two rows
instead of overlapping itself.

Full data: `measure-before.json`, `measure-after.json`.

## Fixes

### 1. Toolbar collided with itself at 512×350 (CSS)

`.toolbar-tabs` is absolutely centred. At 512 px its 260 px pill landed on the
left group (home 32 + Import 84 + Search 30) and on the right group (Queue,
Settings): 5 overlaps, `Import` under `Check`/`Edit`, `Search` under `Edit`,
`Render` under the engine/queue buttons. The old rule that was meant to hide
the engine at small widths, `.top-actions .engine-pill`, names a class this
toolbar no longer has, so the engine pill never hid.

Fix: an end-of-file `@media (max-width: 760px)` block makes the bar wrap, makes
the tabs a static centred second row, hides `.toolbar-engine`, and reduces the
traffic-light inset from 78 CSS px to 46 (the inset is measured in window
pixels; at 200 % zoom 78 CSS px is twice the physical space needed). The block
must live at the end of the file: the base `.toolbar-tabs { position: absolute }`
rule comes *after* the first responsive block, so an override there loses.

Evidence: `pc-512x350-check-before.png` / `-after.png`,
`pc-512x350-render-before.png` / `-after.png`.

### 2. Render stayed two columns below 980 px (CSS)

`@media (max-width: 980px)` set every workspace, including `.workspace.render`,
to one column. A later rule, `.workspace.render { grid-template-columns: 320px
minmax(0, 1fr) }`, comes after it and won. At 512×350 the queue column was
146 px: the title wrapped to three lines and the "Queue idle" label was clipped
by the panel.

Fix: a late `@media (max-width: 980px)` restores the single column for the
render workspace; the queue head wraps, its heading may shrink, and its action
group no longer shrinks (`flex: 0 0 auto`).

This one is worth noting: `documentElement.scrollWidth` stayed equal to the
viewport because `body { overflow-x: hidden }`, and the clipped label sits in a
`.btn.small`, which the first version of the detector skipped. The script now
measures icon buttons and `.btn.small`, and reports buttons whose text overflows.

### 3. Frame timecode is text on the Edit bar (JS + CSS)

The Edit player bar now draws `<span class="player-tc" data-player-tc>` beside
the clock, separated by a 1 px rule: `00:12 / 02:40 │ 00:12:07`. Frames come
from `state.edit.source.fps`, then `check.result.meta.fps`, then 30. `playerBar`
takes `{ timecode: true }` and only the Edit screen passes it, so Check, Clean
and the render modal keep their old bar. The old tooltip is replaced by the
visible value with `title="Frame timecode"`.

`.player-time` and `.player-tc` are `flex: 0 0 auto` and `white-space: nowrap`.
The probe measures the real markup at 340 px (the 1024 landscape column) and at
132 px (a 9:16 stage in that column, ~130 px): one line, inside the bar, every
control inside, at both widths. At 132 px a `@container (max-width: 300px)` rule
wraps the bar and hides the volume slider; the timecode stays a single short
line. Measured values: `probe340` and `probe132` in `measure-after.json`.

Evidence: `pc-edit-bar-widths.png` (391, 340 and 132 px cards with the real bar).

### 4. 1440×900 and 1280×800 are unchanged

A pixel diff of the before/after shots shows 0 changed pixels on Edit, Clean,
Preview and Import; Check differs only below the noise floor (JPEG antialiasing);
Welcome, Render and Settings differ only in the live disk-free numbers
(`1.95 GB free`, storage rows). No geometry moved.

## Screens not reached (need footage — founder hand test)

- the story media player and the story beat timeline;
- render playback (needs a finished render);
- Edit with a loaded video: player bar, inspector, timeline lanes, transcript;
- Clean with layers and real before/after frames;
- Preview sequence and safe zones on a Cut frame;
- copying a transcript line to the real clipboard.

Suggested hand steps for the PO:

1. Open a 9:16 portrait project in a 1024×700 window. Edit: play, scrub, check
   the bar wraps instead of pushing the timecode out of the card; check the
   timeline, inspector tabs and transcript.
2. Same project at 1440×900 and 1280×800: the bar is one line.
3. If the web view exposes zoom, set 200 % and repeat on Welcome, Check, Render,
   Settings and Import.
4. Open Preview, play the sequence, then a finished render; play/pause/seek and
   the transcript menu copy.

## Tests

- `python3 -m pytest -q tests` → 397 passed, 2 skipped (5 warnings from torch).
- `node --check static/duck/app.js` → clean.
- `tests/test_layout_small.py` (5 tests) pins: the Edit-only timecode markup and
  paint, one-line CSS, the cascade order of both media overrides, the container
  wrap, and the measurement script's sizes and probes.

## Files

`static/duck/app.css`, `static/duck/app.js`, `scripts/measure-layout.mjs`,
`tests/test_layout_small.py`, this folder.
