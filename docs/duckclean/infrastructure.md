# DuckClean infrastructure

Status: M1 and M2 code is complete. No live cloud resource is provisioned yet.
This document separates what exists in the repo from what must be created in an
account, and how to run the whole pipeline locally without any of it.

Run `npm run m1:doctor` to check local env files, Wrangler auth and live health
without printing secrets.

Provider alternatives are in [`providers.md`](./providers.md). Hosting and
worker cost at three scales is in [`cost-model.md`](./cost-model.md).

## The four services, plainly

| Service | What it is | Not |
|---|---|---|
| **Clerk** | Hosted identity provider. It runs Google/Apple/email sign-in, issues a session JWT, and publishes JWKS keys. | Not a database. It does not store videos or jobs. |
| **Postgres** | The metadata database: users, library items, sources, jobs, usage. | Not a video store. Videos never go here. |
| **Cloudflare R2** | S3-compatible object storage for source video, proxies, posters, masks, beat clips and outputs. | Not the API and not a CDN for the SPA. |
| **Cloudflare Hyperdrive** | A connection pooler/cache in front of Postgres for Workers. | Not a database. It points at a real Postgres. |

The API Worker talks to all four. The browser uploads video bytes directly to
R2 with a presigned PUT. The worker reads source bytes from R2 and writes the
proxy and poster back to R2.

## Current state

| Resource | Current state | Where it is configured |
|---|---|---|
| Git branch | Pushed at `origin/duckclean` | `github.com/ducpa1912/vibecut` |
| Frontend | Built, not deployed | `web/`, targets Cloudflare Pages |
| API Worker | Code and tests, not deployed | `api/`, `wrangler.toml` |
| Clerk | **Not configured.** Placeholder issuer | `CLERK_ISSUER`, `VITE_CLERK_PUBLISHABLE_KEY` |
| Postgres | **Not provisioned.** Tests use PGlite in memory | Hyperdrive binding + `localConnectionString` |
| R2 | **Not created.** Bucket name is a placeholder (`duckclean-media`) | R2 binding + R2 S3 secrets |
| Queues | **Not created.** Names only | `wrangler.toml` |
| CPU worker | Code and tests, not deployed; runs probe/proxy and LaMa clean | `worker/`, `CPU_WORKER_URL` |
| GPU worker | Not built past the contract; only ProPainter/generative | Later milestone |
| Pages | Not deployed | Later milestone |
| Claude/Cloudflare auth | `wrangler` is **not logged in** on this machine | `npx wrangler login` |
| Docker / local Postgres | Not installed on this machine | Use Neon or Homebrew Postgres |

No secret is committed. `api/.dev.vars` and `web/.env.local` are gitignored.

## What "R2" means here

The bucket is named **`duckclean-media`**. The binding is `MEDIA`; the signer
uses `R2_BUCKET`.

Keys:

```text
u/{user_id}/src/{asset_id}/source.{ext}
u/{user_id}/src/{asset_id}/proxy.mp4
u/{user_id}/src/{asset_id}/poster.jpg
u/{user_id}/detect/{run_id}/mask/{mask_id}.png
u/{user_id}/render/{job_id}/beat/{index}.mp4
u/{user_id}/render/{job_id}/final.mp4
```

The API signs `PUT` and `GET` URLs with an R2 S3 token. The browser never gets
the token.

## Provisioning order

### 1. Cloudflare account and Wrangler

```bash
npx wrangler login
npx wrangler whoami
```

### 2. Clerk

1. Create a Clerk application.
2. Enable Google, Apple and email link as needed.
3. Open **API keys** in the Clerk dashboard (older dashboards:
   **Developers → API keys**).
4. Copy the **Publishable key**, for example `pk_test_...`. This is the Vite
   key. Put it in `web/.env.local` as `VITE_CLERK_PUBLISHABLE_KEY`.
