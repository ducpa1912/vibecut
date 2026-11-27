# R5 product-owner review — SFX Focus

**Verdict: PASS** for the founder acceptance test after two fix loops.

## Round 1 findings (FAIL)

| Finding | Fix |
|---|---|
| P1: colour filter could not be added, though the copy promised it twice | A seventh control, Colour filter, exists in the dock and the inspector; it opens Warm / Cool / B&W / Vivid with start and end. Measured 4 → 5 effects with toast "Filter added." and a `filter` row in list and lane. |
| P1: no effect was visible before a full render | The player draws an approximate preview at the playhead: text as styled DOM text at its x/y and style size, images/GIFs/stickers/layers from a new `GET /sfx/{id}/file`, colour filters as a CSS filter, with a chip "Effect preview · approximate". |
| P1: timing was write-once, invisible and not in timecode | Every row shows start–end timecode; clicking a row opens an editor with Start/End plus a timecode readout. New `PATCH /sfx/{id}` → `effects.update`. Measured start 5.5 → `00:00:05:12`, toast "Effect updated." |
| P1: rows were inert; only text could be changed | Rows are `role=button`, tabbable, with hover and focus states, and open the editor for their kind: text copy/style/colour/position, media width/position, sound volume. Enter and Space open it (measured focused → Enter → dialog open). |
| P1: the SFX lane could not be read — 9 px blocks in two fixed stacks, 4 overlaps | Blocks are packed into lanes by collision at 12 px with ellipsis labels. Measured at eight sizes: lane 46 px, 4 blocks, 0 overlaps, tallest 43 ≤ lane. |
| P1: add-button labels clipped at every size; dock overflowed the window at 1024/800 | The grid is auto-fit 150 px with nowrap labels; measured clipped buttons 0 at 800/960/1024/1100/1200/1280/1440/200 %. The dock body is capped by height tier and scrolls inside: dock bottom 505/545/548/578/582/582/682/375, page scroll 0. |
| P2: the dock repeated its own six buttons | The list card no longer repeats the add buttons. |
| P2: dock height jumped and left large empty fields | Cards align to the top; the dock hugs its content. |

## Round 2 finding (FAIL)

| Finding | Fix |
|---|---|
| P1: the preview's text size was not the render's — the render scaled every text PNG to 35 % width, a 2.9× miss on the badge | `render._apply_visual_effects` draws text at natural size: the PNG already carries the style's share of the frame height. `tests/test_text_effect_size.py` renders real 320×180 clips and measures the ink: headline 0.055–0.115 of height (target 0.092), badge ≤ 0.075 (target 0.046). |
| P2: preview anchored by centre, render by `(W−w)·x`; rows were tabbable but mouse-only | Preview offsets by `translate(-x·100%, -y·100%)`, which equals the render's free-space formula at any width. Measured 1440: card 494 at x 438, text 196 at x 587 → centre 685 = card centre; top 147 = 67 + (278−29)·0.32. Enter/Space open the row editor. |

## Measured after fix

| Viewport | Lane | Overlaps | Dock bottom | Page scroll | Clipped buttons | Rows = timecodes |
|---|---:|---:|---:|---:|---:|---|
| 800×600 | 46 | 0 | 505 | 0 | 0 | 5 = 5 |
| 960×640 | 46 | 0 | 545 | 0 | 0 | 5 = 5 |
| 1024×700 | 46 | 0 | 548 | 0 | 0 | 5 = 5 |
| 1100×800 | 46 | 0 | 578 | 0 | 0 | 5 = 5 |
| 1200×800 | 46 | 0 | 582 | 0 | 0 | 5 = 5 |
| 1280×800 | 46 | 0 | 582 | 0 | 0 | 5 = 5 |
| 1440×900 | 46 | 0 | 682 | 0 | 0 | 5 = 5 |
| 200 % (720×450) | 46 | 0 | 375 | 0 | 0 | 5 = 5 |

Editor modal: timecode shown, Save/Remove visible at 1440/800/200 % (body scrolls, action row sticks).
Preview overlay stays inside the frame at all eight sizes.

## Render rule measured

`tests/test_text_effect_size.py` (2 tests) renders clips through the real ffmpeg path and measures the text ink height, so a future rescale of text fails the suite. `tests/test_effects_update.py` (3 tests) covers the update route: move and restyle, clamp level and width, reject empty text and a missing id.

## Regression guard

`scripts/check-sfx-focus-layout.cjs` fails on a clipped add label, the dock leaving the viewport, page scroll, horizontal overflow, lane blocks overlapping in one row, lane content overflowing the lane, a missing filter door, row/timecode mismatch, the preview drawing outside the frame, or a hidden Back. Needs a live dev server and `NODE_PATH="$(npm root -g)"`; without puppeteer-core it exits 2 with that instruction.

```
NODE_PATH="$(npm root -g)" node scripts/check-sfx-focus-layout.cjs \
  --base "http://127.0.0.1:8813/?t=scratch-3a" --project prj_e95348a97316 --out build/po-r5
```

## Limits kept in the open

- The preview is approximate: text position and size come from the effect's real style, but badge styling shows as plain bold text in the player while the render draws a dark pill.
- At 800×600 and 200 % the last add row sits below the dock-body fold; effect names in very dense lanes squeeze to ellipsis.
- No full render was run this round; the text-size rule is proven on 1 s synthetic clips.
- Layout checks are headless Chromium, not the WKWebView shell.
