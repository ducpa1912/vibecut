# CLAUDE.md — VibeCut Classic

This checkout is the **Classic** lane. `AGENTS.md` is canonical; read it,
`PRODUCT.md`, `docs/classic/plan.md`, `docs/classic/memory.md` and
`docs/classic/todo.md` before editing.

## What this product is

Classic turns a long video into either a whole cleaned video or a short reel.
It is independent from Studio and the Voice Room:

- branch `classic`, port `8796`,
- data `~/vibecut-lanes/classic`,
- owns `static/classic/**`, `routes_classic.py`, `docs/classic/**`.

No Studio or Voice Room UI imports. No merge into `main` without an explicit
release decision.

## Current state (2026-11-18)

- Base `bb3e89e`; the Clean workspace revision and review queue are
  **uncommitted**.
- Clean workspace: frame + region list beside it + compact timeline.
- Review queue: multiple files/folder → upload `source_ready` → Check → prepare
  AI-fill layers → save source review. **It never renders.**
- AI fill: LaMa CPU (ONNX Runtime) and LaMa GPU (PyTorch MPS), plus MI-GAN,
  Telea and Navier-Stokes when installed. Apple Intelligence is not a fill
  engine.
- Verified: **2171 passed, 104 skipped**; all four Classic browser specs pass.
- Founder clean-video acceptance is **PENDING**. Only the founder records it.

## Commands

```bash
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pip install -r requirements-optional.txt
scripts/serve-classic.sh

pytest -q
python -m compileall -q -x '/\.venv/' .
find static -name '*.js' -print0 | xargs -0 -n1 node --check
git diff --check
```

Restart after each fix phase, using the exact listener:

```bash
pid=$(lsof -t -iTCP:8796 -sTCP:LISTEN | head -n1)
[ -n "$pid" ] && kill "$pid"
scripts/serve-classic.sh
```

Never `pkill` by pattern. Never touch ports `8787`, `8795` or `8797`.

## Hard rules

- Review first is the default. A scan does not save or render.
- The review queue does not render. Only
  `POST /api/classic/jobs/{id}/clean/source/render` renders a whole video.
- The source is never modified.
- Clean layout: frame + region list beside it + compact timeline. No separate
  settings rail.
- 11 px minimum visible type.
- No page scroll in the normal populated Clean at 1280×800 or 1440×900.
- Row click/Enter seeks to `start − 0.5 s`; outside rows say **Not in this cut**.
- Selection must not rebuild the region list; use
  `paintCleanStage({ rows: false })` plus `paintCleanSelection()`.
- AI-fill menus open upward; the timeline must not clip them.
- Selecting a preview box selects its region row and timeline bar. The box
  shows two outside controls: **Unselect** and **AI / Blur**.
- Auto-scanned boxes behave the same: click selects, first drag or resize
  creates the layer. Do not apply on click.
- The top-bar phases are **Scan → Review → Clean → Render**. Render reuses the
  reviewed primary action; no second render path.
- User content is never translated. No `MutationObserver`.
- No generated media for tests or acceptance.
- Never weaken tests to match a count.
- Saved-fill tests stub `textfill._free_disk`; this Mac has < 10 GB free and the
  production threshold stays 10 GB.
- After editing a pinned shared file:
  `python scripts/pin-classic-runtime.py --source '<why>' <files>`.

## Tests that matter

```bash
pytest -q tests/test_classic_source_clean_browser.py \
  tests/test_classic_source_clean_gates.py \
  tests/test_classic_cut_clean_browser.py \
  tests/test_classic_phase5_browser.py
```

`npx playwright install chromium` is required once per machine. A skipped
browser suite is not a pass.

`compileall .` fails inside `.venv` because PyTorch ships a Python 3.12-only
file; use the exclude shown above.

## Shipping

- Commit on `classic` only, signed with the founder's key. Never disable
  signing.
- Push only when asked, with `scripts/ship-lane.sh`.
- Never run `scripts/ship.sh`; it moves `main`.
- Do not merge into Studio or `main`.
- Do not record acceptance. The founder does.

## Next work

Follow `docs/classic/todo.md`:

1. Founder clean-video acceptance on real media.
2. Real LaMa GPU render and timing.
3. Review queue end to end on a real folder.
4. Fix only the defects those runs expose.
5. Commit, pin, ship.
