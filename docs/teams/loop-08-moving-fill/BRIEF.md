# Loop 8 — a better fill for moving footage (PLAN.md loop 5)

Senior PO brief, 2026-11-11. Start only after loop 7 is committed and its review is written.
Run with your own PO, researcher, engineer and tester. Do not report between loops.

## State on restart (2026-11-12) — read this first

The Senior PO stopped this loop once, reviewed loop 7 and rebuilt it (commit `8d1a9c8`). Read
`docs/teams/loop-07-ink-check/review.md`, revision 2, before any code. What changed under you:

- `duckcore/ink.py` and `duckcore/inkcheck.py` are rewritten. The fill hole is each letter's
  strokes grown 6 px, only on the frames that letter is on screen (`TextMasks(strokes=, base=)`,
  `prepare_span(..., strokes=)`). `span_key` holds `ink_rect` and `ink_key`.
- `textfill.VERSION` is 17. 155 tests pass. A cold render of the review project takes 698 s.
- No fill is carried across a frame where something crosses the text (`_picture_moved`,
  `crossed`). Do not undo this.
- Your unfinished custom-fill work from the first start is on local branch `loop8-wip` (commit
  `f87730e`). It predates all of the above. Do not merge or rebase it. Read its diff, then write
  the slot again by hand on `ducksuite`, on top of the new `prepare_span`.
- Never read or search `old_memory.md`, `old_todo.md`, `old_plan.md`. Never read
  `docs/reports/SESSION.html` or `docs/reports/ducksuite-product-progress.html`; only insert a row
  with a script that prints nothing.
- Also open in `TODO.md` and in scope here if cheap: the render estimate does not count the extra
  fills at crossings. Measure it against a real cold render and fix the estimate, or record the gap.

## Why

34 of 42 clean layers on the review project are `moving`. LaMa fills one frame at a time and
guesses structure (see `docs/teams/loop-07-ink-check/bad-fill-150s.jpg`). Loop 7 made the hole
small and added the flicker number; this loop asks whether another engine beats LaMa on what is
left.

## Build

1. **Researcher first.** One table in `docs/duck/moving-fill-licences.md`: each video-inpaint
   candidate (STTN weights, ProPainter, E2FGVI, any other found), licence of the code, licence of
   the weights, the quoted clause, the URL, commercial use yes / no / unclear. "Unclear" counts as
   no. No model enters the build, the repo or this Mac's bundle without a yes row.
2. **Bench only the yes rows** with `scripts/bench_fill.py` on the moving spans of
   `prj_e95348a97316`, GPU, with loop 7's ink holes: PSNR on a text-free reference (burn a known
   caption onto clean footage from the same video, then remove it), the loop 7 flicker number,
   seconds per output second, peak memory. Peak memory must stay under 8 GB on this Mac.
3. **The path that needs no licence:** a custom fill slot. The user points the app at a local
   ONNX or TorchScript fill model folder; the app loads it in place of LaMa. No model name in the
   UI. The model is never downloaded by the app and never committed. Its stamp goes in `span_key`.
4. Decide from the table. Either a candidate ships as an optional user-supplied model through the
   slot, or the doc records that none wins and the `moves` warning stays.

## Acceptance

1. The licence table exists, every row has a quoted clause and a URL.
2. The bench table exists, measured on this Mac, with the four numbers for LaMa and each allowed
   candidate. If no candidate is allowed, the table holds LaMa alone and says so.
3. A stated verdict: "candidate X beats LaMa by N dB and M flicker at T× the time", or "none does".
4. The custom fill slot loads a user folder, falls back to LaMa with a plain message when the
   folder is wrong, and is covered by a test with a stub model.
5. No weights are added to git, to the bundle or to any pack. `git diff --stat` shows no file over
   1 MB.
6. If fill output changes for a default user: `textfill.VERSION` bump and a cold-render warning.
   If it does not, say so.
7. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.

## Rules

