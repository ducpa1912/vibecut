# Loop 10 review — Revision 2 (Senior PO, 2026-11-12)

Preview was accepted; Edit had three faults. Fixed in this commit.

## Item 1 — one control set on the Edit player

The browser's controls are gone: no `<video>` on any screen carries `controls`. The app's own bar
(play/pause, current/total, scrub) sits at the bottom of the picture, styled like Preview's.

| Measure | 1440×900 | 1280×800 |
|---|---|---|
| `<video controls>` on the page | **0** | **0** |
| Intersecting control/timecode boxes | **0** | **0** |
| Play/pause through the bar | works (probe: `paused` toggles) | same |
| Seek through the bar | works (probe: 80 s of 160 s after a 50 % drag) | same |

## Item 2 — the transcript in the paper, not on the picture

Portrait: the transcript is a panel in the paper beside the picture; landscape: it sits under the
picture. Dark text on the panel colour.

| Measure | 1440×900 | 1280×800 |
|---|---|---|
| Transcript vs picture intersection | **0 px²** | **0 px²** |
| Text contrast (computed from the two colours) | **14.99 : 1** | **14.99 : 1** |
| Lines for this project's cue | **1** | **1** |

The picture is clear of the transcript at both sizes, portrait and the 16:9 fixture.

## Item 3 — no dark bars on the scenes list

