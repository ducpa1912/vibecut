# Provider evaluation — auth, object storage, Postgres

Status: research note, 2026-11-07. List prices, USD, excluding tax. Every
number must be rechecked on the vendor page before purchase.

DuckClean's shape decides the winner:

- video is large and downloaded often, so **egress** dominates storage cost;
- auth is consumer/B2C, so per-MAU pricing decides the scale bill;
- metadata is small, so the Postgres bill is mostly compute and idle time;
- the API runs on Cloudflare Workers, so R2 and Hyperdrive remove moving parts.

"PostgREST" is the REST layer over Postgres, not the database. Supabase bundles
PostgREST. This note compares Postgres hosting, which is what the current schema
needs.

## Short answer

| Layer | Keep for M1 | Cheapest at scale | Avoid for this shape |
|---|---|---|---|
| Auth | **Clerk free** (50k MRU) | **WorkOS AuthKit** (1M MAU free) or **Better Auth** self-hosted | Auth0, Cognito at small scale |
| Video storage | **Cloudflare R2** | R2 for egress-heavy; B2 for storage-heavy; Hetzner if EU-only | S3, Supabase Storage, Wasabi for low volume |
| Postgres | **Neon free** | Neon Launch or Supabase Pro | Xata, RDS/Aurora at small scale |
| Compute | Cloudflare Workers Paid ($5) | same | leaving Cloudflare for M1 |

Recommended launch stack:

```text
Clerk free        $0        up to 50,000 monthly retained users
Neon free         $0        100 CU-hours + 1 GB per project
Cloudflare R2     ~$0-1     10 GB free, zero egress
Cloudflare Workers $5       required for Queues; Pages is free
HF CPU worker     $0-?       free CPU Space can sleep; GPU later
--------------------------------------------------------------
Total             ~$5/month before domain and worker GPU
```

At 100,000 users the auth line is the cliff. Clerk moves to roughly
**$1,025/month**; WorkOS AuthKit is **$0** up to 1M MAU, and Supabase Pro is
**$25/month** including 100k MAU. That is the point to switch auth, not storage.

## Auth

| Provider | Free | Paid entry | Marginal cost | Fit |
|---|---:|---:|---|---|
| **Clerk** | 50,000 MRU | Pro $25/mo ($20 annual) | ~$0.02 per MRU over 50k | Fastest React DX, prebuilt UI, custom domain included |
| **WorkOS AuthKit** | 1,000,000 MAU | $0 + usage | $2,500 per additional 1M ($0.0025/MAU) | Best marginal price at scale; custom domain $99/mo; SSO $125/connection |
| **Supabase Auth** | 50,000 MAU | Pro $25/mo | $0.00325/MAU over 100k | Best if Supabase is also the DB; bundles storage/PostgREST |
| **Firebase Auth** | 50,000 MAU | Blaze usage | $0.0055/MAU 50k–100k, $0.0046 100k–1M | Google lock-in; phone SMS extra |
| **Better Auth** | Unlimited | $0 framework | $0 licence; you pay DB/server | Cheapest long-term; you own security, patches, UI |
| **Logto Cloud** | 50,000 MAU | Pro $24/mo | Unlimited MAU, token-metered, $0.08/100 extra tokens | Cheap managed; MFA/branding add-ons |
| **Kinde** | 10,500 MAU | Pro $25/mo | $0.0175/extra MAU | Good DX; 0.7% transaction fee if using its billing |
| **Auth0** | 25,000 MAU | Essentials $35/mo for 500 MAU | ~$0.07/MAU; 50k ≈ $3,500/mo | Too expensive for B2C |
| **Cognito** | 10,000 MAU | Essentials | $0.015/MAU | Cheap-ish but AWS complexity; 50 SAML/OIDC free |
| **Stytch** | 10,000 MAU | usage | no hard caps; 5 SSO/SCIM free | Good B2B, weaker B2C price at 100k |

### Auth recommendation

- **Now:** stay on Clerk. It is already integrated, the free tier covers the
  first 50,000 retained users, and the custom domain is included. Moving auth
  now costs engineering time for no launch saving.
- **At ~50k–100k MRU:** benchmark **WorkOS AuthKit** and **Supabase Auth**.
  WorkOS is free to 1M MAU; if you need a branded custom domain it adds $99/mo,
  which is still cheaper than Clerk past roughly 54k MRU. Supabase Pro is $25
  and includes 100k MAU if you also want its Postgres and PostgREST.
- **At 1M MAU:** WorkOS is ~$0; Clerk is roughly $19,000/month. Better Auth is
  $0 in licence but you own the auth runtime.
- **Do not** move to Auth0 or Cognito to save money at this stage. Auth0 is
  more expensive; Cognito is cheaper than Clerk at 100k but WorkOS and Supabase
  beat it, and Cognito adds AWS operational weight.

## Object storage

Video egress is the bill. Storage price is secondary.