Same as loop 7's brief. In addition: downloading a candidate to a scratch folder outside the repo
for the bench is allowed only for a yes row; delete it after the bench and say so in the review.
Never ship NLLB. Write `docs/teams/loop-08-moving-fill/review.md`.

## Revision 1 (Senior PO, 2026-11-12) — after review of `7bda48d`

Loop 8 passed its own items; these three faults are left. Fix them in one commit.

1. **The estimate is 31 % low** (483.5 s against a measured 698 s cold render of
   `ed_38a4c36a3aae`). Crossings added 11.7 s, so they are not the cause. The cause is that the
   estimate plans box runs while the fill runs per-letter stroke holes.
   - Build the estimate from the same run plan the fill executes: one function, called by both.
     No constant fitted to this project, no multiplier.
   - Proof per span, not per total: a table of estimated against real seconds for every filled span
     of the review project. Take the real seconds from the `fill span ... seconds=` log lines; if
     the log of render `20261112-024716` is gone, run one cold render on GPU and do not stop it
     mid-clip.
   - Accept: total within 15 % of the real cold render, and no span off by more than 2× unless the
     review names it and says why. If 15 % cannot be reached, show the measured gap in the UI
     beside the estimate; do not hide it.
2. **A custom model teaches the LaMa speed.** `prepare_span` stores the frame rate of a user model
   under `lama`, so later estimates for the default engine drift. Keep a separate rate for the
   custom engine, keyed by its stamp, or do not learn from it. Test: a slow stub model leaves the
   default estimate unchanged.
3. **Estimate and render can disagree on the key.** `estimate_span` uses `custom_fill_path` even
   when the model would fail to load; `prepare_span` then falls back. Make both take the same
   decision. Test it.

Also write `docs/teams/loop-08-moving-fill/founder-test.md`: a click-by-click script for the
founder to try the fill model folder in the built app (pick a folder, a wrong folder, clear it),
with what must be seen at each step. The founder runs it; do not run the app yourself.

No fill output change is expected. If one happens, bump `textfill.VERSION` and say the next render
is cold. Add a "Revision 1" section on top of `review.md`.

## Revision 2 (Senior PO, 2026-11-12) — after review of `85482ac`

The estimate is right now (6.7 % low) and too slow: 66.7 s on the first call, 24 s on every later
call, inside the request at `duckcore/main.py:1767`, and again in the render queue before each
render. The user sees nothing while it runs.

1. **Build the ink once.** `inkcheck.build_inks` is run by the estimate, by the queue's estimate
   and by the render. Store its result on disk, keyed by the source file stamp, the layer boxes
   and ranges, and a version constant of `ink.py`; the estimate, the queue and the render read the
   same store. A changed layer rebuilds only that layer. Test: second call reads no frame.
2. **The dry run is paid once.** A span whose units are stored must not decode. An edit with one
   changed layer re-plans only the spans that layer touches. Test it.
3. **The request does not block.** The estimate endpoint answers at once with what is stored and a
   state: `ready`, or `working` with progress 0–1. The work runs in one background worker; a
   second request joins it, it does not start a second one. A render that starts while it works
   waits for it or takes over its result; it does not repeat it.
4. **The UI says it.** While `working`: "Measuring the fill…" with the progress, and the last
   known figure marked as old if there is one. No model name. When the fill speed is unknown or
   varies, show the figure as a range: this Mac rendered the same edit cold in 620.6 s and
   847.2 s, so one number hides a limit.
5. **Do not let the estimate hold the fill lock or the GPU** while a render runs.

Accept, measured on `prj_e95348a97316` in the built app's server, not in a test double:

- Warm call (nothing changed): under 1 s. State the number.
- First call ever: the request returns under 1 s; the background work's wall clock is stated.
- One layer's range changed: stated, and less than a third of the cold figure.
- Queue to first fill frame: no second ink build; state the seconds before and after.
- The estimate's total for the unchanged edit equals the figure of `85482ac` (790.4 s at the same
  stored rate), so speed did not cost accuracy.
