# DuckSuite commercial plan

Date: 2026-11-07
Status: active
Product: **DuckSuite for Mac**
Supersedes: VibeCut $249, direct DMG, Cloud Private and hosted-tenant pricing
Related: `DISTRIBUTION.md`, `../PRODUCT.md`, `../ROADMAP.md`

## 1. Offer

| Offer | Price | What the buyer gets |
|---|---:|---|
| **DuckSuite app** | **$29 one-time** | All local v1 tools; 1.x bug fixes and macOS compatibility |
| **DuckSuite Render** | **$5/month** | 10 CPU render hours, 1080p, up to 3 concurrent |
| **DuckSuite Render Plus** | **$20/month** | 10 GPU render hours, 1080p, up to 3 concurrent — after the GPU gate |
| **CPU overage** | **$0.50/hour** | No auto-charge |
| **GPU overage** | **$2.50/hour** | No auto-charge |

**Render hour = one hour of worker wall-clock, not one hour of finished video.** The app shows an output estimate from measured speed.

No unlimited plan. No hidden fair-use cap. No automatic overage.

## 2. Local-first economics

Local rendering is not metered. The $29 sale is the product.

- No account.
- No cloud dependency.
- No per-clip fee.
- No watermark.
- Optional cloud render is a separate subscription, not a gate on local work.

## 3. Cloud render unit economics

Current assumptions, to be measured:

| Plan | Net after Apple | Worker cost | Storage/broker/support | Margin |
|---|---:|---:|---:|---:|
| $5 CPU, 10 h | ~$4.25 | $0.30 at CPU Upgrade $0.03/h | ~$1.50 | ~$2.35 |
| $20 GPU, 10 h T4 | ~$17.00 | $4.00 at T4 $0.40/h | ~$2.00 | ~$10.50 |
| $20 GPU, 10 h L4 | ~$17.00 | $8.00 at L4 $0.80/h | ~$2.00 | ~$6.50 |
| $5 GPU, 10 h T4 | ~$4.25 | $4.00 | ~$1.50 | **negative** |

Rules:

- $5 is CPU only.
- GPU starts at $20.
- GPU Render Plus launches only if it is **>2× faster** than CPU and costs **<$0.50 per 90 s render**.
- Free CPU is a launch tier, not a permanent promise.
- Failed or cancelled cloud jobs do not consume hours.
- No refund after the user cancels a job that already started; state this before queueing.

## 4. Product family pricing

| Product | Buyer | Price | Notes |
|---|---|---|---|
| **DuckSuite** | Mac creator | $29 one-time | Offline app; optional Render |
| **DuckClean** | One finished video, old text | Free trial; paid CPU; Express waitlist | Ships from the **Classic lane** |
| **DuckClassic** | Operator or automation buyer | Credits | Cloud clean/quick, API, templates |
| **DuckStudio** | Non-Mac creator or team | Subscription or credits | Full cloud suite |

DuckClean is not a DuckSuite feature. It is a separate Classic-lane product.

## 5. Upgrade paths

- DuckSuite → Render subscription: only when the user chooses cloud render.
- DuckSuite → DuckClean: only if the user has one finished video and no timeline need.
- DuckClean → DuckClassic: when the user needs API, templates or batch.
- DuckClassic → DuckStudio: when the user needs a full cloud suite.

No ads inside DuckSuite. One “More from Duck” item in Help when the other products are live.

## 6. Refunds and updates

- App Store handles refunds for the $29 app and Render subscriptions.
- $29 includes 1.x bug fixes and macOS compatibility.
- New feature packs may be paid later. Do not promise free 2.0.
- No fake discounts, countdowns, pre-checked annual plans or dark patterns.

## 7. Costs to measure before launch

- Real CPU render cost per 90 s on HF/Beam.
- Real GPU render cost per 90 s on T4/L4.
- Cold start and queue time.
- Payment/StoreKit fees.
- Support time per sale.
- Refund rate.
- Storage and egress per active user.
