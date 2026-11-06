# Commercial packaging plan

Date: 2026-11-06
Status: decision draft
Supersedes the commercial sequence in `distribution-plan.md` and
`raas-distribution-plan.md`. The technical build and license details in those
documents still apply.

## 1. The rethink

Do not sell one product. Sell three shapes from one codebase, in this order:

1. **VibeCut Mac** — a signed, notarized Apple Silicon DMG. Local-first,
   one-time license, no account required.
2. **VibeCut Cloud Private** — a managed single-tenant instance. Same app, own
   volume, own URL. This is SaaS without the multi-tenant rewrite.
3. **VibeCut Web** — public multi-tenant, pay per render. Only after Private
   proves demand and the tenancy work is done.

Why this order:

- The current app is a single-process, single-workspace product. It is not
  multi-tenant. Selling a private instance is honest and ships now.
- The Mac buyer wants local files, offline work and a flat price. The hosted
  buyer wants no install and burst capacity. They are different offers.
- Public RaaS needs accounts, tenant isolation, a queue, GPU workers, billing
  and abuse controls. That is a separate engineering phase, not a packaging
  step.

Non-negotiable:

- Direct Developer ID DMG, **not** the Mac App Store.
- No Classic lane in the paid Mac bundle. Classic stays a separate beta product.
- No Demucs weights, GPL ffmpeg or GPL TTS phonemizer in the Mac app.
- Online clean uses a commercially licensed model. ProPainter is
  non-commercial; VOID is Apache-2.0. See § 6.

## 2. Product matrix

| Product | Buyer | Delivery | Starting price | Main cost | Status |
|---|---|---|---|---|---|
| **VibeCut Mac Solo** | solo creator | DMG, arm64 | **$149 one-time**, 1 year updates, 2 Macs | payment fee, support | Build first |
| **VibeCut Mac Studio** | small team | DMG, arm64 | **$249**, 1 year updates, 5 Macs | payment fee, support | Same build, license tier |
| **Cloud Private** | team that wants its own server | managed container + URL | **$199/mo + $299 setup** | shared 16-core host, storage, support | Build second |
| **Mac Native** | team that needs Apple OCR/STT | managed Mac mini | **$349/mo** | Mac mini M6, support | Optional premium |
| **Cloud Web / RaaS** | occasional creator | browser, per render | **$0.12/render second, $9 minimum**, or $29/mo with 5 min | CPU/GPU, clean API, storage, egress | Build third |

Prices are starting assumptions. Validate with 10 founder calls before launch.

Upgrade policy: 1 year of updates included; renewal optional. A license keeps
working after the update window. No feature is taken away from an owned build.

## 3. VibeCut Mac

### 3.1 Shape

- Apple Silicon only, arm64.
- macOS 14 Sonoma or newer. Test on macOS 26.
- SwiftUI + WKWebView shell, bundled Python sidecar on loopback.
- Random loopback port and per-launch bearer token.
- Single-instance lock.
- Data in `~/Library/Application Support/VibeCut`, never inside the `.app`.
- Quit kills the sidecar and its ffmpeg children.

### 3.2 What ships in the base DMG

Target: **under 450 MB compressed**.

| Component | Included | Why |
|---|---|---|
| Python 3.11 arm64 + FastAPI + static UI | yes | app runtime |
| ONNX Runtime + LaMa ONNX (198 MB) | yes | default AI fill |
| LGPL ffmpeg/ffprobe + VideoToolbox | yes | no GPL |
| Apple Vision/Speech helpers | yes | local OCR/STT on macOS |
| OpenCV (Telea/NS optional) | optional | small |
| STTN + PyTorch | no | optional 1.5–2 GB pack |
| Whisper / Kokoro / RoFormer | no | optional packs |
| Demucs | no | weights unresolved |
| ProPainter | no | non-commercial |

The `lean` build downloads LaMa on first run if the DMG must stay tiny.
The `offline` build includes LaMa so Clean works with the network off.

