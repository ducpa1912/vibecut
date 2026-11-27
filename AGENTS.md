# AGENTS.md — VibeCut Classic

Operating instructions for AI agents and developers working in this checkout.
This file is canonical for agent behaviour. Read it before changing code.

## Identity

This checkout is the **Classic** lane of VibeCut:

- independent local-first long-video → short-reel cutter,
- own branch: `classic`,
- own port: `8796`,
- own data: `~/vibecut-lanes/classic`,
- owns `static/classic/**`, `routes_classic.py`, `docs/classic/**`,
- does **not** import Studio or Voice Room UI state.

Classic is not Studio, not DuckSuite and not DuckClean.

## Read first

1. `PRODUCT.md` — current product truth.
2. `docs/classic/plan.md` — active plan and release gate.
3. `docs/classic/memory.md` — durable decisions, traps, current state.
4. `docs/classic/todo.md` — ordered backlog.
5. `docs/classic/testing/clean-video-acceptance.md` — founder gate.
6. `docs/shared/branching.md` — lanes and shipping.
7. `docs/shared/vi-glossary.md` and `docs/shared/platform-capabilities.md`.

Do not start a new product scope while the founder clean-video acceptance is
open.

## Environment

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pip install -r requirements-optional.txt
scripts/serve-classic.sh
```

- Open <http://127.0.0.1:8796/>.
- Fill models: `~/.cache/vibecut/models/fill`.
- Do not use ports `8787`, `8795` or `8797`.
- Restart Classic after each backend or frontend fix phase:

```bash
pid=$(lsof -t -iTCP:8796 -sTCP:LISTEN | head -n1)
[ -n "$pid" ] && kill "$pid"
scripts/serve-classic.sh
```

Never `pkill` by pattern and never stop another lane's server.

For a session that outlives the tool timeout, start Classic detached:

```bash
nohup scripts/serve-classic.sh > "$HOME/vibecut-lanes/classic/server.log" 2>&1 &
```

Verify `lsof -nP -iTCP:8796 -sTCP:LISTEN`. Do not start a second copy.

## Checks

```bash
pytest -q
python -m compileall -q -x '/\.venv/' .
find static -name '*.js' -print0 | xargs -0 -n1 node --check
git diff --check
```

Browser specs:

```bash
npx playwright install chromium
pytest -q tests/test_classic_source_clean_browser.py \
  tests/test_classic_source_clean_gates.py \
  tests/test_classic_cut_clean_browser.py \
  tests/test_classic_phase5_browser.py
```

Last verified tip: `77f708c` on `classic`, **2171 passed, 104 skipped**; 92 of
the skips wait on absent `data/media` files. A skipped acceptance is not a pass.

The plain `compileall .` walks `.venv`. PyTorch ships a Python 3.12-only file
that fails under 3.11; use the exclude shown above.

## Architecture

| Area | Files |
|---|---|
| Classic page | `static/classic/index.html`, `style.css`, `workspace.css` |
| Classic controller | `static/classic/app.js` |
| Clean timeline rules | `static/classic/clean-timeline.js` |
| AI-fill choice | `static/classic/clean-options.js` |
| Lane backend | `routes_classic.py`, `clean_source.py` |
| Source Check | `routes_check.py`, `detect.py` |
| Upload / jobs | `app.py` (`mode=clean`, `source_ready`) |
| AI fill | `textfill/` (LaMa, MI-GAN, Telea, Navier-Stokes) |
| Shared pin | `classic_runtime/manifest.json` |

New HTTP routes belong in `routes_classic.py`, never `app.py`.

## Clean contract

- **Review first is default.** A scan never saves a layer or renders.
- **Review queue never renders.** Multi-file/folder flow uploads as
  `source_ready`, runs Check, prepares AI-fill layers, saves a source review
  record, then waits for a human.
- Source review is stored at `job.classic_text.source`; the only render path is
  `POST /api/classic/jobs/{id}/clean/source/render`.
- The source file is never modified. Every result is a new file.
- Clean workspace = frame + region list beside it + compact timeline. Do not
  reintroduce a separate settings rail.
- Preserve title/metadata/time copy only if it helps the task; prefer one
  heading and one line of state.
- Type floor is **11 px**. No visible label, time or ruler tick below it.
- Normal populated Clean must fit with no page scroll at 1280×800 and 1440×900.
  Internal lists and the timeline may scroll.
- AI fill: LaMa CPU through ONNX Runtime, LaMa GPU through PyTorch MPS. Apple
  Intelligence is not a fill engine. Missing model disables only that engine.
- Classic has no rights gate, attestation or watermark refusal.

## Front-end rules

- `sizeCleanCanvas()` measures `.clean-stage-body`. Do not size from the pane.
- A row click must not rebuild the region list. Use
  `paintCleanStage({ rows: false })` and `paintCleanSelection()`; otherwise
  double-click detail breaks.
- Row click and Enter seek to `start − 0.5 s`, clamped at 0.
- Outside-cut rows are filtered from the timeline; check
  `cleanRowCutStart(row) === null` first and call `focusCleanRow()`.
- AI-fill menus open **upward** in Clean. The timeline panel must not clip them.
- Selection is shared: a preview box selects its region row and timeline bar,
  scrolls both into view, and keeps the row's time inputs reachable.
- Auto-scanned boxes are directly editable. A plain click selects; the first
  drag or resize calls `ensureScanLayer()` and creates the Clean layer. Do not
  create on pointerdown.
- A selected preview box owns exactly two controls outside its top-right:
  **Unselect** and the **AI / Blur** method toggle. Pointerdown on those
  controls must not deselect the box.
- The four phase labels are **Scan → Review → Clean → Render**. Render calls
  the same reviewed primary action; it is not a second render path.
- User content is never translated: file names, transcripts, OCR text,
  captions, provider errors.
- No `MutationObserver`. Use curated `data-i18n` keys.

## Test rules

- Never weaken a test to match a number.
- Update a browser spec only when the product contract changed; assert the new
  visible behaviour, not a removed id.
- Saved-fill tests must stub `textfill._free_disk` above `SAVED_MIN_FREE`
  because this Mac has less than 10 GB free. Do not lower the production
  threshold.
- Real-media tests skip when `data/media` is absent. Do not generate video,
  voice or audio to make them run.
- After editing a pinned shared file, run:

```bash
python scripts/pin-classic-runtime.py --source '<why>' <files>
```

Then re-run `tests/test_classic_runtime_pin.py`.

## Git and shipping

- Commit on `classic` only. Never commit on `main`.
- Commits are signed with the founder's SSH key. Never disable signing.
- Push only when asked, using `scripts/ship-lane.sh`.
- Never run `scripts/ship.sh`; old copies move `main`.
- Never force-push, never delete a lane feature to hide it.
- Do not merge Classic into Studio or `main`.

## Boundaries

- Do not touch `vibecut-studio`, `ducksuite` or `duckclean` worktrees.
- Do not open founder media unless the request names it.
- Do not run the full suite while a founder render is running.
- Do not record acceptance. Only the founder records the verdict.
- Do not add accounts, cloud sync, publishing, analytics, generative face/logo
  repair, avatars, voice cloning, stock B-roll or hosted rendering.
- Do not add a new AI model to Classic without an explicit founder decision.

## Definition of done

- Behaviour verified on the real UI; real media where the item requires it.
- Focused tests added or updated; full suite green.
- JavaScript syntax, product compile and diff checks green.
- Server restarted; `/api/health` healthy; `/openapi.json` returns 200.
- Evidence and current tip recorded in `docs/classic/memory.md`.
- If a founder gate is still open, say so; do not call the release done.
