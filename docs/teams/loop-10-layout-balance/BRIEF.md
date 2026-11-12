# Loop 10 — layout balance (PLAN.md loop 9)

Senior PO brief, 2026-11-12. Source: `docs/teams/uiux-balance-01.md` (read it; proposals P1–P4).
The founder tests the whole app by hand right after this loop, so this is the layout they judge.
Run with your own PO, engineer, tester and creator. Do not report between steps.

## Why

The flows work; the page weight does not. Render ends at 60 % of the window, the inspector clips a
row with no hint, three empty timeline lanes read as missing data, and a 9:16 project leaves paper
each side of the player.

## Build

1. **Render: two columns.** Settings (320 px) with `Start render` under it on the left; the queue
   full width on the right, rows 56 px; finished renders as cards under the queue. The estimate
   lives in the left column: "Measuring the fill… N %", then the range, then the leftover-check
   line with "N lines not checked" when there are any. Nothing in the left column scrolls at
   1280×800.
2. **Inspector.** `5 of 9 layers` in the list head and a 24 px fade at the bottom of the scroll
   area. The fade goes away at the end of the list.
3. **Timeline.** A lane with no cues is one 32 px row with a `+`; a lane with cues keeps its
   height. Adding the first cue opens the lane.
4. **Portrait Preview.** For a portrait source the scene strip is a 300 px column beside the
   player. Landscape is unchanged.
5. **Settings.** The fill model folder row from loop 8 sits with the other model rows, same
   height, same buttons, with its state in one line (in use / not usable + reason / none).

## Acceptance (measure, do not eyeball)

Measure with headless Chrome against the local core, the way `uiux-balance-01.md` did, on
`prj_e95348a97316` (9:16) at **1440×900 and 1280×800**. Give the numbers in the review.

1. No screen's content ends above 85 % of the window height: Welcome, Check, Edit, Clean Focus,
   Preview, Render. State the percentage per screen and size.
2. No text overlaps an image or another text: zero intersecting boxes among visible labels,
   thumbnails and buttons, by a script, per screen and size.
3. Every scrollable list shows a count or a fade.
4. The 9:16 project uses at least 60 % of the main column width in Preview.
5. No horizontal scrollbar and no clipped button label at 1280×800.
6. Before and after captures of every screen at both sizes in this folder, as JPEG under 300 KB
   each. No capture shows a model name.
7. No new mode, no new step, no token change (type scale, palette, density stay).
8. A landscape project is not worse: the same measures on a 16:9 project. Use a project that
   already exists in the data root only if the founder's review project is the only one there;
   otherwise do not open other projects — build the 16:9 case from the test fixtures.
9. `python3 -m pytest -q tests`, `node --check static/duck/app.js` and
   `./scripts/build-xcode-dev.sh` pass. No fill output change; `textfill.VERSION` untouched.

## Rules

- Local only. No model name in the UI. Do not hide a limit: the range, the "not checked" count and
  the `moves` flag stay visible in the new layout.
- Never read or search `old_memory.md`, `old_todo.md`, `old_plan.md`. Never read the two HTML
  reports; insert a row with a script that prints nothing.
- Do not Check, render or edit the founder's project; read it and screenshot it. Do not click in
  the app window; the founder does that after this loop.
- Never merge `main`. No App Store work.

## Done

`docs/teams/loop-10-layout-balance/review.md` (verdict, each acceptance item with its number, what
was not tested), `founder-test.md` here: one click-by-click script for the **whole app** in the
new layout — import, Check, Clean, Edit, Preview, Render, the fill model folder, "Measuring the
fill…", the "not checked" count — with what must be seen at each step. `MEMORY.md`, `TODO.md`,
`PLAN.md`, `PRODUCT.md`, `CLAUDE.md` current; report row; one commit, pushed to `ducksuite`.

Reply once: each acceptance item pass or fail with its number, what got worse, what was not
tested, the commit hash.

## Revision 1 (Senior PO, 2026-11-12) — after looking at the captures of `6132d75`

9 of 9 "pass" by the script; not by the eye. The founder will see these in the first minute. The
measure was bent in two places: the 60 % rule was met by a black stage, not by the picture, and
the overlap script excludes the one overlap that hides controls. Fix the screens, then fix the
script so it would have caught them.

1. **Preview, 9:16** (`after-preview-1440x900.jpg`). The stage is 734 × 410 px black with a
   picture about 215 px wide in it, and about 425 px of empty paper under it. The player ends at
   53 % of the window.
   - Measure the **picture** (the video's displayed rectangle, from `videoWidth/videoHeight` and
     the element box), never the stage.
   - The picture's height is at least 80 % of the column height available under the top bar, at
     both sizes. The stage hugs the picture: at most 24 px of black on each side.
   - Nothing but the page margin is empty below the player column.
2. **Edit, 9:16** (`after-edit-1280x800.jpg`). Same rule for the stage: about 170 px of black each
   side of the picture today. Hug the picture and give the width back to the panels beside it, or
   say in the review why the stage must be wider and by how much.
3. **Edit: the transcript box covers the player's controls.** The play button and the scrub bar
   sit under "TRANSCRIPT · 1 line in this scene". Zero intersection between that box and any
   player control, and every control clickable (`elementFromPoint` at its centre returns the
   control). Remove this pair from the script's exclusions.
4. **Edit: scenes panel.** The filter field runs into the panel's right edge and its label sits
   outside the padding; the scene rows carry a dark 2 px box unlike any other list in the app.
   Left and right inner padding equal within 1 px, measured; rows use the same hairline row style
   as the Render queue.
5. **Edit: the inspector cuts a sentence at its bottom edge** ("Apple GPU. Measured 4.6× …") with
   no fade and no count in view. Every scroll area on every screen shows the fade while more is
   below, including the inspector body, the scenes list (row 07 is cut) and Preview's scene strip
   (the fourth thumbnail is cut). Probe each one, real content, no forced height.
6. **The overlap script.** List every exclusion in the review with one crop that shows why it is
   designed. An exclusion without a crop is removed. Add two measures to the script and the
   tables: picture share of the column (items 1–2) and "text cut by a container edge" (item 5):
   count of visible text boxes that cross their scroll parent's bottom edge without a fade.
7. Render is accepted as it is. Do not rework it.

Accept: the three new measures are 0 / ≥ 80 % at 1440×900 and 1280×800, portrait and the 16:9
fixture; all earlier items still pass; new `after-*` captures replace the old ones and you have
looked at each one; `founder-test.md` matches the new screens. Tests, `node --check`, the Xcode
build pass; `textfill.VERSION` 17. "Revision 1" on top of `review.md`. One commit, pushed.
