# R1 product-owner review — Edit desk + Clean inspector

**Verdict: PASS for the founder acceptance test** after one fix loop.

## PO findings and fixes

| Finding | Fix |
|---|---|
| P0: Fill/Blur/Off below the fold in Edit Clean, no cue | Layer list, then the clean choice directly beneath it; a missing-engine warning sits beside the choice. At 800/1024/1440/1280 the choice is inside the body. |
| P0: Clean Focus showed the uncleaned source under an **After** tag | No proof → tag **Source · no proof yet**; compare right tag **No proof yet**; proof thumb says **Not cleaned yet**. |
| P1: Before/After thumbnails identical | Right thumb carries the **Not cleaned yet** badge until a proof exists. |
| P1: brush canvas taller than the window, toolbar off-screen | `.brush-stage` capped at `calc(100vh - 220px)`; opening brush scrolls to top. Toolbar at 651–737 in a 900 px window. |
| P1: page scroll at 1024/800 | Short-window layout: workspace and timeline shrink; the timeline scrolls inside its own panel; document = viewport at 800 and 1024. |
| P1: Fill selected while engine reads missing | Amber line beside Fill/Blur/Off: “AI fill is missing, so Fill will not run. Set up”. |
| P2: empty transcript box shows an Opacity slider | Opacity row is hidden when there is no cue. |

## Measured after fix

| Viewport | Choice | Body | Document / viewport | Timeline |
|---|---|---:|---|---|
| 1440×900 | 476–512 | ends 605 | 900 / 900 | normal |
| 1280×800 | 481–509 | — | 800 / 800 | panel 560–760, scrolls (198/226) |
| 1024×700 | 361–397 | ends 501 | 700 / 700 | internal scroll |
| 800×600 | 361–397 | ends 401 | 600 / 600 | panel 416–556, scrolls (138/255) |
| 200 % (720×450) | 361–397 | ends 401 | 540 / 450 (90 px page scroll) | reachable |

Clean Focus tag: **Source · no proof yet**; caption **After · no proof yet**. Brush toolbar inside the viewport. `346 tests`, `node --check` clean.

## What got worse

- At 800/200 % the preview column is ~130 px and the empty transcript message wraps 1–2 words per line.
- Timeline scroll folds can show half-clipped rows.
- 200 % still has a 90 px page scroll; choice remains reachable.

## Not tested

- Real founder click-through; VoiceOver; a proof rendered on this scratch project.
