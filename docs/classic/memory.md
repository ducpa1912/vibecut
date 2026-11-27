# Classic memory

Durable working memory for the Classic lane. Read this before changing Clean.

Last updated: 2026-11-18. Base commit `bb3e89e` (`classic`, matches
`origin/classic` when last fetched). All work described below is **uncommitted
in the working tree**.

## Lane facts

| Item | Value |
|---|---|
| Branch | `classic` |
| Worktree | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic` |
| Port | `8796` |
| Data | `~/vibecut-lanes/classic` |
| Media | `~/vibecut-lanes/media/classic` |
| Recordings | `~/vibecut-lanes/recordings/classic` |
| Fill models | `~/.cache/vibecut/models/fill` |
| Python | `3.11.7` |
| ffmpeg | `9.0.2` |
| Encoder | `videotoolbox` on this Mac |

Do not use ports `8787` (founder), `8795` (Studio) or `8797` (Voice Room).
Never `pkill` by pattern. Kill the exact listener on `8796` and restart:

```bash
pid=$(lsof -t -iTCP:8796 -sTCP:LISTEN | head -n1)
[ -n "$pid" ] && kill "$pid"
scripts/serve-classic.sh
```

For a long agent session, run it detached so a tool timeout cannot kill it:

```bash
nohup scripts/serve-classic.sh > "$HOME/vibecut-lanes/classic/server.log" 2>&1 &
```

Log: `~/vibecut-lanes/classic/server.log`.

Restart Classic after each backend or frontend fix phase.

## Current verified state

- Full suite: **2171 passed, 104 skipped**.
- The summary block reports **92** tests waiting on absent `data/media` files.
  The remaining skips are other opt-ins.
- All four Classic browser specs pass:
  - `tests/test_classic_source_clean_browser.py`
  - `tests/test_classic_source_clean_gates.py`
  - `tests/test_classic_cut_clean_browser.py`
  - `tests/test_classic_phase5_browser.py`
- `/api/health` is healthy and `/openapi.json` returns `200`.
- Final browser check at 1280×800: page height 800, frame 248×440, timeline
  139 px, lanes 44 px, 26 region rows at 51 px, phases on **Review**, Render
  enabled, no console errors.
- Founder clean-video acceptance remains **PENDING**. No real-media verdict is
  recorded.

## Files touched in the current working tree

| File | Purpose |
|---|---|
| `static/classic/workspace.css` | New bounded Clean workspace: frame, region list, compact timeline, slim bars, popovers upward |
| `static/classic/app.js` | Canvas sizing, region selection, review queue, source review hydration, manager mount, AI popover placement |
| `static/classic/index.html` | Workspace stylesheet, multiple file input, folder input, review queue panel, compact zoom controls |
| `static/classic/style.css` | Compact timeline chrome, manager/list rules, batch panel styles |
| `routes_classic.py` | Source review `GET`/`POST`; review record is persistence only, never a render |
| `app.py` | `XhsCookieBody` moved above its route so OpenAPI resolves |
| `classic_runtime/manifest.json` | Re-pinned after the `app.py` change |
| `tests/test_classic_textfill.py` | Saved-fill tests stub `_free_disk`; this Mac has < 10 GB free |
| `tests/browser/*.spec.mjs` | Updated to the region manager and current AI-fill chip/options |
| `tests/test_classic_clean_merge.py` | Selection assertion now checks `data-selected` and `paintCleanSelection` |
| `tests/test_classic_source_clean_ui.py` | Header copy assertion updated to `Regions` / `N found` |

## Architecture map

### Front end

- `static/classic/index.html` — Classic page and Clean markup.
- `static/classic/style.css` — base Classic UI.
- `static/classic/workspace.css` — Clean workspace overrides. It is linked after
  `style.css`, so later rules win at equal specificity; keep selector
  specificity in mind.
- `static/classic/app.js` — main controller.
  - `sizeCleanCanvas()` sizes the canvas from `.clean-stage-body`, not the pane.
  - `paintCleanTimeline()` mounts `#clean-found`, `#clean-layers` and
    `#clean-detail` into `#clean-manager` while Clean is active.
  - `paintCleanSelection()` updates `data-selected` without rebuilding rows.
  - `selectCleanBar()` seeks and selects; it must not re-render the list, or a
    double-click never reaches `dblclick`.
  - `scanCleanBatch()` runs the review queue.
  - `prepareSourceClean()` hydrates prepared source layers from
    `job.classic_text.source.clean`.
- `static/classic/clean-timeline.js` — pure timeline math, bars and ranges.
- `static/classic/clean-options.js` — AI-fill choice persistence.
- `static/classic/clean-merge.js` — carried-layer identity.

### Backend

- `routes_classic.py`
  - `POST /api/classic/jobs/{id}/clean/source/review` — validate source layers
    and store `job.classic_text.source = {clean, review_ready, updated}`.
    Returns `rendered: false`.
  - `GET /api/classic/jobs/{id}/clean/source/review` — read the stored review.
  - `POST /api/classic/jobs/{id}/clean/source/render` — the only render path.
  - Clean layers route, plan, frame, fill preview and fill estimate.
- `app.py`
  - `POST /api/jobs/upload` and `/api/jobs/path` with `mode=clean` create a
    `source_ready` job with no analysis.
  - `public_job()` includes `classic_text`; that is how Source Clean reloads a
    prepared review without an extra request.
- `routes_check.py` — one Check pass per job; source Check samples the whole
  source when scenes are empty.
- `clean_source.py` — whole-source clean render.
- `textfill/` — LaMa per-frame fill, GPU through PyTorch MPS, CPU through ONNX
  Runtime; Telea/Navier-Stokes through OpenCV.
- `classic_runtime/` — pinned copy of shared runtime files. Run
  `scripts/pin-classic-runtime.py --source '<why>' <files>` after changing a
  pinned shared file.

## Decisions that must stay true

1. **Review first is the default.** A scan alone never saves a layer or starts
   a render.
2. **The review queue never renders.** It uploads, scans, applies AI-fill
   candidates and stores a review record. Rendering needs an explicit human
   action.
3. **The source review is additive.** Stored under `job.classic_text.source`; it
   does not touch cut layers or the source file.
4. **Clean is one workspace**: frame + region list beside it + compact timeline.
   Do not reintroduce a separate right settings rail.
5. **11 px type floor.** No visible label, time or ruler tick below 11 px.
6. **No page scroll at 1280×800 or 1440×900** for the normal populated Clean
   workspace. Internal lists may scroll.
7. **AI fill engines**: LaMa CPU (ONNX) and LaMa GPU (PyTorch MPS), plus MI-GAN,
   Telea and Navier-Stokes when installed. Apple Intelligence is not a fill
   engine.
8. **No rights gate in Classic.** Plain responsibility notice only.
9. **Never generate media** for tests or acceptance. Real founder media only.
10. **Phases are state, not a new render path.** The Scan/Review/Clean/Render
    strip reports progress; Render calls the same reviewed primary action. Do
    not add a second render implementation.
11. **One selection across three surfaces.** A preview box, its region row and
    its timeline bar point at the same layer. Selecting one must select and
    reveal the other two, and keep the time inputs reachable.
12. **Auto-scanned boxes are directly editable.** A plain click selects the
    scan box and shows its handles and two actions. The first drag or resize
    materializes the Clean layer; do not create a layer on selection alone.
13. **The selected box owns two actions only**: Unselect and the AI/Blur method
    toggle. Do not add a third floating action without a product decision.

## Traps already paid for

- **Disk-space test assumption.** Saved fills stop below 10 GB free. This Mac
  has ~6–7 GB free, so saved-fill tests must stub `textfill._free_disk` to a
  value above `SAVED_MIN_FREE`. Do not weaken the production threshold.
- **Canvas sizing loop.** Sizing the canvas from `stage.clientHeight` while the
  canvas itself defines the stage height produced a tiny frame. Measure
  `.clean-stage-body` and set explicit width/height.
- **Selection rebuilt the list.** Calling `paintCleanStage()` from a row click
  replaced the DOM between the first and second click, so `dblclick` and the
  detail strip never fired. Use `paintCleanStage({ rows: false })` plus
  `paintCleanSelection()`.
- **Popover clipped by the timeline.** The AI-fill options opened downward from
  the last row and were clipped/unclickable. In Clean they open upward and the
  timeline panel overflows visibly.
- **Outside rows.** `cleanTimelineRows()` filters outside-cut rows, so a row
  click must check `cleanRowCutStart(row) === null` and call `focusCleanRow()`
  first to say **Not in this cut**.
- **Row seek convention.** Clicks and Enter seek to `start − 0.5 s`, clamped at
  0. Timeline bars seek to the bar start exactly.
- **Box action pointerdown.** The floating Unselect / method buttons sit above
  the canvas. The canvas pointerdown handler must return early for
  `[data-clean-box-action]` and `[data-scan-box-action]`; otherwise it
  deselects the box before `click` reaches the button.
- **Auto-scan drag threshold.** A selected scan box uses `pendingScan` until
  the pointer moves past 0.006 of the frame, then `ensureScanLayer()` creates
  the layer. Creating on pointerdown would make a plain click apply a box.
- **Scan box overlap.** Added rows are excluded from `cleanScanPartsAt()`, so
  the saved layer box is the only outline after materialization.
- **Phase strip width.** At narrow widths only the active phase and Render stay
  visible, and the build string is hidden. The top bar must not wrap.
- **Compileall and the venv.** `python -m compileall -q .` walks `.venv`, where
  PyTorch ships a Python 3.12-only file under a 3.11 install. Validate product
  code with `python -m compileall -q -x '/\.venv/' .`.
- **Playwright was installed late.** Browser specs were skipped until browsers
  and the Node module existed. The module is in the `~/.npm/_npx` cache and
  browsers are in `~/Library/Caches/ms-playwright`.
- **Stale browser specs.** Two specs still asserted the old settings rail and
  old AI-fill select ids. They now assert the region manager and the chip/menu
  UI. Keep specs aligned with the product, not with removed UI.
- **OpenAPI 500.** A Pydantic forward reference to `XhsCookieBody` was declared
  after its route. Moving the class above the route fixed `/openapi.json`.
  Re-pin `classic_runtime` after any `app.py` edit.

## Commands

```bash
# environment
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pip install -r requirements-optional.txt   # AI fill / OpenCV / torch

# run
scripts/serve-classic.sh

# checks
pytest -q
python -m compileall -q -x '/\.venv/' .
find static -name '*.js' -print0 | xargs -0 -n1 node --check
git diff --check
pytest -q tests/test_classic_source_clean_browser.py \
  tests/test_classic_source_clean_gates.py \
  tests/test_classic_cut_clean_browser.py \
  tests/test_classic_phase5_browser.py

# runtime pin after editing a pinned shared file
python scripts/pin-classic-runtime.py --source '<why>' <files>
```

## Do not

- Do not stop or kill another lane's server.
- Do not touch Studio, DuckSuite or DuckClean worktrees.
- Do not merge Classic into Studio or `main`.
- Do not push unless asked; use `scripts/ship-lane.sh`, never `scripts/ship.sh`.
- Do not open founder media unless the request names it.
- Do not run the full suite while a founder render is running.
- Do not record acceptance. Only the founder does.
