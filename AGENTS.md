# AGENTS.md — DuckClean

This file tells any coding agent how to work in this local directory.

## What this project is

DuckClean is a **cloud-only** product with one purpose: remove baked-in text,
logos and burnt-in images from video, then return the **full-length** video with
the original audio, duration, display size and frame rate.

It is not Classic, not Studio, not a reel cutter, not a local runner and not a
desktop app. The browser is the client; rendering happens on cloud workers.

- Repository: `https://github.com/ducpa1912/vibecut.git`
- Branch: `duckclean` (orphan; no shared history with `classic` or `main`)
- Local path: `/Users/happynghia/Public/Project/Code/drop_eval/duckclean`
- Push only to `origin/duckclean`. Never move `main` or `classic`.
- Classic source is `origin/classic` in the same repo. The old
  `vibecut-classic` worktree is deleted.

## Read first

1. `FREEBUFF_HANDOFF.md` — takeover brief for the next coding agent.
2. `HANDOFF.md` — binding product brief.
3. `docs/duckclean/plan.md` — architecture and build plan.
4. `docs/duckclean/contract.md` — frozen wire/data contract.
5. `docs/duckclean/infrastructure.md` — Clerk, Postgres/Hyperdrive, R2, worker,
   queues and Pages.
6. `docs/duckclean/cost-model.md` — hosting, CPU and GPU at three scales.
7. `docs/duckclean/providers.md` — auth/storage/Postgres alternatives.
8. `docs/duckclean/roadmap.md` — product milestones.
9. `docs/duckclean/detection-report.md` — real-file evidence.
10. `SESSION.html` — full request/response history.

If a doc conflicts with `HANDOFF.md`, `HANDOFF.md` wins. If `HANDOFF.md` conflicts
with this file on engineering workflow, this file wins.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Vite + React + TypeScript, static SPA, Cloudflare Pages |
| Auth | Clerk, `@clerk/react` 6, OAuth/JWKS |
| API | Cloudflare Workers + Hono, `/api/v1` |
| Database | Postgres; Neon free for now; Cloudflare Hyperdrive |
| Blob | Cloudflare R2; presigned PUT/GET; zero egress |
| Queue | Cloudflare Queues + DB-backed job state |
| CPU worker | Python FastAPI Docker image; HF CPU Basic / local |
| GPU worker | RunPod or Modal serverless; ProPainter/generative only |
| Billing | Stripe metered render-hour equivalent (M6) |
| Unit of work | Beat: scene-bounded 1–4 s span |

## Layout

```text
web/                       React SPA
api/                       Cloudflare Worker
  src/app.ts               app shell and middleware
  src/routes/              health, uploads, library, detect
  src/jobs/                queue dispatch, handlers, worker call
  src/db.ts                user-scoped Postgres queries
  src/storage.ts           R2 signer/binding/local S3
  migrations/              0001, 0002, 0003
  test/                    PGlite/Vitest
worker/                    Python CPU/GPU worker
  duckclean_worker/app.py  FastAPI routes
  duckclean_worker/detect.py
  duckclean_worker/dissect.py
  tests/
engine/                    deliberate Classic ports; no app code
scripts/                   dev-db, dev-s3, m1-doctor
docs/duckclean/            plan, contract, infra, cost, providers
```

## Commands

```bash
make setup                 # npm install + .venv + worker[dev,ocr]
make check                 # lint, typecheck, API tests, worker tests, build

npm run dev:web            # Vite :5173
npm run dev:api            # wrangler dev :8787
npm run dev:db             # PGlite :5432
npm run dev:s3             # MinIO :9000 (brew install minio)
npm run m1:doctor          # env, Wrangler, live health

cd worker
set -a; source .env; set +a
../.venv/bin/uvicorn duckclean_worker.app:app --port 8799
```

`api/.dev.vars`, `web/.env.local` and `worker/.env` are local, gitignored and
must never be committed.

## Current status

- M1: complete — auth, library, direct-to-R2 upload, probe, proxy, poster,
  playback.
- M2: complete for short sources — scene dissection, RapidOCR, tiled OCR,
  tracklets, groups, masks, coverage, scoped detection, detection UI.
- Local no-Cloudflare path: PGlite + MinIO + real worker.
- 68 API tests, 40 worker tests, typecheck, lint, mypy, ruff, build pass.
- `npm audit --omit=dev` is clean.
- Live cloud resources are **not provisioned**.
- M3 review workspace, M4 pre-render, M5 render, M6 billing and M7 best-quality
  engines are not built.

## Hard rules

1. **No fake media, voice, progress or success.** Acceptance uses real user
   media. Generated clips are unit-test fixtures only.
2. **Video bytes never pass through the API Worker.** Browser uploads directly
   to R2 with a presigned PUT. Workers read/write R2. Only small masks pass
   through the API in M2.
3. **Server owns groups, members, boxes, ranges, masks and revision.** The UI
   sends intent, never derived state.
4. **`range_mode` is `ranges` or `whole_source`.** Empty ranges never mean the
   whole video.
5. **LaMa is CPU-only.** ProPainter and generative fill are GPU. Reject LaMa with
   `gpu_standard` or `gpu_premium` in both API and worker.
6. **A scoped detection never marks unread beats empty.** They stay `pending`.
7. **A truncated scan is not a full scan.** Report `truncated` and real
   `effective_fps`; never claim coverage that was not read.
8. **Do not reintroduce `api/src/jobs.ts`.** It is now `api/src/jobs/`.
9. **Do not import Classic app modules.** Port engine code deliberately into
   `engine/`, with a port log.
10. **No local runner and no Apple Vision in the cloud path.**

## Known M2 limits

- 600 OCR-frame run cap. At 30 fps, roughly the first 20 s; longer plans report
  `truncated`. M3 must chunk long sources by beats.
- RapidOCR only. PaddleOCR is rejected until packaged.
- No logo/watermark model. Every run reports `logo_model_unavailable`.
- One union mask per member, not one per range.
- Detection is synchronous and single-slot.
- No render engine is implemented yet.

## Testing rules

- Before every commit: `make check`.
- Add tests for any behavior change.
- API tests use PGlite; worker tests use real ffmpeg and RapidOCR.
- Do not weaken tests to make a change pass.
- Real-media acceptance must use a real clip with known text, a logo, a
  burnt-in image, and a genuinely text-free clip.

## Commit and push

- Small, scoped commits.
- Conventional style: `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`.
- Sign with the configured SSH key if possible.
- Push only `origin/duckclean`.
- Never merge Classic or move `main`.

## Next move

Read `FREEBUFF_HANDOFF.md`, run `make check`, then start M3: review timeline,
tight member bars, include/exclude, preview tickets, blur pre-render, and
long-source beat chunking.
