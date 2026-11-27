# Fix 03 review — the estimate queue, and a refill that redraws one clip

**Verdict: pass (tests on synthetic media; no real render was run).** Revision of the estimate
(REQ-20261111-11, loop 8 revisions) and the refill retry (loop 7). Findings #4, #5 and #8 of
`docs/reviews/2026-11-13-loops-07-19.md`.

## Faults

| # | Fault | Before | After |
|---|---|---|---|
| 4 | Every save made a new estimate job; the one worker ran them all, oldest first | saves 1, 2, 3 → measured **1, 2, 3** | measured **1, 3** (2 never runs; it answers "a newer version is being measured") |
| 4 | A render waited for its own estimate, which could sit behind other jobs, up to 900 s, then measured again on the spot | blocked behind the queue | returns in **< 0.3 s** with the last known figure or none; waits only when its own estimate is already running (that run builds the ink the render reads next) |
| 5 | One leftover hit re-rendered and refilled **every** clip | 3 clips + 3 clips | 3 clips + **1** clip (the one the hit is in) |
| 8 | A ready job trimmed from the map between two looks → `KeyError`, HTTP 500 | possible past 16 jobs | the answer is read from the job held |

## Change

- `render._drop_queued`: when an edit gets a new key, its jobs that have not started leave the queue
  and are marked ready and superseded, so nobody waits on a job that never runs.
- `render._ESTIMATE_RUNNING` records the job being measured; `render.estimate_for_render` is what the
  render queue calls: ready → that; running for this edit → wait; queued or none → drop it and start
  now with `_ESTIMATE_LAST` or nothing. `wait_for_estimate` no longer re-measures synchronously on a
  timeout.
- `render._retry_clips` finds the clips that the widened spans touch (the same ±2/+3 frame guard as
  `_widen_edit`). The first pass keeps its clip files; the refill pass takes `_reuse` and redraws only
  the others, then joins, burns captions, adds effects and mixes audio again on the whole output.
- The check sidecar now carries `refilled_clips`. The learned render rate counts from the first
  pass's start (`_started`), so it learns what the user waited, not a partial pass.
- Fill output is unchanged: `textfill.VERSION` stays 17.

## Acceptance

| Check | Result |
|---|---|
| Older saves of one edit are never measured | pass (`test_older_saves_of_an_edit_are_never_measured`) |
| A render does not wait behind another edit's estimate | pass (< 0.3 s, job dropped) |
| A render takes the last known figure when its own estimate is only queued | pass |
| A render joins its own running estimate (one run) | pass |
| A trimmed ready job still answers | pass |
| Retry clips: the hit's clip, a hit across a clip edge, none for a media beat | pass |
| Real ffmpeg render, 3 clips, one hit: clips drawn `0,1,2` then `1`; 3.0 s output; `retried`, `refilled_clips` 1; no clip file left | pass (`test_a_refill_draws_only_the_clip_that_kept_text`) |
| Full suite | **214 pass** |

## Not tested

- A real render of the review project with a leftover hit. The refill saving on it is not measured.
- The refill still re-checks the whole output (68–81 s quiet) and redoes the caption burn, effects and
  audio mix on the whole file. Only the fill and clip encode are limited to the touched clips.
- A render that starts while another edit's estimate runs now runs beside it: two heavy jobs on an
  8 GB Mac. Before, it waited. Not measured.
- Report row in `docs/reports/ducksuite-product-progress.html`: not added, the anchor is not named.
