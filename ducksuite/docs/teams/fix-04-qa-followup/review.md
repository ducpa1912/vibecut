# Fix 04 review — the independent QA findings the first repair left open

**Verdict: pass on tests; the UI pieces are not yet seen in the app.** Revision of the Render screen,
the render player and the QA repair (`docs/teams/qa-repair-2026-11-13/review.md`). Source:
`docs/reviews/independent-qa-2026-11-13.md` — its four follow-up P2 findings, its packaged-app P2,
and one fault in the repair's own focus fix found on review.

## Faults and changes

| # | Fault | Change |
|---|---|---|
| 1 | Play on a finished card opened the edit's **latest** render, not that job's | Every Play button carries `data-job`; `render/file?job=` serves that job after checking it belongs to the project and edit and that its file is inside the project's `renders/` folder. `RenderQueue.job()` added. Without `job` the old behaviour stays. |
| 2 | The frame-rate selector changed nothing (24 fps source → 24 fps out, selector reset) | Selector removed. Render shows the rule the renderer uses: 24 fps when the source is within 0.6 of 24, else 30, with the source rate in brackets. |
| 3 | Render settings showed the source-aspect size, not the Cut output (1:1 showed 1920 × 1080) | `outputSizeLabel` uses `cutOutputSize`. Its even rule now matches `render._target_size` (round, then up to even); the old `round(x/2)*2` disagreed, e.g. 1920.6 → 1920 vs 1922. |
| 4 | A check that judged no frame showed "No check yet" and hid "1 line not checked" | Queue column `check_ran`, set when the check report exists. Render shows the report whenever a check ran; with nothing to judge it says "Checked · no cleaned line to judge". |
| 5 | The render player modal's bar was never wired (timer `00:00 / 00:00`, play/pause dead) | `openVideoModal` calls `setupPlayerBars()`; each player is wired once (`data-bar-wired`), since the modal outlives `render()`. |
| 6 | The repair's focus restore matched by tag, label, action and text: every queue card's "Show" matched, so focus went to the first card | The signature holds every `data-*` value (path, job, edit) and `name`; when two controls are still identical, focus is not moved rather than guessed. |

Fill output is unchanged: `textfill.VERSION` stays 17.

## Acceptance

| Check | Result |
|---|---|
| Two done jobs of one edit: no `job` → newest; `job` → that job's bytes; another edit's job or unknown id → 404 | pass (`tests/test_qa_followup.py`) |
| A job whose output is outside `projects/<id>/renders/` → 404 | pass |
| `check_ran` stored and returned with `check_unchecked` | pass |
| Every Play button has `data-job`; no `render-fps` selector; size label uses the Cut; modal wires its bar once | pass (source checks) |
| JS even rule equals `render._target_size` on five sizes | pass |
| Focus functions run in Node: two "Show" buttons differ, focus returns to the second, identical twins return none | pass |
| Full suite / `node --check` | **228 pass** / clean |

## Not tested

- Nothing here was opened in the app or a browser: no server was started (the founder runs it), and
  the packaged app the QA left running serves the bundled copy, not this tree. The founder steps are
  in `TODO.md` → Now.
- Unsaved text in an input is still lost when a queue refresh redraws the screen; focus returns, the
  typed value does not.
- Report row in `docs/reports/ducksuite-product-progress.html`: not added; the insert anchor is not
  named in `AGENTS.md`.