| Provider | Storage | Egress | Free | Notes |
|---|---:|---|---|---|
| **Cloudflare R2** | $0.015/GB-mo | **$0** | 10 GB, 1M Class A, 10M Class B | Best for video and Workers; S3-compatible |
| **Backblaze B2** | $0.00695/GB-mo ($6.95/TB) | Free up to 3× stored, then $0.01/GB | 10 GB, free API calls | Cheapest storage-heavy; S3-compatible |
| **Hetzner** | €6.49/mo includes 1 TB; extra €6.26/TB | €1/TB after 1 TB included | No permanent free tier | EU-only; cheapest EU storage+egress |
| **Wasabi** | $0.0078/GB-mo ($7.99/TB) | Free ≤ 1× stored | Trial only | 1 TB minimum, 90-day minimum; bad for small/variable |
| **Amazon S3** | ~$0.023/GB-mo | ~$0.09/GB | 5 GB, 12 months | Do not use for video egress |
| **Supabase Storage** | $0.0213/GB-mo | $0.09/GB uncached, $0.03 cached | 1 GB; Pro includes 100 GB + 250 GB egress | Fine for avatars, not video |

### Storage recommendation

- **Keep R2.** Zero egress is the defining feature for a product that returns
  video files. It is already integrated with the Worker signer.
- **Backblaze B2** wins when stored bytes are high and egress is low (for
  example, archives or source masters). It is not better for a clip that is
  downloaded several times.
- **Hetzner** wins only if EU-only residency is acceptable and storage is large;
  it is not a US/global first choice.
- **Wasabi** does not fit early DuckClean: 1 TB minimum and a 90-day minimum
  storage duration fight a small, changing library.
- **S3 and Supabase Storage** lose on video egress. Use them only if the file is
  small and already in that stack.

Example: 1 TB stored and 10 TB downloaded

| Provider | Approx. monthly |
|---|---:|
| R2 | ~$15 storage + $0 egress |
| B2 | ~$7 storage + 7 TB × $0.01/GB ≈ $77 |
| Hetzner | ~€16 (~$18) with 1 TB egress included + 9 TB × €1 |
| S3 | ~$23 storage + 10 TB × $90/TB ≈ $923 |

At 10 TB stored and 1 TB downloaded, B2 (~$70) beats R2 (~$154); at high egress,
R2 wins. Model the ratio, not the headline storage rate.

## Postgres

| Provider | Free | Paid entry | Notes |
|---|---:|---:|---|
| **Neon** | 100 CU-hours + 1 GB per project; 100 projects | Launch $0.106/CU-hour + $0.35/GB-mo | Scale-to-zero; best idle/bursty cost; vanilla Postgres |
| **Supabase** | 500 MB, 2 projects, pauses after 1 week idle | Pro $25/mo (8 GB, 100k MAU, 250 GB egress) | Bundles Auth, Storage, PostgREST; best one-bill option |
| **Railway** | 30-day $5 trial, then ~$1/mo | Hobby $5 minimum; Postgres as a service | Good if app+DB in one place; egress $0.05/GB |
| **Render** | Free Postgres expires after 30 days | $6/mo 256 MB; $19/mo 1 GB | Free is not production; storage $0.30/GB |
| **DigitalOcean** | None | $15.15/mo 1 GB | Predictable flat price |
| **PlanetScale** | None | $5/mo single node | Cheap fixed instance; check Postgres feature limits |
| **Cloudflare D1** | 5 GB, 5M rows/day | Workers Paid $5 | SQLite, not Postgres; would require schema rewrite |
| **Turso** | 5 GB, 500M reads | $4.99/mo | SQLite, not Postgres; cheap for edge SQLite |
| **Xata** | No permanent free; 14-day trial | ~$9/mo + $0.28/GB | Branching-focused; not cheapest for this app |
| **AWS RDS/Aurora** | Credits only | Instance-hour + storage | Not cheapest at small scale; operational weight |

### Postgres recommendation

- **Keep Neon free for M1.** It is vanilla Postgres, works through Hyperdrive,
  and scales to zero when nobody uses it. Move to Launch when the free
  CU-hours or 1 GB storage stop fitting; there is no migration.
- **Supabase Pro ($25)** is the best "one bill" alternative: it includes
  Postgres, Auth, PostgREST and 100k MAU. Keep video on R2, not Supabase
  Storage.
- **Railway ($5)** is the cheapest always-on small app+DB bundle if you also
  want to run the Worker or a container there.
- **Render free Postgres is not production** because it expires after 30 days.
- **Do not move to D1/Turso** for M1. The schema uses Postgres-only features
  (JSONB, generated columns, triggers, `gen_random_uuid`), and the Worker code
  is written against Postgres.

## All-in-one options

