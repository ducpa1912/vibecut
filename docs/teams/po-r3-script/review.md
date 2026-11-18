# R3 product-owner review — Script Focus

**Verdict: PASS** for the founder acceptance test after three fix loops.

## Round 1 findings (FAIL)

| Finding | Fix |
|---|---|
| P0: twin Cues/Script lists drifted out of register — clicking cue #10 seeked to 28 s but the editor stayed at `scrollTop 0` | The duplicate Cues pane is gone; one Script editor row per cue, so there is no second scroll to fall out of step. |
| P0: fixed 310 px grid + 1100 px breakpoint — grid 2665 px at 1024/800/200 %, rail 2330 px below the first row | Grid height is viewport-derived per height tier; the rail stays beside the editor at every width down to 720 px and scrolls inside itself. |
| P1: no "current line" — `.is-current` was an elapsed trail (31 rows lit), playback did not advance it | Current row is exactly one row by `start ≤ t < end`; a seek scrolls it into view. |
| P1: "what will be captioned" unanswerable — burn toggle below the rail fold | Summary line: `47 lines · 00:00:00:00–00:02:39:14 of 00:02:40:00 · Burn captions · SRT only`, with the burn checkbox in it. |
| P1: Translate/Rewrite/Reset overwrote all 47 lines with no confirm, inputs live during the job | Confirm dialog states the line count and that hand edits are replaced; inputs and the three controls disable while busy. |
| P1: transcript panel contradicted the script on the same screen | The transcript panel is hidden in Script Focus. |

## Round 2 findings (NOT PASS)

| Finding | Fix |
|---|---|
| P1: dock exceeded the viewport, 113 px clipped at 1440, three nested scrollers | Dock and dock body no longer own a scroller; only the list and the rail scroll. Page height equals the viewport at all five sizes. |
| P1: no seek control in Script Focus | Every row timecode is a seek button (`[data-action="script-seek"]`, 47 of them); it seeks and scrolls the exact current row into view. |
| P1: preview card painted over the Script Focus card at 769–1200 px width | Focus mode clips the preview block and sizes the card inside a size container. |

## Round 3 findings (PASS)

| Finding | Fix |
|---|---|
| P1: at 800×600 the card measured 198×150 (1.32:1) with the frame cropped — `max-width` won over `height:100%; width:auto` | Card `width: min(100cqw, calc(100cqh * var(--media-ratio)))`, `height:auto`, `min-height:0`, ratio kept, `object-fit: contain` backstop. Measured 198×111 = 1.784. |
| P2: the guard asserted neither `object-fit` nor a visible-row floor | Both are now part of the failure test, with a per-viewport row floor. |

## Measured after fix

| Viewport | doc / vh | Card | Ratio error | fit | overlap | Visible rows | Seek |
|---|---|---|---:|---|---:|---:|---|
| 800×600 | 600 / 600 | 198×111 | 0.0002 | contain | 0 | 3 | 1 current, in view |
| 1024×700 | 700 / 700 | 263×148 | 0.0002 | contain | 0 | 5 | 1 current, in view |
| 1100×800 | 800 / 800 | 316×178 | 0.0001 | contain | 0 | 6 | 1 current, in view |
| 1200×800 | 800 / 800 | 316×178 | 0.0001 | contain | 0 | 6 | 1 current, in view |
| 1280×800 | 800 / 800 | 316×178 | 0.0001 | contain | 0 | 6 | 1 current, in view |
| 1440×900 | 900 / 900 | 494×278 | 0.0001 | contain | 0 | 6 | 1 current, in view |
| 200 % (720×450) | 450 / 450 | hidden | — | — | 0 | 3 | 1 current, in view |

No horizontal overflow at any size. `346 tests` pass; `node --check` clean on `app.js` and the guard.

## Regression guard

`scripts/check-script-focus-layout.cjs` fails (exit 1) on preview/dock overlap, page scroll, horizontal
overflow, card aspect error > 0.02, media `object-fit` other than `contain`, visible rows under the
per-viewport floor, or a seek that leaves zero or several current rows or scrolls the row out of view.
It needs a live dev server and `NODE_PATH="$(npm root -g)"`; without puppeteer-core it exits 2 with that
instruction.

```
NODE_PATH="$(npm root -g)" node scripts/check-script-focus-layout.cjs \
  --base "http://127.0.0.1:8813/?t=scratch-3a" --project prj_e95348a97316 --out build/po-r3
```

## Limits kept in the open

- At 200 % the preview workspace is hidden on purpose; only the editor and rail show, 3 rows.
- 3 rows visible at 800×600 and 200 %; the rail scrolls at every size.
- No proof rendered on this scratch project; no VoiceOver pass; no real founder click-through.
- Layout checks are headless Chromium, not the WKWebView shell.