- No fill output change, `textfill.VERSION` stays 17. If it must change, stop and say why.
- Tests, `node --check`, `./scripts/build-xcode-dev.sh` pass.

Do not open the app window or click in it; the founder does that. Add a step to
`founder-test.md` for the "Measuring the fill…" line. "Revision 2" section on top of `review.md`,
one commit with `MEMORY.md`, `TODO.md`, the test counts and the scripted report row, pushed.

## Revision 3 (Senior PO, 2026-11-12) — after review of `9f1bb32`

Revision 2 made the estimate fast and broke the thing it stores. Fix A first; it is a correctness
fault. One commit for A–C, one for D–E.

**A. The ink store loses the letters.** `inkcheck._save_ink` writes `mask, rect, first, last, fps`.
`ink.Ink` also has `settled`, `glyphs` and `spans`. A line read back from the store has no letter
spans, so `Ink.pieces()` returns one whole-line hole, `Ink.reach` falls back to the line, and the
check judges the line as one letter. The first render of a project (store empty) and every later
one (store warm) therefore fill different holes under different `ink_key`s, and the warm one loses
the per-letter check that loop 7 revision 2 exists for. The 44 files now on this Mac prove it: no
`glyphs`, no `spans`.

- Store every field of `Ink`. Bump `ink.STORE_VERSION`. An old or unreadable file (catch
  `zipfile.BadZipFile` too) is rebuilt, not trusted.
- Test: for a line with two letters that end on different frames, `pieces()`, `reach`, `settled`
  and the layer's `ink_key` are equal before and after a round trip through the store.
- Test: a new field added to `Ink` without the store knowing fails a test (compare
  `dataclasses.fields(Ink)` with what the store writes).
- Proof on `prj_e95348a97316`: every layer's `ink_key` with an empty store equals the key with a
  warm store, 42 of 42. Then one render with the warm store: 0 leftover, 40 of 42 lines checked,
  the same as `20261112-024716`. If its fill cache is warm from the earlier cold renders, say so and
  give the count of spans reused; it must be all of them.
- Delete the fill cache files written by the render you started in revision 2 with the letterless
  store, if you can tell them by key; say how many. Cap the ink store (oldest files out past a
  stated size).

**B. The estimate worker can die.** `estimate_status` trims `_ESTIMATE_JOBS` to the last 8 and can
remove a job that is still working; the worker then raises `KeyError` outside its `try`, the thread
ends, and `wait_for_estimate` waits 900 s. Never trim a working job; the worker must survive any
error. Test both.

**C. The estimate key ignores what changes the answer.** `_estimate_key` has `"fill_device": None`
and no fill model. Key it by the same layer fields as the ink store, the chosen device and
`engine_choice`'s stamp. Test: setting a fill model folder makes the stored estimate stale.

**D. What got worse since loop 6, measured, with no output change.** Cold render 418 s → 620–847 s;
leftover check 21–37 s → 60–70 s; first estimate of a project 144.8 s. Profile one cold render and
one check on the review project and write the table: seconds per stage (decode, ink build, dry
run, fill runs, paste, encode, check decode, check judge). Then take every win that does not
change a pixel: frames decoded twice, a source read at full size where a crop serves, work the
estimate already did that the render repeats. State before and after per stage. A win that needs a
fill output change is listed with its expected gain and **not** built. `textfill.VERSION` stays 17.

**E. The 48 filled letter-frames that still show strokes** (loop 7 revision 2, TODO). Save crops of
six of them, source beside output, in this folder. Say what they are: outline residue, a shadow, or
the fill redrawing an edge. No code unless it is a hole that is too small, and then say what
`GROW_PX` would cost in pixel-frames before changing it.

Reply once: A–E pass or fail with the numbers, what got worse, what was not tested, commits.
"Revision 3" section on top of `review.md`; `MEMORY.md`, `TODO.md`, test counts, report row.