| Stack | Price | What you get | Why not |
|---|---:|---|---|
| **Supabase Pro + R2** | $25 + R2 | Postgres, Auth, PostgREST, 100k MAU, 100 GB storage, 250 GB egress | Video egress must stay on R2; project-level pause on Free |
| **Firebase** | $0 to start | Auth, Firestore, Storage | Storage egress and Google lock-in; no Postgres |
| **Clerk + Neon + R2** | ~$5 | Best-of-breed, already integrated | Three vendors; auth cliff at 50k |
| **WorkOS + Neon + R2** | ~$5–35 | 1M MAU free; vanilla Postgres; zero egress | Custom domain $99/mo; more auth rework |
| **Better Auth + Neon + R2** | ~$5–35 | No per-user auth fee; own the data | You own auth security, UI, patches |
| **Self-hosted Supabase/PocketBase** | ~$5 VPS | Full control | You own backups, upgrades, uptime |

## Cost scenarios

Assumptions: list prices, 1,000 / 100,000 / 1,000,000 MAU, video on R2,
Cloudflare Workers Paid for Queues. Domain and GPU worker excluded.

| Workload | Clerk + Neon + R2 | WorkOS + Neon + R2 | Supabase Pro + R2 | Better Auth + Neon + R2 |
|---|---:|---:|---:|---:|
| 1k MAU, 50 GB stored, 500 GB egress | ~$6 | ~$6 | ~$31 | ~$6 |
| 100k MAU, 1 TB stored, 10 TB egress | ~$1,060 | ~$34 (or ~$133 with custom domain) | ~$45 | ~$34 |
| 1M MAU, 10 TB stored, 100 TB egress | ~$19,260 | ~$259 | ~$3,108 | ~$259 |

The 100k row is the decision point. The 1M row shows why per-MAU auth pricing
matters more than a few dollars of storage.

## What to change in DuckClean

### Keep

- R2 signer, presigned PUT/GET, bucket layout.
- Neon Postgres and Hyperdrive; `DATABASE_URL` is portable.
- Cloudflare Pages + Workers + Queues.
- Clerk for M1; it is a standard OIDC/JWKS integration.

### If switching auth

- **WorkOS AuthKit:** OIDC/JWKS, so the Worker verifier changes issuer/audience
  and the web swaps the Clerk SDK for WorkOS AuthKit. No database migration.
- **Supabase Auth:** JWT verification differs by signing key; use the
  Supabase JWKS/secret and swap the web SDK. Users live in Supabase's `auth`
  schema, not `users`.
- **Better Auth:** runs in the Worker or a small auth service against the same
  Postgres; no external issuer. More code, no per-MAU fee.
- In all cases, keep `users.oauth_subject` as the local join and do not trust
  client-supplied identity.

### If switching storage

- **B2:** S3-compatible; change the signer endpoint/region and bucket. Keep the
  same keys and presigned flow.
- **Hetzner:** S3-compatible; EU endpoint; same signer changes.
- **Supabase Storage:** different auth model and signed-URL flow; only worth it
  for small files, not video.

### If switching Postgres

- **Neon → Supabase/other Postgres:** run the two migrations, change the
  Hyperdrive connection string. The schema is vanilla Postgres.
- **Postgres → D1/Turso:** rewrite migrations and queries. Do not do this for
  M1.

## Final recommendation

1. **Ship M1 on Clerk free + Neon free + R2 + Workers Paid.** About **$5/month**
   before domain and GPU.
2. **Keep R2.** It is the correct storage for video egress, and the code already
   uses it.
3. **Do not switch auth yet.** Re-evaluate at 50k MRU; then WorkOS AuthKit is
   the cheapest managed option at scale, Supabase Pro is the cheapest bundled
   option, and Better Auth is the cheapest ownership option.
4. **Do not switch Postgres yet.** Neon free is enough for M1 and Launch is
   usage-priced with no minimum.
5. **Do not use S3, Supabase Storage or Wasabi for video.** Their egress or
   minimums lose to R2 at DuckClean's shape.

## Sources

- Clerk: https://clerk.com/pricing
- WorkOS: https://workos.com/pricing
- Supabase: https://supabase.com/pricing
- Neon: https://neon.com/pricing
- Cloudflare R2: https://developers.cloudflare.com/r2/pricing/
- Cloudflare Workers: https://developers.cloudflare.com/workers/platform/pricing/
- Backblaze B2: https://www.backblaze.com/cloud-storage/pricing
- Hetzner Object Storage: https://www.hetzner.com/storage/object-storage/
- Wasabi: https://wasabi.com/pricing
- Auth0: https://auth0.com/pricing
- Amazon Cognito: https://aws.amazon.com/cognito/pricing/
- Firebase: https://firebase.google.com/pricing
- Better Auth: https://better-auth.com/pricing
- Logto: https://logto.io/pricing
- Kinde: https://kinde.com/pricing
- Railway: https://railway.com/pricing
- Render: https://render.com/pricing
- DigitalOcean: https://www.digitalocean.com/pricing/managed-databases
- Turso: https://turso.tech/pricing
- Xata: https://xata.io/pricing
