# Loop 22 — leftover check under grade, and the fps change (REQ-20261115-01, items C and D)

Written by the sub-leader on 2026-11-15. HEAD `d533a48`, 241 tests. Build team: OpenCode.
Verifier: the sub-leader, who reruns the tests, reads the diff and checks the numbers on disk.

## C — the leftover check under a grade or Enhance

`render.check_view` reads the source through the whole render chain, grade and sharpen included,
and the output is graded the same way. The thresholds were calibrated on ungraded pixels:
`ink.EDGE` 40 (stroke edge), `inkcheck.SAME` 20 (untouched text measured 9–13.4, a fill 30+).
Contrast −50 halves edge strength, so strokes may fall under `EDGE` and lines go "not checked";
contrast or exposure up scales the output/source difference, so a leftover may read closer to or
further from `SAME`. Nobody has measured it.

**Rule to prove: a line that still shows text in the output is a hit or "not checked", never
clean.** A clean line must not turn into a false hit either; measure that too.

### C acceptance

C1. **Real media, no generated video.** Use a scratch copy of `prj_e95348a97316` (copy into
    `build/loop22-evidence/`, never the app container, never edit `ed_38a4c36a3aae` in place). Pick
    a short span (2–4 clips) with at least two fill lines that the check judges today (not one of
    the two "not checked" lines). Make one of them a **known leftover**: render it with its fill
    skipped while the check still judges it (a test hook or a patched fill selection in the
    measuring script; nothing in product code may skip a fill). The other stays filled.
C2. **Matrix.** For each Cut: none · contrast −50 · contrast +50 · contrast +100 · exposure −1 ·
    exposure +1 · Enhance 2× (crop to half, sharpen on) — record for both lines: verdict (hit /
    clean / not checked), frames judged, the max and median judged difference against `SAME`,
    and the share of ink pixels above `EDGE`. One table in `review.md`.
C3. **Pass rule.** The leftover line is a hit or "not checked" in all seven; the filled line is not a
    hit in any. If a cell fails, stop: report the table and propose a fix in `review.md` (for
    example, building the ink from a geometry-only view of the source so `EDGE` sees ungraded
    strokes). Do not ship a threshold or check change without a sub-leader revision.
C4. A pytest that locks the pass rule on a small fixture derived from real frames already in the
    repo's tests (no new generated video files): grade the leftover by contrast −50 and +100 and
    assert hit-or-unchecked.

## D — output frame rate stated, one rule

The rule `24 if |fps − 24| < 0.6 else 30` lives in `render.render_edit` and `render.py` ≈ line 430
**and** is copied in `static/duck/app.js` ≈ line 3673. The Render screen shows
`30 fps · set from the source (25 fps)` but never says what the change does.

### D acceptance

D1. **One rule.** A single core function (e.g. `render.output_fps(meta)`) is used by
    `render_edit`, the proof path and the estimate, and its result reaches the UI through an existing
    payload (edit source meta or the estimate). The JS copy is removed. Test: 23.976 → 24, 24 → 24,
    25 → 30, 29.97 → 30, 50 → 30, 60 → 30, 0/unknown → 30.
D2. **Say the limit.** When the source rate and the output rate differ by more than 0.6, the
    Render frame-rate line states it in plain words, measured from the two rates, for example
    `Source 60 fps → 30 fps: every 2nd frame is dropped` or `Source 25 fps → 30 fps: about 1 frame
    in 5 is shown twice`. No selector. Same-rate sources show what they show today.
D3. Look at the screen: rebuild with `./scripts/build-xcode-dev.sh` is not required; serve the core
    on a scratch data root (`python3 duck_app.py --data-root build/loop22-evidence/root --port 8799`)
    and capture the Render screen at 1440×900 for one 24 fps and one 25 or 60 fps source **already
    on disk** (do not generate media; if none exists, say so and test the string with node). Do not
    click in the founder's app window.

## Out of scope

`ink.EDGE` / `inkcheck.SAME` values (unless the sub-leader revises after C3); an fps selector;
60 fps output; any fill change (`textfill.VERSION` stays 17).

## Definition of done

Behaviour + tests + `MEMORY.md` Outcome line for C/D + `TODO.md` ticks +
`docs/teams/loop-22-check-grade-fps/review.md` (verdict, pass/fail per item with numbers, the C2
table, what got worse, what was not tested, commits) in one commit. pytest (241 today) and
`node --check static/duck/app.js` pass. Do not push. Never read `old_*.md` or
`docs/reports/*.html`.

## Revision 1 — 2026-11-15 (sub-leader review of `2e87acd`)

Verified by the sub-leader: 252 tests pass, `node --check` clean; diff of `render.py` and `app.js`
read. **C1–C3 accepted** as OpenCode's measured claim (7/7 leftover hits, 0/7 filled false hits,
thresholds unchanged). **D1 accepted** (`render.output_fps`, JS copy removed). D2's wording is
accepted.

Two things block the push:

R1. **No founder footage in git.** `tests/fixtures/loop22_real_line.npz` is 3.3 MB of frames from
    the founder's video; footage may belong to a client and this repo is pushed to GitHub. The
    commit is not pushed: replace it (`git reset --soft HEAD~1`, recommit) so the file is in no
    commit. C4's test must use strokes drawn in memory with numpy (text-like shapes on a
    textured background, no file), the same contrast −50/+100 grades, the real `ink.build` and
    `inkcheck._judge`, and assert hit-or-unchecked. Keep the real-frame matrix as the measured
    evidence in `review.md` (numbers only, no frames). `build/loop22-evidence` stays gitignored;
    confirm with `git check-ignore`.
R2. **The fps line can stick on "Reading the output frame rate…".** It reads only
    `state.renderEstimate.output_fps`; when the estimate fails (`{failed: true}`) the text never
    resolves. The core must also put `output_fps` where the Render screen always has it (the
    edit's `source` meta the UI already loads, or the failed-estimate payload), and the JS reads
    that first. Node test: failed estimate still shows the rate.
R3. pytest and `node --check` pass (state the count). Update `review.md`, `MEMORY.md` Outcome and
    `TODO.md`. One commit replacing `2e87acd`; do not push.
