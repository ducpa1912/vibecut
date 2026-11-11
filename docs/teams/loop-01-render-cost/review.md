# Loop 1 — show the render cost

Date: 2026-11-11 · Request: REQ-20261111-05 (`PLAN.md`, loop 1) · Ground rule 4: do not hide a limit.

## Brief

A render with AI fill can take hours, and nothing said so before Start render. The time estimate
existed in `textfill` (`estimate_span`, `estimate_summary`) with no caller. Show it where the user
decides: the Render screen and the Clean all dialog. No fill output change, no `VERSION` bump.

## What changed

- `duckcore/render.py` · `estimate_edit(edit, meta, data_root)`: walks the same clips and fill layers
  as `render_edit`, sums the span estimates, adds layer counts, fill seconds and the disk state.
- `duckcore/engine/textfill` · `saved_fill_disk(path)`: free disk against `SAVED_MIN_FREE`, with the
  sentence shown when it is low.
- `duckcore/main.py` · `GET /api/projects/{id}/edits/{id}/render/estimate`.
- `static/duck/app.js`, `app.css` · a cost box above Start render and inside the Clean all dialog;
  the toast after Clean all carries the new estimate. The box is patched in place; no full re-render.
- `tests/test_render_estimate.py` · 5 tests.

## Acceptance

| Check | Result | Evidence |
|---|---|---|
| Render screen shows an estimate before Start | pass | Review project at 1440×900: "AI fill · 2h 45m · 60s of video in 40 fill layers · measured on this Mac" above Start render |
| Clean all dialog shows the same estimate | pass | Dialog opened (not confirmed): same box under "Rendering the layers as they are now" |
| Says measured vs first guess | pass | `test_estimate_uses_the_rate_measured_on_this_mac`, `…_seed_rate_and_says_it_is_a_guess` |
| No fill layers adds no time | pass | `test_estimate_with_no_fill_layers_adds_no_time` |
| Low disk warns | pass (test only) | `test_estimate_warns_when_disk_is_under_the_saved_fill_floor`; this Mac has 18 GB free now, so the warning was not seen on screen |
| Route answers, 404 on a missing edit | pass | `test_estimate_route_answers_for_a_saved_edit` |
| No fill output change | pass | no change under `textfill` fill paths; `VERSION` stays 12 |
| Suite | pass | 88 passed; `node --check static/duck/app.js` passes |

## Not tested

- The toast after a confirmed Clean all. Confirming rewrites the layers; that belongs to loop 2.
- The accuracy of the figure. The rate in `fill_rates.json` comes from 4 short runs. Loop 4 records
  real wall-clock beside it.
- The screen was checked in the dev core in a browser at 1440×900. `./scripts/build-xcode-dev.sh`
  passed (377 MB) and the bundle carries the new UI, but the native window was not opened and
  looked at in this loop.

## Roles

One agent did the brief, the code and the test pass in this loop; the `creator` and `product-owner`
subagents were not spawned. Sign-off is the founder's.

## Found on the way, not fixed here

- The render queue still lists two "Done" jobs with a Play button for this project; their files
  were deleted in the disk cleanup. Logged in `TODO.md`.
- 15 stale `duck_app.py` dev servers from earlier sessions are still running on this Mac
  (ports 8783–8802, `/tmp` data roots, up to 2.5 days old). Not touched.

## Verdict

Good to go, pending the founder's look at the screen.
