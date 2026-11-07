# DuckClean

Cloud-only removal of baked-in text, logos and burnt-in images from video.

Upload a full-length video, review what was detected, and get the whole video
back with the selected regions filled in. Rendering runs in the cloud, so a
phone can complete the entire flow.

`HANDOFF.md` is the binding brief. `docs/duckclean/contract.md` is the frozen M0
contract. If a doc disagrees with `HANDOFF.md`, the handoff wins.

## Status

M0 in progress: monorepo scaffold, lint/format, CI and the frozen contract.

- `api/migrations/0001_init.sql` — Postgres schema with the hard rules enforced
  by constraints.
- `api/openapi.yaml` — every route, ticket, error and payload.
- `api/src/schemas.ts` — zod mirror used by the Worker.
- `api/src/canonical.ts` — beat-manifest, detection and selection revisions.
- `worker/duckclean_worker/contract.py` — worker wire models and HMAC signing.

No upload, review or render code exists yet, and no screen shows progress that
is not real.

## Layout

```
web/        Vite + React + TypeScript SPA (Cloudflare Pages)
api/        Cloudflare Worker + Hono, migrations, OpenAPI, contract tests
worker/     Python CPU/GPU worker contract (FastAPI app lands with task 4)
engine/     Ported Classic engine, added deliberately, no Classic routes
docs/       Product plan, roadmap, detection report, frozen contract
```

Video bytes never pass through `web/` or `api/`. The browser uploads directly to
R2 with a presigned URL and downloads through a signed URL.

## Requirements

- Node 22+ (`.nvmrc`), npm 10+
- Python 3.11+ (the worker image is `python:3.11-slim`)
- ffmpeg on the worker host only; not needed for the contract checks

## Local setup

```bash
make setup          # npm install + .venv + worker[dev]
make check          # lint, typecheck, tests, build
```

Individual commands:

```bash
npm run dev:web                 # Vite on :5173, proxies /api to :8787
npm run dev:api                 # wrangler dev on :8787
npm run test --workspace api    # contract tests (PGlite + revision hashing)
.venv/bin/python -m pytest worker/tests
```

`api/wrangler.toml` points Hyperdrive at a local Postgres DSN; the API cannot
serve library or upload routes until one is running (task 3).

## Checks

| Command | Covers |
|---|---|
| `npm run lint:js` / `npm run format:js:check` | ESLint + Prettier |
| `npm run typecheck` | `web` and `api` (tests typechecked separately, without DOM/Worker leakage) |
| `npm run test --workspace api` | Migration against real Postgres (PGlite), OpenAPI structure, revision hashing, zod payloads |
| `ruff format --check worker` / `ruff check worker` | Python format and lint |
| `cd worker && mypy` | Strict Python types |
| `pytest worker/tests` | Worker contract and HMAC signing |

The migration test applies `0001_init.sql` to Postgres and asserts the range
rule, beat uniqueness, segment uniqueness and ledger maths. It is not a mock.
