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
| **Cloud Private** | team that wants its own server | managed container + URL | **$199/mo + $499 setup** | VM, storage, support | Build second |
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

### 4.4 Pricing

Starting assumption:

- **$199/month**, 4 vCPU / 16 GB / 250 GB, one concurrent render.
- **$499 setup** (provision, migrate, first project).
- Extra storage $0.20/GB/month.
- Extra render concurrency $49/month.
- Managed GPU clean billed at cost + 30%, or a $49/month add-on with a quota.

Gross margin target: 50–60% after VM, storage, backup and support.

### 4.5 Why not multi-tenant first

The app has one shared `VIBECUT_TOKEN`, one settings file and one job list.
Every route assumes one workspace. A public site would expose every customer's
videos. Tenancy is a code project: owner checks on every route, tenant IDs on
jobs/media, object storage isolation, auth, queue and billing. Private
instances avoid that risk while proving willingness to pay.

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
  └─ fill workers (GPU) or VOID API: Clean only
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

- VM 4 vCPU/16 GB: $50–$90/month.
- 250 GB + backup: $10–$20.
- Monitoring/support: $30–$50.
- Price $199 → 50–65% margin.

### Cloud Web

Per 90-second job:

| Cost | Low | High |
|---|---:|---:|
| CPU render | $0.10 | $0.40 |
| Clean (VOID) | $0.75 | $2.25 |
| Storage/egress | $0.05 | $0.15 |
| Payment fee | $0.30 | $0.50 |
| **Total** | **$1.20** | **$3.30** |

Charge $9–$12 → 65–85% margin before support.

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
| M2 | Cloud Private beta: image, auth edge, volume, backup, runbook | 3–4 weeks | One paying pilot |
| M3 | Paid launch: Mac + Private, website, docs, support | 2 weeks | 10 sales / 3 pilots |
| M4 | Multi-tenant Web: auth, tenancy, queue, billing, GPU clean | 8–12 weeks | 100 users, cost per job measured |

Do not start M4 before M3 metrics: activation, first render, repeat use,
support minutes per customer.

## 10. Risks and decisions

| Risk | Mitigation |
|---|---|
| Mac notarization fails on nested Python binaries | Sign inside-out; test on clean Mac early |
| GPL ffmpeg or TTS enters the DMG | `check_proprietary_deps.py` in CI; LGPL build |
| Model pack licenses drift | Pin hash + license per model; SBOM |
| ProPainter used commercially by mistake | Block it in the provider interface; document S-Lab |
| Private cloud leaks between customers | One instance per customer until tenancy ships |
| Apple Vision/Speech missing on Linux | Measure cloud OCR/STT before promising parity |
| GPU clean cost overruns | Quote before render; per-job budget alert |
| Piracy of the Mac app | Offline license + fair refunds; no heavy DRM |
| Support burden | Docs, in-app diagnostics, 48-hour email SLA |
| App Store rejection | Direct DMG only |

Open decisions for the founder:

1. Mac price: $149 Solo / $249 Studio, or a single $199 license?
2. Is a 1-year update window acceptable, with optional renewal?
3. Private Cloud at $199/month, or $299 with more support?
4. RaaS price: $0.12/render second with $9 minimum?
5. Is a Mac-only product enough for launch, with Cloud Private as a service?
