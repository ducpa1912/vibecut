# DuckClean infrastructure

Status: M1 code is complete. No live cloud resource is provisioned yet. This
document separates what exists in the repo from what must be created in an
account.

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

- This repo currently uses `@clerk/clerk-react` (the Clerk Core 2 package).
- Current Clerk React docs use `@clerk/react`. Moving to it is a dependency and
  import swap, not an architecture change.
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

## Local M1

1. Copy `api/.dev.vars.example` to `api/.dev.vars`; fill Clerk, Postgres, R2.
2. Copy `web/.env.example` to `web/.env.local`; fill the Clerk publishable key.
3. Run migrations against the Postgres in `localConnectionString`.
4. Start the API: `npm run dev:api`.
5. Start the worker: `cd worker && ../.venv/bin/uvicorn duckclean_worker.app:app --port 8799`.
6. Start the web: `npm run dev:web`.
7. Open `http://127.0.0.1:5173` and upload one real clip.

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
- M1 does not detect text yet; detection and beats are M2.
- `wrangler.toml` still contains a zero Hyperdrive ID and placeholder Clerk
  issuer until the resources exist.