5. Copy the **Frontend API URL**, for example
   `https://your-app.clerk.accounts.dev`. Put it in `api/.dev.vars` as
   `CLERK_ISSUER`.
6. Add `http://localhost:5173` and `http://127.0.0.1:5173` to Clerk's allowed
   origins.
7. Default session tokens have no `aud`. Leave `CLERK_AUDIENCE` empty for M1.
   If you create a JWT template that adds an audience, set both
   `CLERK_AUDIENCE` and `VITE_CLERK_JWT_TEMPLATE`.
8. Restart `npm run dev:web` after changing the env file.

Only variables prefixed with `VITE_` reach the browser. The publishable key is
public by design. **Never put the Clerk secret key (`sk_...`) in a `VITE_`
variable.**

### Clerk is not Next.js-only

DuckClean is **React + Vite**. Vite is the bundler, not a framework; Clerk's
React SDK works in a Vite SPA, and Next.js is not required.

- This repo uses the current `@clerk/react` package with Vite.
- The deprecated `@clerk/clerk-react` package is not used.
- Clerk also ships SDKs for Next.js, React Router, Astro, TanStack React Start,
  Vue, Nuxt, Expo, Electron, Android and iOS. DuckClean uses only the React one.

The Vite key is the Clerk publishable key, not a Vite-generated key. It starts
with `pk_test_` in development and `pk_live_` in production.

### 3. Postgres

Use Neon, Supabase, or local Postgres. Hyperdrive only pools the connection; it
does not create the database.

Neon example:

```bash
export DATABASE_URL='postgres://user:password@host/db?sslmode=require'
psql "$DATABASE_URL" -f api/migrations/0001_init.sql
psql "$DATABASE_URL" -f api/migrations/0002_m1.sql
```

Local Postgres example:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb duckclean
psql duckclean -f api/migrations/0001_init.sql
psql duckclean -f api/migrations/0002_m1.sql
```

Create Hyperdrive:

```bash
npx wrangler hyperdrive create duckclean \
  --connection-string="$DATABASE_URL"
```

Copy the returned ID into `api/wrangler.toml`:

```toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "<returned-id>"
localConnectionString = "<local or Neon DSN>"
```

### 4. R2

```bash
npx wrangler r2 bucket create duckclean-media
npx wrangler r2 bucket cors set duckclean-media --file infra/r2-cors.json
```

Create an R2 API token with **Object Read & Write** on this bucket. Set:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET=duckclean-media
```

Add the production Pages origin to `infra/r2-cors.json` before deploying.

### 5. Queues

```bash
npx wrangler queues create duckclean-jobs
npx wrangler queues create duckclean-jobs-dlq
```

The consumer is the same Worker; `api/src/index.ts` exports both `fetch` and
`queue`.

### 6. Worker

Local:

```bash
cp worker/.env.example worker/.env
# keep DUCKCLEAN_HMAC_SECRET identical to WORKER_HMAC_SECRET in api/.dev.vars
cd worker
set -a; source .env; set +a
../.venv/bin/uvicorn duckclean_worker.app:app --port 8799
```

Then set `CPU_WORKER_URL=http://127.0.0.1:8799` and the same
`WORKER_HMAC_SECRET` in `api/.dev.vars`.

Remote:

- `worker/Dockerfile` and `worker/README.md` make `worker/` a Hugging Face
  Docker Space (port 7860, ffmpeg included).
- Set `DUCKCLEAN_HMAC_SECRET` in the Space settings.
- Set `CPU_WORKER_URL` to the HTTPS Space URL.
- Keep the same HMAC secret in the API Worker and the worker.

### 7. API Worker secrets and deploy

```bash
cd api
npx wrangler secret put CLERK_ISSUER
npx wrangler secret put WORKER_HMAC_SECRET
npx wrangler secret put R2_ACCOUNT_ID
npx wrangler secret put R2_ACCESS_KEY_ID
npx wrangler secret put R2_SECRET_ACCESS_KEY
npx wrangler deploy
```