### 3.3 License and trial

- Ed25519-signed license file: product, edition, machine limit, update-until
  date, issued-to.
- Machine fingerprint: stable hash of hardware UUID + app install id.
- 14-day full trial. No watermark. After expiry, rendering is disabled; the
  app opens and shows the license panel.
- Offline verification. No phone-home to run. Optional activation endpoint for
  revocation and seat reset.
- 2 Macs for Solo, 5 for Studio. Deactivate a Mac from the license portal.
- Merchant of record: Paddle or Lemon Squeezy, so VAT/sales tax is handled.
- Refund: 14 days, no questions.

Do not build a heavy DRM system. A signed file and a fair refund policy is
enough for this buyer.

### 3.4 Updates

- Sparkle 2 with EdDSA-signed appcast.
- Stable and beta channels.
- Staged rollout: 10% → 50% → 100%.
- Delta updates optional; full ZIP first.
- Minimum OS and minimum core version in the appcast.
- Crash reports opt-in only. Logs stay local by default.

### 3.5 Signing and notarization

1. Build arm64 only.
2. Sign every nested binary: Python framework, `.so`/`.dylib`, ffmpeg,
   Vision/Speech helpers, then the `.app`.
3. Hardened runtime. Minimal entitlements: audio input if recording, network
   client/server for loopback, user-selected files.
4. `notarytool submit --wait`, `stapler staple`, `spctl --assess`.
5. Create a signed DMG with a drag-to-Applications layout.
6. Publish SHA-256, appcast, release notes and SBOM.
7. Test on a clean Mac with no Python, ffmpeg, Node or Xcode.

### 3.6 Build pipeline

GitHub Actions `macos-14` arm64 runner:

1. `pip install -r requirements.lock` into a clean venv.
2. Build the LGPL ffmpeg or fetch the pinned LGPL build; record `ffmpeg -L`.
3. `py2app` (preferred) or PyInstaller with the bootloader exception.
4. Build Swift helpers for arm64.
5. Copy EULA, `THIRD_PARTY_NOTICES.md`, `LICENSES/`, SBOM.
6. Run `scripts/check_proprietary_deps.py --all`.
7. Sign, notarize, staple, DMG, Sparkle ZIP, checksums.
8. Smoke test on a clean runner: launch, import, render 5 s, one LaMa fill.

### 3.7 Mac acceptance

- Gatekeeper passes on a clean Mac.
- No network needed for import, edit, render and Clean with the offline pack.
- No GPL binary in the bundle.
- License works offline; trial expiry disables render only.
- Update from previous version keeps jobs and settings.
- Uninstall leaves source files elsewhere untouched; app data can be removed
  from the app.

## 4. VibeCut Cloud Private

A managed single-tenant instance. This is the fastest route to SaaS revenue.

### 4.1 Shape

```text
Customer browser
   │ HTTPS + auth
   ▼
Caddy / ALB  ──►  VibeCut container (Studio, HOSTED profile)
                     ├── /data volume (jobs, edits, settings, shares)
                     ├── models volume
                     ├── CPU render workers
                     └── optional GPU fill worker or VOID API
```

- One customer, one container, one volume, one URL.
- 4 vCPU / 16 GB RAM / 250 GB SSD baseline.
- Daily volume backup to S3-compatible storage.
- Caddy TLS + OIDC or magic-link auth at the edge.
- No public port; admin via VPN or authenticated proxy.
- Pinned image digest; SBOM and notices shipped.

### 4.2 What the customer gets

- Their own URL, data and admin setup.
- Studio only. No Classic, no path import, no voice cloning.
- Import, Check, Moments, Edit, Clean, Captions, Audio, Render, Publish.
- Optional managed GPU clean or remote VOID.
- Updates handled by us; maintenance window stated.

### 4.3 Linux limits

Apple Vision and Apple Speech are macOS-only. On Linux:

