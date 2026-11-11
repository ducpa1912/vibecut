# Freebuff handoff — DuckClean

Read this with `HANDOFF.md` and `docs/duckclean/plan.md`. This file describes the
current code, what changed, and what the next agent must not break.

## Repository

- Remote: `https://github.com/ducpa1912/vibecut.git`
- Branch: `duckclean`
- Local: `/Users/happynghia/Public/Project/Code/drop_eval/duckclean`
- Orphan branch: no shared history with `classic` or `main`.
- Push only to `origin/duckclean`. Never move `main` or `classic`.
- Classic source is `origin/classic` in the same repo. The old Classic worktree
  is deleted.
- Current head when this handoff was updated: see `git log -1` (`3ebde2e` before
  the handoff refresh).

## Current status

M1 and the short-source M2 path are implemented and gate-green:

```text
npm run typecheck          pass
npm run lint:js            pass
mypy (worker)              pass
ruff check/format          pass
API Vitest                 68 tests pass
Worker pytest              40 tests pass
web build                  pass
npm audit --omit=dev       0 vulnerabilities
```

Local no-Cloudflare stack exists:

```bash
npm run dev:db       # PGlite on 127.0.0.1:5432, migrations applied
npm run dev:s3       # MinIO on 127.0.0.1:9000 (requires `brew install minio`)
npm run dev:api      # wrangler dev on 127.0.0.1:8787
npm run dev:web      # Vite on 127.0.0.1:5173
cd worker && set -a && source .env && set +a && ../.venv/bin/uvicorn duckclean_worker.app:app --port 8799
```

`api/.dev.vars` and `web/.env.local` exist locally and are gitignored. Fill
Clerk and R2 values, or use `R2_ENDPOINT=http://127.0.0.1:9000` with MinIO.
`worker/.env` holds the same HMAC secret as the API.

## What is implemented

### M1

- Clerk sign-in, library list, upload, probe, 720p proxy, poster, signed playback.
- Direct browser-to-R2 PUT with real byte progress and cancel/retry.
- Postgres migrations `0001` and `0002`.
- API routes split under `api/src/routes/`; dispatch under `api/src/jobs/`.
- Local PGlite and MinIO development path.

### M2

- Scene-cut beat dissection with frame-exact spans, max 4 s, min 1 s.
- RapidOCR detection with 2×2 or 3×3 tiled OCR.
- Tracklets, grouping, masks, coverage, low-confidence retention.
- Detection run API, cancel, scope selection, revision, UI detection panel.
- Mask writes to R2; masks are inline base64 from the worker until M3.
- API owns the canonical beat-manifest hash; worker returns `source_sha256`.

## Software factory workflow

This project is not ad-hoc chat. Before any **totally new** capability, append a
`REQ-YYYYMMDD-NN` entry to `memory.md` and a linked actionable checklist to
`todo.md`. Then freeze the contract, build, test, ship and reflect.

- New capability: new panel/screen/route/table/worker route/queue/storage/
  integration/billing unit/acceptance rule.
- Revision: spacing, colour, type, copy, icon, layout, rename, refactor,
  dependency patch. No new REQ unless contract/data/acceptance/capability
  changes.
- Example: “transcript panel inside the video preview” = new REQ.
  “Move the transcript panel 4 px lower” = revision.
- Commit code + tests + memory + todo together. Fill the REQ commit hash and mark
  the todo done.

Read `AGENTS.md` §Software factory workflow for the exact templates.

## Hard rules

1. **No fake media, voice, progress or success.** Tests may generate clips;
   acceptance uses real user media only.
2. **Video bytes never pass through the API Worker.** Browser PUTs to R2; worker
   uses signed URLs. Only small masks go through the API in M2.
3. **Server owns groups, members, boxes, ranges, masks and revision.**
4. **`range_mode` is explicit.** Empty ranges never mean whole source.
5. **LaMa is CPU-only.** ProPainter and generative fill are GPU. The API planner
   and worker contract reject LaMa with a GPU class.
6. **A scoped detection never marks unread beats empty.** They stay `pending`.
7. **A truncated scan is not a full scan.** Report `truncated` and real
   `effective_fps`; do not claim coverage that was not read.
8. **Do not reintroduce `api/src/jobs.ts`.** It is now `api/src/jobs/`.
9. **Do not merge Classic.** Port engine fixes deliberately into `engine/`.

## Known M2 limits

- **600 OCR-frame run cap.** At 30 fps, roughly the first 20 seconds of a source
  are scanned. Longer sources report `truncated`; M3 must chunk by beats.
- **RapidOCR only.** `engine: paddleocr` is rejected. Do not record an engine
  the worker cannot run.
- **No logo/watermark model.** Every run reports `logo_model_unavailable`.
- **One union mask per member**, not one mask per range. This prevents moving
  text from being left unmasked, but is less precise than per-range masks.
- **Detection jobs are synchronous and single-slot.** Fine for M2 testing; M3
  and scale need parallel beat jobs.
- **No render yet.** LaMa/ProPainter/generative are contract-only in this tree.

## What to build next

M3 — review workspace:

1. Real timeline with group rows, tight member bars, playhead, include/exclude.
2. Frame/video preview tickets; blur pre-render.
3. Chunk long-source detection across beats instead of the 600-frame cap.
4. Wire the pre-render check before render.
5. Use real user media with known text for acceptance.

Then M4/M5: render selection, LaMa CPU clean, ProPainter/generative GPU,
assembly, audio mux, download.

## Files that matter

- `api/src/routes/detect.ts` — detection start/cancel, scope, engine truth.
- `api/src/jobs/handlers.ts` — probe, proxy, dissect, detect dispatch.
- `api/src/db.ts` — detection state, beat reset, masks, job retry.
- `worker/duckclean_worker/detect.py` — OCR, tracklets, groups, masks, coverage.
- `worker/duckclean_worker/dissect.py` — scene pass and beat planner.
- `web/src/components/ItemView.tsx` — detection panel and polling.
- `scripts/dev-db.mjs`, `scripts/dev-s3.mjs` — local stack.
- `docs/duckclean/contract.md` — wire rules.
- `docs/duckclean/cost-model.md` — hosting and GPU economics.

## Workflow

- Before every commit: `make check`. It now installs `worker[dev,ocr]`, so
  detection tests are real.
- If adding a migration, add it in `api/migrations/` and update
  `api/test/helpers/migrate.ts`; `npm run dev:db` must be restarted.
- If adding a worker route, update `worker/duckclean_worker/contract.py`, the
  API `worker-contract.ts`, and tests together.
- Do not commit `api/.dev.vars`, `web/.env.local`, `worker/.env`, `web/dist`,
  `.dev/`, or model/cache files.
- Commit to `duckclean`; push with `origin/duckclean`. Do not move `main`.

## First move

Read `docs/duckclean/plan.md` §7 and `contract.md` §M2, then run `make check`
and `npm run m1:doctor`. Pick up at M3, not by rewriting M2.
