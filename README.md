# DuckClean

Cloud-only removal of baked-in text, logos and burnt-in images from video.

Upload a full-length video, review what was detected, and get the whole video
back with the selected regions filled in. Rendering runs in the cloud, so a
phone can complete the entire flow.

`HANDOFF.md` is the binding brief. `docs/duckclean/contract.md` is the frozen M0
contract. `docs/duckclean/infrastructure.md` says exactly what Clerk, R2,
Postgres and Hyperdrive are, what exists, and what must be created.
`docs/duckclean/providers.md` compares current auth, storage and Postgres
prices. `docs/duckclean/cost-model.md` is the three-scale hosting and worker
cost model. If a doc disagrees with `HANDOFF.md`, the handoff wins.

## Status

M1 code complete: signed-in upload, direct-to-R2 transfer with real byte
progress, probe, 720p proxy + poster, library, and signed playback. The live
cloud is **not provisioned** yet.

- `api/migrations/0001_init.sql`, `0002_m1.sql` — Postgres schema with the hard
  rules enforced by constraints.
- `api/openapi.yaml` — every route, ticket, error and payload.
- `api/src/app.ts` — health, me, uploads, library, play.
- `api/src/jobs.ts` — DB-backed probe/proxy dispatch with signed worker calls.
- `api/src/auth.ts` — Clerk JWKS verification.
- `api/src/canonical.ts` — beat-manifest, detection and selection revisions.
- `worker/duckclean_worker/app.py` — FastAPI probe, proxy + poster, cancel.
- `web/src/App.tsx` — M1 library and upload surface, real states only.

No detection or render code exists yet, and no screen shows progress that is not
real. The phone upload flow is in place; the cloud resources are the next step.

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

M1 needs live Clerk, Postgres and R2 credentials. Read
`docs/duckclean/infrastructure.md` before starting the API.

```bash
cp api/.dev.vars.example api/.dev.vars
cp web/.env.example web/.env.local
# fill Clerk, Postgres, R2 and the worker secret

npm run m1:doctor               # missing env, Wrangler auth, live health
npm run dev:web                 # Vite on :5173, proxies /api to :8787
npm run dev:api                 # wrangler dev on :8787
cd worker && ../.venv/bin/uvicorn duckclean_worker.app:app --port 8799
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

The migration test applies `0001_init.sql` and `0002_m1.sql` to Postgres and
asserts the range rule, beat uniqueness, segment uniqueness and ledger maths.
It is not a mock. PGlite is used in CI; production uses a real Postgres through
Cloudflare Hyperdrive.