- OCR: cloud OCR or a reviewed local OCR engine. Measure against Apple Vision.
- STT: cloud STT or Whisper on CPU/GPU. Measure.
- TTS: Apple `say` is unavailable; use cloud or a licensed local engine.
- Encoding: ffmpeg + hardware encoder where available.

Do not claim Apple-quality OCR on Linux until measured.

### 4.4 Hosting options

CPU-only fill changes the economics. MI-GAN is MIT (code and weights) and its
seed rate is 0.6 s per frame on CPU, versus 4.0 s for LaMa. A 90-second job can
therefore run on a cheap CPU host without a GPU. Prices below are the founder's
2026 quotes and must be rechecked.

| Host | Spec | Price | Role | Tenants |
|---|---|---:|---|---:|
| Contabo VPS Plus 6 | 6 vCPU EPYC, 12 GB, 300 GB NVMe | **$23/mo** | pilot / design partners | 1 |
| Contabo CPU 16 | 16 vCPU EPYC 7282, 64 GB, 480 GB NVMe | **$155/mo** | Private Standard | 3 isolated containers |
| Contabo dedicated | 24 × 2.5 GHz EPYC 9224, 128 GB, 2 × 1 TB SSD | **$240/mo** | scale / dedicated tier | 6–8 containers |
| Mac mini M6 | 16 GB, 256 GB | **$150/mo** | Mac Native | 1 |
| Mac mini M5 Pro | 24 GB, 512 GB | **$250/mo** | Mac Native Pro | 1 |

Sharing a 16-core host between three private containers is **isolated data,
shared compute**. Each container gets a CPU and memory limit. It is not a
dedicated SLA; sell it as shared compute and keep the dedicated tier for
customers who need guaranteed throughput.

### 4.5 Pricing

| Tier | Host | Price | Includes | Host cost per tenant |
|---|---|---|---:|---:|
| **Pilot** | VPS Plus 6 | **$49/mo** or free design partner | 720p, 1 project, 1 render at a time | $23 |
| **Private Standard** | 16-core host, 3 containers | **$199/mo + $299 setup** | 1080p, 1 render at a time, 100 GB | ~$52 |
| **Private Dedicated** | 24-core dedicated | **$499/mo + $499 setup** | 2K, 2 renders at a time, 500 GB, SLA | $240 |
| **Mac Native** | Mac mini M6 | **$349/mo** | Apple OCR/STT, VideoToolbox, 1080p | $150 |
| **Mac Native Pro** | Mac mini M5 Pro | **$449/mo** | 2K, 2 renders at a time, 512 GB | $250 |

Add-ons: extra storage $0.20/GB/month; extra concurrency $49/month; remote
clean billed at cost + 30%.

The $199 Standard price only works because three containers share a $155 host.
A one-tenant $199 instance on a $155 host leaves too little for support. If
sharing is not acceptable, the price is $299–$349.

### 4.6 CPU fill

- Default hosted fill: **MI-GAN** on CPU. MIT code and weights; 0.6 s/frame
  seed.
- Quality fallback: LaMa ONNX. Slower (4.0 s/frame seed), still CPU.
- STTN optional on CPU, 4.6 s/frame; use only when its subtitle quality wins.
- No GPU worker needed for the pilot or Standard tier.
- One fill at a time per container; separate containers can fill in parallel.
- Set `OMP_NUM_THREADS`/torch threads per container so three containers do not
  each spawn all cores.
- Remote VOID is a burst/quality option, not the default.
- Measure the real rate on the host before promising 25 minutes. The seed rates
  are starting estimates, not a benchmark.

### 4.7 Why not multi-tenant first

The app has one shared `VIBECUT_TOKEN`, one settings file and one job list.
Every route assumes one workspace. A public site would expose every customer's
videos. Tenancy is a code project: owner checks on every route, tenant IDs on
jobs/media, object storage isolation, auth, queue and billing. Private
containers avoid that risk while proving willingness to pay.

## 5. VibeCut Web / RaaS

Build only after Private has paying customers.

### 5.1 Flow

