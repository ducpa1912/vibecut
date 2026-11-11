# DuckClean

Cloud-only removal of baked-in text, logos and burnt-in images from video.

Upload a full-length video, review what was detected, and get the whole video
back with the selected regions filled in. Rendering runs in the cloud, so a
phone can complete the entire flow.

`HANDOFF.md` is the binding brief. `FREEBUFF_HANDOFF.md` is the takeover brief
for the next coding agent. `AGENTS.md` is the local working agreement.
`memory.md` is the request/response history. `todo.md` is the done/not-done
list. `SESSION.html` is the full visual session log. `docs/duckclean/contract.md`
is the frozen M0 contract. `docs/duckclean/infrastructure.md` says exactly what Clerk, R2,
Postgres and Hyperdrive are, what exists, and what must be created.
`docs/duckclean/providers.md` compares current auth, storage and Postgres
prices. `docs/duckclean/cost-model.md` is the three-scale hosting and worker
cost model. If a doc disagrees with `HANDOFF.md`, the handoff wins.

## Status

M1 and M2 code complete: signed-in upload, direct-to-R2 transfer with real byte
progress, probe, 720p proxy + poster, scene dissection into frame-exact beats,
frame-by-frame OCR with groups/members/ranges/masks/coverage, and a read-only
detection panel in the item view. The live cloud is **not provisioned** yet.

The full pipeline has been run end to end on a local stack with no Cloudflare
account: PGlite for Postgres, MinIO for S3, the real Python worker and real
ffmpeg/RapidOCR. See `docs/duckclean/infrastructure.md` §Local development.

- `api/migrations/0001_init.sql` … `0003_m2.sql` — Postgres schema with the hard
  rules enforced by constraints.
- `api/openapi.yaml` — every route, ticket, error and payload.
- `api/src/app.ts` — health, me, uploads, library, play, detect (start/read/cancel).
- `api/src/jobs.ts` — DB-backed probe/proxy/dissect/detect dispatch, signed
  worker calls, mask upload from the worker's inline PNG.
- `api/src/auth.ts` — Clerk JWKS verification.
- `api/src/canonical.ts` — beat-manifest, detection and selection revisions.
- `worker/duckclean_worker/app.py` — FastAPI probe, proxy + poster, dissect,
  detect, cancel.
- `worker/duckclean_worker/media.py`, `dissect.py`, `detect.py` — ffmpeg facts,
  scene pass and beat planner, OCR/track/group/mask pipeline.
- `web/src/App.tsx` — library, upload, playback and a detection summary panel.

No render, preview or billing code exists yet, and no screen shows progress that
is not real. Missing models are reported (`logo_model_available: false`), never
silently skipped.

## Layout

```
web/        Vite + React + TypeScript SPA (Cloudflare Pages)
api/        Cloudflare Worker + Hono, migrations, OpenAPI, contract tests
worker/     Python CPU/GPU worker: FastAPI probe, proxy, poster, HMAC
engine/     Ported Classic engine, added deliberately, no Classic routes
infra/      R2 CORS and account setup helpers
docs/       Product plan, roadmap, detection report, contract, infrastructure
```

Video bytes never pass through `web/` or `api/`. The browser uploads directly to
R2 with a presigned URL and downloads through a signed URL.

## Branch

Standalone orphan branch `duckclean` in
`github.com/ducpa1912/vibecut`. It shares no history with `classic` or `main`.
Push only to `origin/duckclean`.

## Requirements

- Node 22+ (`.nvmrc`), npm 10+
- Python 3.11+ (the worker image is `python:3.11-slim`)
- ffmpeg on the worker host only; not needed for the contract checks

## Local setup

```bash
make setup          # npm install + .venv + worker[dev]
make check          # lint, typecheck, tests, build
```

Everything below runs without a Cloudflare account: `npm run dev:db` serves
Postgres from PGlite on `:5432`, `npm run dev:s3` runs MinIO on `:9000`, and the
API presigns against `R2_ENDPOINT` when `APP_ENV` is not `production`. Detection
needs the OCR extra: `pip install -e 'worker[ocr]'`.

The cloud path still needs live Clerk, Postgres and R2 credentials. Read
`docs/duckclean/infrastructure.md` before starting the API against the cloud.

```bash
cp api/.dev.vars.example api/.dev.vars
cp web/.env.example web/.env.local
cp worker/.env.example worker/.env
# fill Clerk, Postgres and R2; keep both HMAC secrets identical

npm run m1:doctor               # missing env, local/cloud mode, live health
npm run dev:db                  # PGlite Postgres on :5432, applies migrations
npm run dev:s3                  # MinIO on :9000 with the media bucket + CORS
npm run dev:web                 # Vite on :5173, proxies /api to :8787
npm run dev:api                 # wrangler dev on :8787
cd worker && set -a && source .env && set +a && ../.venv/bin/uvicorn duckclean_worker.app:app --port 8799
```

Individual tests:

```bash
npm run test --workspace api    # PGlite migrations + OpenAPI + revisions
.venv/bin/python -m pytest worker/tests
```

`api/wrangler.toml` contains a zero Hyperdrive ID and a placeholder Clerk
issuer until the real resources exist. The UI shows an honest setup state when
Clerk is not configured; it never fakes sign-in.

## Checks

| Command | Covers |
|---|---|
| `npm run lint:js` / `npm run format:js:check` | ESLint + Prettier |
| `npm run typecheck` | `web` and `api` (tests typechecked separately, without DOM/Worker leakage) |
| `npm run test --workspace api` | Migration against real Postgres (PGlite), OpenAPI structure, revision hashing, zod payloads |
| `ruff format --check worker` / `ruff check worker` | Python format and lint |
| `cd worker && mypy` | Strict Python types |
| `pytest worker/tests` | Worker contract and HMAC signing |

The migration test applies `0001_init.sql`, `0002_m1.sql` and `0003_m2.sql` to
Postgres and asserts the range rule, beat uniqueness, segment uniqueness and
ledger maths. It is not a mock. PGlite is used in CI; production uses a real
Postgres through Cloudflare Hyperdrive.

Known local-only artifact: `wrangler dev` runs the queue consumer in the same
isolate as HTTP, so the first request issued right after a job finishes can
return a one-off 500 ("code had hung"). Production runs the consumer in its own
invocation. `api/src/sql.ts` uses one connection per call in development so a socket never
crosses two request contexts; production keeps the pooled Hyperdrive client.