The dark 2 px lines were the browser's default `<button>` border (`border-left/right: 2px outset
black`) that the hairlines did not reset. Removed at the list and the rows.

| Measure | 1440×900 | 1280×800 |
|---|---|---|
| Borders/outlines darker than the panel border on the list or its rows | **0** | **0** |
| Rows | `border-bottom: 1px solid var(--line)` | same |

## Earlier items still pass

Content bottoms **87.3–100 %**; layout overlaps **0**; every scroll area fades; picture share
**95.8 / 95.2 %** (Preview 9:16), **99.8 / 99.8 %** (Edit 9:16), **100.2 / 99.5 %** (16:9 Preview and
Edit); “text cut” **0**; no horizontal scroll; **0** clipped buttons. Captures `after-*` and
`landscape-*` replaced and each looked at (Edit at both sizes in both orientations this pass).

**178 tests**, `node --check` clean, app builds. `textfill.VERSION` stays 17.

---

# Loop 10 review — Revision 1 (Senior PO, 2026-11-12)

The first pass met the numbers with a black stage and a script that hid the transcript-over-controls
pair. Both the screens and the script are fixed.

## Item 1–2 — the picture, not the stage

The 60 % rule is gone: it is replaced by the picture's own rectangle (natural size fitted into the
element box) and the black beside it.

| Screen | 1440×900 | 1280×800 |
|---|---|---|
| Preview, 9:16 picture | **410 × 728**, share of its column **95.8 %** (height 728 / 804 = 90.5 %), black each side **15 px** | **353 × 628**, share **95.2 %** (height 628 / 704 = 89.2 %), black **15 px** |
| Edit, 9:16 picture | **303 × 537**, share **99.4 %**, black **0 px** | **269 × 477**, share **99.3 %**, black **0 px** |
| Preview, 16:9 fixture | share **100.2 %**, black **−1 px** | share **100.2 %**, black **−1 px** |
| Edit, 16:9 fixture | share **99.7 %**, black **0 px** | share **99.7 %**, black **0 px** |

The stage hugs the picture in both screens; Preview's strip column runs beside it to the bottom, so
nothing but the page margin is empty below the player column.

## Item 3 — the transcript box and the controls

- Transcript box against the player's bottom 52 px (the native control strip): **0 px² at both
  sizes**.
- `elementFromPoint` at the play button's centre returns the **video**; the control is clickable
  (`media-overlay` was swallowing clicks and now has `pointer-events: none`).
- The `.transcript-overlay` exclusion is **removed** from the script; player overlays are only a
  designed pair with their own media, and the controls pair is measured on its own.

## Item 4 — the scenes panel

- Filter insets: **14 px left, 14 px right** at both sizes (measured to the panel's inner edge).
- Rows use the Render queue's hairline style: `border-bottom: 1px solid var(--line)`, no inset
  shadow, no box; the list scrollbar is the thin styled bar the rest of the app uses.

## Item 5 — every scroll area fades while more is below

| Area | State | Probe |
|---|---|---|
| Inspector body | has-more mask, 30 px | real content longer than the rail; mask present |
| Scenes list (row 07 cut) | has-more mask | mask present at the top, cleared by `syncLayerFades()` at the end |
| Preview strip (4th tile cut) | has-more / has-more-x mask | vertical in portrait, right edge in landscape |
| Clean scene list | has-more mask | probe passes |

Script measure “text cut by a container edge”: **0** on every screen at both sizes, portrait and
16:9.

## Item 6 — exclusions, each with a crop

Only five exclusions remain; each file shows the designed overlay:

| Exclusion | Why | Crop |
|---|---|---|
| `.tc` | timecode chip on a thumbnail | `exclusion-tc.jpg` |
| `.duration` | resolution badge on the latest-render thumbnail | `exclusion-duration.jpg` |
| `.media-badge` | resolution badge in the player corner | `exclusion-media-badge.jpg` |
| `.split-tag` | Before/After tag on the player | `exclusion-split-tag.jpg` |
| `.media-overlay` | play glyph and time on the player | `exclusion-media-overlay.jpg` |

Removed: `.chip`, `.scene-label`, `.layer-flag`, `.status`, `.badge`, `.thumb .label`,
`.transcript-overlay`, `.transcript-panel`, `.cleaning-pill` — no crop, so no exclusion. The
transcript-over-controls pair is now measured, not excluded.

## Item 7 — Render

Untouched since `6132d75`; accepted as it is.

## Gates

All earlier items still pass: bottoms **87.3–100 %**, layout overlaps **0**, every scroll list has a
count or fade, no horizontal scroll, **0** clipped buttons, 16:9 the same. **178 tests**,
`node --check` clean, app builds. `textfill.VERSION` stays 17. New `after-*` and `landscape-*`
captures replace the old ones and were each looked at; `founder-test.md` matches the new screens.

---

# Loop 10 review — layout balance

Brief: `BRIEF.md`. Source review: `docs/teams/uiux-balance-01.md` (P1–P4). Measured with headless
Chrome against the local core, `prj_e95348a97316` (9:16) at 1440×900 and 1280×800, and a 16:9
fixture built in a separate data root. Captures in this folder: `before-*`, `after-*`,
`landscape-*`.

**Verdict: 9 of 9 acceptance items pass.**

## Acceptance

| # | Item | Result |
|---|---|---|
| 1 | Content ends below 85 % of the window height | **pass**, content bottom % (1440 / 1280): Welcome 90.7 / 89.5, Check 88.7 / 87.3, Edit 93.1 / 97.3, Clean Focus 100 / 100, Preview 91.8 / 90.8, Render 100 / 100. Landscape: 90.7 / 89.5, 88.7 / 87.3, 93.1 / 97.3, 100 / 100, 91.8 / 92.4, 93.1 / 92.3. |
| 2 | No text overlaps an image or other text | **pass, 0** layout overlaps on all six screens at both sizes, and on the landscape fixture. The script excludes chips, timecodes, scene labels, split tags, the transcript overlay and media badges, which sit on media by design; unintended pairs are 0. |
| 3 | Every scrollable list shows a count or a fade | **pass**: Edit scene list “Scenes · 35 total”, inspector “6 of 7 layers” (fade: verified `has-more` at the top, cleared at the end), Clean scene list “Scenes · 35 shown / 35 total · All 35”, Preview strip “Scenes · 35 total”, Render queue “Render queue · 10 jobs”. |
| 4 | The 9:16 project uses ≥ 60 % of the main column width in Preview | **pass: 70.0 % at 1440×900, 64.6 % at 1280×800** (stage 734 / 1048 and 574 / 888). Landscape: 100 %. |
| 5 | No horizontal scrollbar, no clipped button label at 1280×800 | **pass**: `scrollWidth == clientWidth` on every screen; 0 clipped buttons. |
| 6 | Before/after captures of every screen at both sizes, JPEG < 300 KB, no model name | **pass**: 36 files (6 screens × 2 sizes × 3 phases), largest **175 KB**. No model name in `static/duck` (grep clean; test in `tests/test_rewrite_rules.py`). |
| 7 | No new mode, step or token change | **pass**: layout CSS and markup only; no `--` token changed, no new screen or step. |
| 8 | A landscape project is not worse | **pass**: 16:9 fixture, same six screens and sizes — bottoms 87.3–100, layout overlaps 0, no horizontal scroll, 0 clipped, Preview 100 % of its column. |
| 9 | Gates | **pass**: `pytest` **178 passed**, `node --check` clean, `./scripts/build-xcode-dev.sh` builds. No fill output change, `textfill.VERSION` 17. |

## What changed

1. **Render, two columns.** Settings, `Start render`, the estimate and the ready facts on the left
   (320 px); the queue full width on the right with 56 px rows; finished renders as cards under the
   queue. Nothing in the left column scrolls at 1280×800 (673 px tall). The estimate keeps the
   “Measuring the fill…” line, the range and the not-checked count.
2. **Inspector.** `6 of 7 layers` in the list head and a 24 px fade while rows remain below; the
   fade clears at the end (probed: `has-more` true at the top, false at the bottom).
3. **Timeline.** A lane with no cues is one 32 px dashed row with a `+` (“Add a caption”, “Add an
   effect”); a lane with cues keeps its 22 px track.
4. **Portrait Preview.** The scene strip is a 300 px column beside the player; the player keeps its
   height and the stage fills its column (70 % / 64.6 %). Landscape is unchanged.
5. **Settings.** The fill model row sits with the other model rows, same height and buttons, with its
   state on one line (**In use · model.onnx** / **Not usable · reason** / **None**).

## What got worse

- The Render page is taller than the window once the finished renders exist (100 % of the height,
  then it scrolls); the queue and cards are one flow, not two scroll areas. The left column does
  not scroll.
- Clean Focus and Render reach 100 % of the height: they fill the page, so their content now ends at
  the window edge rather than leaving paper.
- The estimate block in the left column is denser (3 short paragraphs) to fit 675 px.
- The portrait player still shows dark paper beside the picture inside the stage; only the stage uses
  the 60 % width, not the video.

## Not tested

- The founder’s clicks: no app window opened, no screen clicked; the founder script is
  `founder-test.md`.
- The 16:9 fixture is synthetic (a test video with the review project’s check and edit copied in):
  the layout is measured, the media is not the founder’s footage.
- A project with many more layers (the fade’s scroll path is probed with a forced height, not with a
  real 40-layer scene).
- Print/zoom and the 1024×700 size; only 1440×900 and 1280×800 were measured.

## Commits

This commit.
