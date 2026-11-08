# DuckClean cost model

Status: planning estimate, 2026-11-07. List prices, USD, excluding tax.
Recheck before purchase. The render line is the largest unknown and must be
measured on real clips.

This file covers **hosting and worker compute**. Auth, storage and Postgres
alternatives are in [`providers.md`](./providers.md).

## What the earlier model missed

The auth/storage/Postgres comparison priced the data plane but not:

- Cloudflare Workers requests and CPU time,
- Hyperdrive and Queues (bundled into Workers Paid, but the plan is not free),
- the CPU detection worker,
- the GPU render worker,
- video egress from non-R2 hosts.

At 1M MAU, the missing worker/egress lines move the estimate from a few hundred
dollars to roughly **$1.5k–2k/month** before auth. Clerk would add roughly
**$19k/month** more.

## Three scales

These are planning assumptions, not forecasts.

| Scale | MAU | Uploads/mo | Avg source | Stored | Egress/mo | GPU-engine renders/mo |
|---|---:|---:|---:|---:|---:|---:|
| Early | 1k | 100 | 2 min | 50 GB | 500 GB | 20 |
| Growth | 100k | 10k | 2 min | 1 TB | 10 TB | 2k |
| Scale | 1M | 100k | 2 min | 10 TB | 100 TB | 20k |

Worker assumptions:

- Detection: 3 CPU-minutes per upload.
- LaMa clean: CPU only. Its minutes add to the CPU line, not the GPU line.
- GPU fill: 5 GPU-minutes per clip that chooses ProPainter or generative fill.
- CPU upgrade: $0.03/hour.
- L4 GPU: $0.59/hour RunPod, $0.80/hour HF or Modal.
- One region, no retries, no peak concurrency, no model training.

## What subsidizes the bill

| Lever | What it covers | Limit |
|---|---|---|
| **Cloudflare Workers Paid $5** | 10M requests, 30M CPU-ms, Hyperdrive, Queues, Pages static | Requests and CPU overage; no video bytes |
| **HF CPU Basic** | 2 vCPU, 16 GB, 50 GB disk | Free, but sleeps after inactivity; 48h default |
| **Supabase Pro $25** | Postgres, Auth, PostgREST, 100 GB storage, 100k MAU | 1M MAU overage and $0.09/GB video egress |
| **Railway Hobby $5** | $5 of usage credit, app + Postgres in one bill | Memory billed while idle; egress $0.05/GB |
| **Cloudflare for Startups** | Up to $350k, $10k tier without funding | Credits expire; not a run rate |
| **AWS Activate** | $1k–$5k self-funded; up to $200k portfolio | Credits expire; AWS egress is expensive |
| **Google for Startups** | ~$2k start; up to $350k AI | Credits expire; GCP egress is expensive |
| **Microsoft for Startups** | Up to $150k Azure | Investor referral for large tiers |

The standard clean path uses **LaMa on CPU**, so a LaMa-only month can avoid the
GPU line entirely. GPU-engine renders are the clips that choose ProPainter or
generative fill.

The real subsidies at M1 are: Cloudflare bundles the DB proxy and queue into
$5, and HF CPU Basic is free. Neither survives heavy video egress or GPU work.

## What increases the bill

| Driver | Result |
|---|---|
| Video egress outside R2 | 100 TB costs ~$5k on Railway, ~$8.5k on AWS/CloudFront, ~$9k on Supabase, ~$15k on Vercel/Render |
| Always-on GPU | L4 at $0.80/hr is **$584/month** if left running; at $0.59/hr it is **$431/month** |
| Clerk above 50k MRU | ~$0.02/MRU; 1M MAU is ~$19k/month |
| Supabase above 100k MAU | $0.00325/MAU; 1M MAU is ~$2,925/month |
| Auth0 above 25k MAU | ~$0.07/MAU; 50k MAU is ~$3,500/month |
| Cognito above 10k MAU | $0.015/MAU |
| Always-on managed Postgres | Fly Basic $38/mo, DigitalOcean $15.15/mo, Render $6/mo; Neon can be $0 idle |
| Vercel/Render bandwidth | Vercel 1 TB included then $0.15/GB; Render 5 GB then $0.15/GB |
| Railway memory | Billed while the service is idle; $10/GB-month |
| Supabase Storage | $0.0213/GB-month and $0.09/GB uncached egress |

## Hosting archetypes