Sign in → upload → prepare → plan → quote → pay → render → download.

- Planning is capped by upload length and a free allowance.
- Quote is computed from the Edit: duration, shape, quality, clean spans.
- Payment freezes the Edit version and queues the render.
- Failed render refunds automatically.
- Output kept 7 days, signed download link.

### 5.2 Architecture

```text
Browser
  │
  ▼
API (HOSTED profile) ── Postgres: users, orgs, jobs, orders, credits
  │                   ── S3: sources, work copies, edits, outputs
  ├─ prepare workers (CPU): proxy, scenes, transcript, OCR
  ├─ render workers (CPU): ffmpeg
  └─ clean workers (CPU MI-GAN; GPU optional) or VOID API
```

Start with Postgres as the queue (`SKIP LOCKED`). Add Redis/SQS when measured.
One region. Autoscale render workers only.

### 5.3 Tenancy and security

- Owner check on every route, denied by default.
- `tenant_id` on jobs, media keys, edits, shares and artifacts.
- Resumable direct upload to object storage; no server path import.
- Per-tenant quotas: source length, storage, render minutes, clean seconds.
- FFmpeg jobs in a sandbox: no network, memory/time limits, local protocols only.
- Signed URLs; no public buckets.
- Secrets in a managed secret store; no provider keys in the image.
- Data deletion and export endpoints.

### 5.4 Pricing

- **Creator:** $29/month, includes 5 render minutes and 60 clean seconds.
- **Pay as you go:** $0.12 per render second, $9 minimum.
- **Clean add-on:** $0.03 per cleaned second (VOID cost + margin).
- **Team:** $99/month, 3 seats, 20 render minutes.

A 90-second render at 1080p costs roughly $0.50–$2.50 in compute and clean, so
the margin is healthy at $9–$12.

## 6. Licensing matrix for the paid builds

| Component | Mac DMG | Cloud Private | Cloud Web | Action |
|---|---|---|---|---|
| ffmpeg | LGPL + VideoToolbox | GPL server-side or LGPL | GPL server-side or LGPL | Record build and notices |
| LaMa | Apache-2.0, bundle | Apache-2.0 | Apache-2.0 | Include notice + hash |
| STTN | MIT code, Apache weights | same | same | Optional pack |
| VOID | not bundled | Apache-2.0 via fal or self-host | same | Online clean candidate |
| ProPainter | no | no | no | S-Lab 1.0 non-commercial; written license only |
| Demucs | no | no | no | weights unresolved |
| Kokoro + espeak | no | server-side only | server-side only | GPL phonemizer review |
| MusicGen / Stable Audio | no | no | no | non-commercial / threshold |
| xhs_get | no | separate process or no | no | GPL |
| Classic | no | no | no | separate beta lane |

Every artifact ships:

- EULA and privacy policy.
- `THIRD_PARTY_NOTICES.md`, `LICENSES/`, SBOM.
- Exact ffmpeg build and model hashes.
- A written source offer if any GPL binary is distributed.

## 7. Unit economics

### Mac

- Price $149. Payment fee ~5% → $7.45.
- Support 15 min per sale at $30/h → $7.50.
- Update bandwidth/S3 → under $1.
- Gross margin: roughly 85–90% before tax.

### Cloud Private

| Tier | Host cost | Other cost | Price | Margin before support |
|---|---:|---:|---:|---:|
| Pilot, 1 tenant | $23 | $5 backup | $49 | ~40% |
| Standard, 3 tenants on $155 host | $52/tenant | $15 | $199 | ~66% |
| Dedicated, 1 tenant on $240 host | $240 | $20 | $499 | ~48% |
| Mac Native, 1 Mac mini M6 | $150 | $10 | $349 | ~54% |

Support is the variable. Budget 20 minutes per customer per month; at $30/h
that is $10. Shared-host Standard has the best margin. The pilot is for
learning, not profit.

### Cloud Web

Per 90-second job, CPU-only MI-GAN:

| Cost | Low | High |
|---|---:|---:|
| CPU render + local MI-GAN | $0.10 | $0.40 |
| Remote VOID, optional | $0 | $2.25 |
| Storage/egress | $0.05 | $0.15 |
| Payment fee | $0.30 | $0.50 |
| **Total** | **$0.45** | **$3.30** |

Charge $9–$12 → 65–90% margin before support. The CPU-only path is the default;
remote VOID is a speed/quality add-on.

Do not offer unlimited renders. Do not include long source analysis free.

## 8. Release pipeline

### Mac artifacts

- `VibeCut-<version>-arm64.dmg`
- `VibeCut-<version>.zip` for Sparkle
- `appcast.xml`
- `SHA256SUMS`
- `sbom/`, `THIRD_PARTY_NOTICES.md`, `LICENSES/`

### Cloud artifacts

- `vibecut-api:<version>` and `vibecut-worker:<version>` images, digest-pinned.
- `docker-compose.private.yml` for single-tenant.
- Helm chart later, after Private.
- SBOM per image; model hashes; source-offer URL.

### Versioning

- App version: marketing (`1.0.0`).
- Core version: contract (`core.version.CORE_VERSION`).
- Feature versions: pinned per profile.
- A Mac update must not change the data schema without a migration and a
  rollback.

## 9. Milestones

| Phase | Work | Time | Gate |
|---|---|---|---|
| M0 | Price, license, merchant, supported macOS, hosted profile | 1 week | Founder sign-off |
| M1 | Mac DMG beta: sidecar, LaMa pack, signing, notarization, license, Sparkle | 4–6 weeks | Clean-Mac install + 10 founder runs |
| M2 | Cloud Private beta: image, auth edge, volume, backup, benchmark | 3–4 weeks | One 90 s job under 25 min on the $23 VPS; 3 tenants stable on the $155 host |
| M3 | Paid launch: Mac + Private, website, docs, support | 2 weeks | 10 sales / 3 pilots |
| M4 | Multi-tenant Web: auth, tenancy, queue, billing, CPU/GPU clean | 8–12 weeks | 100 users, cost per job measured |

Do not start M4 before M3 metrics: activation, first render, repeat use,
support minutes per customer.

## 10. Risks and decisions

| Risk | Mitigation |
|---|---|
| Mac notarization fails on nested Python binaries | Sign inside-out; test on clean Mac early |
| GPL ffmpeg or TTS enters the DMG | `check_proprietary_deps.py` in CI; LGPL build |
| Model pack licenses drift | Pin hash + license per model; SBOM |
| ProPainter used commercially by mistake | Block it in the provider interface; document S-Lab |
| Private cloud leaks between customers | One container per customer until tenancy ships |
| Contabo has no SLA and shares CPU | Pilot only; move paid Standard to a 16-core host or dedicated; monitor steal and latency |
| Three containers contend for CPU | Per-container CPU/memory limits; benchmark one tenant first |
| Mac mini host is a single point of failure | Backups + swap unit; premium price reflects it |
| Apple Vision/Speech missing on Linux | Measure cloud OCR/STT before promising parity; Mac Native tier for Apple-native |
| Clean cost overruns | CPU MI-GAN default; remote VOID only when quoted |
| Piracy of the Mac app | Offline license + fair refunds; no heavy DRM |
| Support burden | Docs, in-app diagnostics, 48-hour email SLA |
| App Store rejection | Direct DMG only |

Open decisions for the founder:

1. Mac price: $149 Solo / $249 Studio, or a single $199 license?
2. Is a 1-year update window acceptable, with optional renewal?
3. Private Standard: $199 with three containers on one host, or $299 with a
   dedicated slice? The first needs shared-compute wording.
4. Is the $23 VPS pilot for design partners only, or a paid $49 tier?
5. Mac Native at $349 on a $150 Mac mini: premium support or self-serve?
6. RaaS price: $0.12/render second with $9 minimum?
7. Is Mac + Private enough for launch, with Web/RaaS later?