`CLERK_ISSUER`, `WORKER_HMAC_SECRET` and the R2 keys are secrets. Non-secret
values live in `wrangler.toml`.

### 8. Pages

```bash
VITE_CLERK_PUBLISHABLE_KEY='pk_test_...' \
VITE_API_BASE_URL='https://api.example.com/api/v1' \
  npm run build

npx wrangler pages deploy web/dist --project-name duckclean
```

Add the Pages origin to `ALLOWED_ORIGINS` in `api/wrangler.toml` and to R2 CORS.
The API and Pages are different origins, so CORS must include the exact origin.

## Local development without Cloudflare

No account is needed to run the real pipeline. Two dev-only seams:

- **Postgres** — `npm run dev:db` starts PGlite on `127.0.0.1:5432` and applies
  every `api/migrations/*.sql` once (tracked in `dev_schema_migrations`). Point
  `localConnectionString` in `api/wrangler.toml` at
  `postgres://duckclean:duckclean@127.0.0.1:5432/duckclean`.
- **R2** — `npm run dev:s3` starts MinIO on `:9000`, creates the `duckclean-media`
  bucket and sets CORS for the Vite origins. Set `R2_ENDPOINT`,
  `R2_REGION=us-east-1` and local credentials in `api/.dev.vars`. The API refuses
  this override when `APP_ENV=production`.

`npm run dev:db` must be restarted after a new migration file is added; it
applies only migrations it has not recorded.

Order:

1. `npm run dev:db`, `npm run dev:s3`
2. `pip install -e 'worker[ocr]'` once, so `/v1/detect` has the OCR model
3. `npm run dev:api` (wrangler dev on `:8787`)
4. `cd worker && set -a && . ./.env && set +a && ../.venv/bin/uvicorn duckclean_worker.app:app --port 8799`
5. `npm run dev:web` and open `http://127.0.0.1:5173`

Clerk is still the sign-in path; local runs verify a token minted against a
local JWKS via `AUTH_JWKS_JSON` (development only, ignored in production).

`wrangler dev` shares one isolate between HTTP and the queue consumer, so the
first request right after a job finishes can return a one-off 500. Retrying is
the honest workaround; production isolates the consumer.

## Local M1/M2 acceptance (proven on this machine)

- Real MP4 → presigned PUT to MinIO → HEAD verify → probe → 720p proxy → ready.
- Dissection: one 1.5 s clip → one beat `[0, 12)` at 8 fps; hash frozen.
- Detection: 12/12 frames read, `DUCK` found, 29 groups, masks served as PNG.
- `logo_model_available: false` with `logo_model_unavailable`, never a silent
  skip.

## M1 acceptance

- A real phone uploads an MP4/MOV to R2 and the progress is byte-accurate.
- The API verifies the object with R2 HEAD; a wrong size is `upload_incomplete`.
- The worker probes the real file and writes a 720p proxy plus poster to R2.
- The library shows measured duration, resolution, frame rate, size and audio.
- Playback uses a short-lived signed R2 GET.
- No video byte passes through Pages or the API Worker.
- Missing Clerk, missing R2 and missing worker each show an honest state.

## Known gaps

- Clerk, R2, Postgres and Wrangler are not provisioned on this machine.
- The CPU worker is not deployed.
- The frontend is built but not deployed.
- Logo/watermark detection has no packaged model; every run reports
  `logo_model_available: false` and `logo_model_unavailable`.
- Detection has a per-run frame budget (`MAX_OCR_FRAMES = 600` in
  `worker/duckclean_worker/detect.py`). A longer source is reported as
  `truncated` with `frame_cap`; chunked runs are M3 work.
- A `wrangler dev` request that follows a finished job can return one 500.
- `wrangler.toml` still contains a zero Hyperdrive ID and placeholder Clerk
  issuer until the resources exist.
