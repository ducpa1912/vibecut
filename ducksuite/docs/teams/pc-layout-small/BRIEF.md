# P-C · Layout at small sizes (loop 28, REQ-20261115-02 P2)

Owner: **OpenCode**. Folder `drop_eval/ducksuite-opencode`, branch `oc/pc-layout-small`, port 8821,
data root `build/scratch-root` in that folder. Read `AGENTS.md` → "Three agents" first.
In this loop you own `static/duck/app.js` and `static/duck/*.css`. Nobody else touches them.

## Why
The window was only ever measured at 1440×900 and 1280×800. A $29 buyer on a 13-inch MacBook Air
with a smaller window, or with zoom turned up, may hit overlaps, cut-off buttons or a page that
scrolls sideways.

## What to do
1. **Measure.** Check every screen you can reach without footage at 1024×700, 1280×800 and
   1440×900, and at 200 % zoom (1024×700 with `deviceScaleFactor` 1 and CSS zoom 2, or a 512×350
   viewport). That's at least the home/projects screen, Settings, Setup → Engines, the import
   dialog, an empty project and the render queue. For each one, record:
   - horizontal scroll (`document.documentElement.scrollWidth > innerWidth`);
   - elements overlapping (bounding boxes of buttons, inputs and headings intersect);
   - text cut off (`scrollWidth > clientWidth` on buttons and labels);
   - controls pushed off screen.
   Write it as a table in the review, one row per screen and size.
2. **Fix** what you found in CSS first, then `app.js` markup if CSS can't do it. Keep the 1440×900
   and 1280×800 layouts unchanged: take screenshots before and after at those sizes and compare
   them.
3. **Frame timecode.** Show the frame timecode beside the time on the Edit bar. Today it's only a
   tooltip (`98e1edf`). Keep it to one short line, and make sure it doesn't wrap at 1024×700.
4. **Tests.** Add `tests/test_layout_small.py`. Pick the form you can keep stable: run the
   measurement script under headless Chrome when Chrome is present and skip when it isn't, or
   check the CSS rules by string, like `tests/test_ui_actions.py` does. The measurement script
   itself goes in `scripts/measure-layout.mjs` (or `.py`).
5. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.

## Not in this loop
These need real footage, so they move to the founder's hand test:
- the story media player;
- render playback;
- the Edit screen with a loaded video;
- copying from the transcript menu to the real clipboard.
Don't make or download video. List which screens you couldn't reach without footage, so the PO
can write the founder's steps.

## Rules
Commit on `oc/pc-layout-small` with `git -c commit.gpgsign=false commit`. Don't push or merge.
Don't edit `MEMORY.md`, `TODO.md`, `PLAN.md` or `PRODUCT.md`. Don't open the app. Never read the
Containers data root or founder projects. Put the screenshots in `docs/teams/pc-layout-small/`
(PNG, scratch data only) and write `review.md`.
