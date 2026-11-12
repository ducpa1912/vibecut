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
