# AGENTS.md — DuckSuite

Read `MEMORY.md` (what was asked and answered) and `TODO.md` (what is left) before touching code.

## What this is

DuckSuite is an offline macOS video editor. A local Python core does analysis, clean, and render; a
WKWebView UI is the product surface; a thin Swift shell owns the window, disk access, and the sidecar.
One project is open at a time. No account, no upload, no telemetry, no downloaded executable code.

```
duckcore/        Python core: check, clean, render, packs, stt, translation
static/duck/     UI: app.js, app.css, index.html, extracted helpers
mac/DuckSuite/   Swift shell (window, import bridge, sidecar launch)
scripts/         build, sign, bench
tests/           pytest suite + node helper tests
docs/            reports, team reviews, plans
```

## Ground rules

1. Local only. Nothing leaves the Mac. Model packs are data, not code.
2. Do not start App Store, signing, or TestFlight work unless the user asks. It is paused by decision.
3. Merge target is this branch, `ducksuite`. `main` has no common ancestor and lives in another
   worktree. Never merge it.
4. Do not hide a limit. If fill cannot rebuild what it covers, measure it and say so in the UI.
5. Old information is never deleted from the progress report. New entries go on top.
6. Existing comments in code are payload. Do not shorten or delete one you were not asked to change.

## Request intake — the factory loop

Every request enters the same pipeline. Classify it before touching code.

**New request** — a capability, screen, data flow or behaviour that does not exist yet.
Example from this project: "put the transcript panel inside the video preview panel".
That needs a new panel, state and data flow, so it is new.

**Revision** — a change to something that already exists: polish, spacing, wording, a
regression, a bug in shipped behaviour. Example: "revise the UI/UX", "the inspector is too busy".

Rule of thumb: if the request can be answered with a screenshot of an existing screen, it is a
revision. If it needs a new panel, state, endpoint or data flow, it is new.

### For a new request

Do this before writing code.

1. **`MEMORY.md`** — append one entry under `## Request log`:

   ```md
   ### REQ-20261111-01 · 2026-11-11
   **Request:** <the user's words, verbatim>
   **Read as:** <one sentence: what must exist after this>
   **Response:** <what the agent said it would build, or the decision taken>
   **Outcome:** <filled when done: what shipped, test count, follow-up id if any>
   ```

2. **`TODO.md`** — add the plan under the right priority. Every item carries the request id:

   ```md
   - [ ] REQ-20261111-01 · transcript panel docks inside the video preview
   - [ ] REQ-20261111-01 · scene change updates the docked transcript
   ```

3. Implement, test, then tick the items and fill `Outcome`. Name the change, not the sha of the
   commit that contains the record; a commit cannot contain its own hash.
4. Add the loop to `docs/reports/ducksuite-product-progress.html` on top, old entries kept.

### For a revision

No new entry body. Add one line to the request that created the thing if the plan changes, and a
TODO line only when it creates new work. It still gets a commit and a report line.

### Never batch

One request, one MEMORY entry, one TODO block, one commit. A second request during the same turn
gets its own id and its own block, even when the code lands together.

## Run

```bash
# Full local build: core, static, helpers, LaMa, ad-hoc signature.
./scripts/build-xcode-dev.sh
open build/DuckSuite-Xcode.app

# Core only, for UI work in a browser.
python3 duck_app.py --data-root \
  "$HOME/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite" \
  --port 8799
# The launch token is read from stdin. UI: http://127.0.0.1:8799/?t=<token>
```

App data root: `~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite`
Projects live in `projects/<id>/`, renders in `projects/<id>/renders/`, fill cache in `projects/<id>/fill/`.

## Test

```bash
python3 -m pytest -q tests      # 82 pass; 1 skips when node is not on PATH
node --check static/duck/app.js
./bin/vision_probe <dir>        # OCR on real frames, JSON lines
python3 scripts/bench_fill.py --project prj_... --frames 10   # fill quality, ground truth
```

A change is not done until pytest passes, `node --check` passes, and the real screen was looked at.

## Environment gotchas (this Mac)

- A restarted harness resets `PATH` to `/usr/bin:/bin:/usr/sbin:/sbin`. Put these back first:
  ```bash
  export PATH="/Users/happynghia/.nvm/versions/node/v26.11.1/bin:/opt/homebrew/bin:$PATH"
  ```
- `ffmpeg` / `ffprobe`: bundled at `build/DuckSuite-Xcode.app/Contents/Resources/Helpers`, also in
  `/opt/homebrew/bin`. The app reads the bundled ones.
- The git remote is SSH and fails. Push over HTTPS:
  ```bash
  git push https://github.com/ducpa1912/vibecut.git ducksuite
  ```
  The repo is named `vibecut`; the product branch is `ducksuite`.
- The commit signing key needs a passphrase. Use `git -c commit.gpgsign=false commit`.
- The sidecar handshake times out after 12 s. If the app window is blank, check for an orphan
  `Resources/duckcore/duckcore` process and kill it before relaunching.

## Invariants

- Clean layer boxes are normalized to the source frame; ranges are absolute source time.
- The fill cache key includes `textfill.VERSION`. Bump it whenever fill output changes, or old clips
  are reused and the render silently keeps the previous look. A bump makes the next render cold and
  slow; say so.
- Blur uses the wide shadow pad, fill uses the tight one (`layer_rect`). Do not merge them.
- Check must read the true first frame (`pipeline._first_still`). Some titles live under 100 ms.
- Proofs are optional. Render never waits for a proof.
- A line over a moving background is flagged (`quality: "moving"`), not silently switched to blur.
  Only a flash under 0.5 s defaults to blur.
- `clean.patch_layer` marks a layer `auto: false`; Clean all must keep the user's Fill/Blur/Off choice.
- Clean all is destructive-ish: it confirms first and reports `fill · blur · off` counts.

## Change recipe

0. Classify the request with **Request intake** above. New request: log it in `MEMORY.md` and
   plan it in `TODO.md` first.
1. Pick one item from `TODO.md`.
2. Reproduce it; write the failing test first when the bug is in Python.
3. Fix small, in the module that owns the behaviour.
4. `pytest`, `node --check`, then rebuild and look at the real screen at 1440×900.
5. Commit in Conventional Commits, then push with the HTTPS URL above. One loop = one commit.
6. Close the loop in the same commit: tick `TODO.md`, fill `Outcome` in `MEMORY.md`, add the entry
   to `docs/reports/ducksuite-product-progress.html` on top.

Definition of done: behaviour + test + the three documents changed in one commit. A commit that
changes behaviour but leaves the documents stale is not done.

## Where the evidence lives

- `docs/reports/ducksuite-product-progress.html` — product report, newest on top, plus the session log.
- `docs/teams/uiux-balance-01.md` — layout balance review and proposals.
- `scripts/bench_fill.py` — fill quality benchmark with ground truth.
- `tests/` — behaviour contract. `tests/test_clean_loop2.py` covers layer planning and the fill hole.

## Known traps

- Do not start a throwaway HTTP server to read an HTML file. Open the file.
- Do not judge fill quality from one frame. Use the benchmark, then check a real span.
- Do not trust `check.json` after a detection change; the project must be re-Checked.
- A full render after a cache bump can take hours. Warn before starting one.