| Stack | Early | Growth | Scale | Notes |
|---|---:|---:|---:|---|
| **Cloudflare-first + WorkOS** | ~$6–30 | ~$150–210 | ~$1.4k–2.0k | Best steady-state; video on R2 |
| **Cloudflare-first + Clerk** | ~$6–30 | ~$1.2k | ~$20.4k | Auth cliff at 50k |
| **Supabase Pro + R2 + Workers** | ~$30–50 | ~$145–185 | ~$3.1k–4.3k | One bill at low scale; MAU cliff at 1M |
| **Railway + R2** | ~$14–25 | ~$160–220 | ~$1.5k–2.2k | App+DB bundle; no GPU; keep video on R2 |
| **Vercel + Neon + R2** | ~$25–40 | ~$100–250 + egress | ~$500–1.5k + egress | Frontend/functions only |
| **AWS/GCP/Azure + R2** | credits | credits | $1k+ + egress risk | Only with credits or enterprise need |

## Cloudflare-first detail

| Line | Early | Growth | Scale |
|---|---:|---:|---:|
| Pages static | $0 | $0 | $0 |
| Workers Paid | $5 | $5–15 | $10–45 |
| Queues | included | ~$0 | ~$0 |
| Hyperdrive | included | included | included |
| Neon | $0 | ~$14 | ~$90–150 |
| R2 storage | ~$0.60 | ~$15 | ~$190 |
| CPU worker | $0–22 | ~$15–30 | ~$150–300 |
| GPU render | ~$1 | ~$100 | ~$980–1,300 |
| **Total** | **~$6–30** | **~$150–210** | **~$1.4k–2.0k** |

Workers math:

```text
requests: max(0, requests - 10M) / 1M * $0.30
CPU:      max(0, cpu_ms - 30M) / 1M * $0.02
base:     $5
```

At 100M requests and 7 ms average CPU: `$5 + $27 + $13.40 = $45.40`.

## GPU sensitivity

At 20k **GPU-engine** renders/month, the GPU line depends entirely on measured
fill time. LaMa-only renders do not appear here; their cost is CPU time.

| GPU-min per render | GPU-hours/mo | At $0.59/hr | At $0.80/hr |
|---:|---:|---:|---:|
| 1 | 333 | $197 | $267 |
| 5 | 1,667 | $983 | $1,333 |
| 10 | 3,333 | $1,967 | $2,667 |
| 15 | 5,000 | $2,950 | $4,000 |
| 30 | 10,000 | $5,900 | $8,000 |

At 2k renders/month, divide by 10.

CPU sensitivity at 100k uploads/month:

| CPU-min per upload | CPU-hours/mo | At $0.03/hr |
|---:|---:|---:|
| 1 | 1,667 | $50 |
| 3 | 5,000 | $150 |
| 10 | 16,667 | $500 |

## GPU host comparison

| Provider | L4 | A100 80GB | Billing | Best use |
|---|---:|---:|---|---|
| **HF Spaces** | $0.80/hr | $2.50/hr | hourly | CPU Basic free for M1; GPU Space stays on unless sleep set |
| **RunPod** | $0.59/hr | $1.79/hr | per-second/hour | Cheapest on-demand L4 |
| **Modal** | $0.80/hr | $2.50/hr | per-second | Bursty render; $30/month free credits |
| **AWS/GCP/Azure** | higher | higher | per-second/minute | Only with credits or enterprise |

Recommendation:

- **M1:** HF CPU Basic, free. It may sleep; that is acceptable before render.
- **M5 GPU:** RunPod or Modal serverless for render. Keep HF for probe/proxy only if it remains free.
- Do not leave a paid GPU Space running idle. Set sleep, or use per-second serverless.

## Revised recommendation

1. **M1:** Cloudflare Pages + Workers Paid + Neon free + R2 + HF CPU Basic.
   **~$5–6/month**, or ~$28 if the CPU worker must stay awake.
2. **Growth:** move auth to WorkOS or Supabase before 50k Clerk MRU.
   Keep video on R2. Budget **~$150–250/month** including worker.
3. **Scale:** WorkOS + Neon + R2 + RunPod/Modal GPU.
   Budget **~$1.4k–2.0k/month** at the assumptions above.
4. **Do not move video to Vercel, Render, Railway, Supabase Storage, S3 or
   Wasabi.** Their egress or minimums dominate at 10–100 TB/month.
5. **Measure GPU-minutes per output minute before pricing the commercial plan.**
   That single number moves the 1M bill from ~$1.2k to ~$6k.

## Decision needed from real usage

Before locking price, measure:

- CPU-minutes per uploaded minute for probe + OCR + beat dissection.
- CPU-minutes per rendered output minute for LaMa.
- GPU-minutes per rendered output minute for ProPainter and generative fill.
- Percentage of uploads that actually need render.
- Average source duration and egress per user.

Without those four numbers, every plan is a range, not a quote.
