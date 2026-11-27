# DuckSuite distribution plan

Date: 2026-11-07
Status: active
Product: **DuckSuite for Mac**
Supersedes: VibeCut DMG, Cloud Private, and hosted-tenant distribution plans
Related: `COMMERCIAL.md`, `APPSTORE-READINESS.md`, `CLEAN-QUALITY-PLAN.md`, `../PRODUCT.md`, `../ROADMAP.md`

## 1. What DuckSuite is

An **offline macOS app** for one long video or one finished video:

```text
Import → Analyze → Edit → Render → Export
```

Local tools:

- Dissect: scenes, transcript, moments.
- Detect: on-screen text, faces, speech, music, quality.
- Clean: LaMa AI fill or explicit blur.
- Voice-over and dub: local voices, local translation.
- Edit: trim, split, reorder, reframe, captions, text, music.
- Render: 1080p, 24/30 fps.
- Export: MP4, SRT, cover.

No account. No telemetry. No upload unless the user chooses optional cloud render.

## 2. Distribution channel

Phase 1: **Mac App Store only.**

- macOS 26+.
- Apple Silicon.
- Paid upfront: **$29**.
- App Store handles payment, tax, refunds and updates.
- No Sparkle, no license key, no Ed25519 activation, no direct DMG in Phase 1.
- Direct DMG only if App Review rejects the bundled sidecar, and only after a separate decision.

## 3. App Store requirements

### Bundle

```text
DuckSuite.app/
  Contents/MacOS/DuckSuite
  Contents/Helpers/duckcore            # or Resources/duckcore
  Contents/Helpers/ffmpeg              # LGPL build
  Contents/Helpers/ffprobe
  Contents/Helpers/vision_probe
  Contents/Helpers/transcribe_apple
  Contents/Helpers/translate_apple
  Contents/Resources/base-models/lama_fp32.onnx
  Contents/Resources/static/duck/
  Contents/Resources/PrivacyInfo.xcprivacy
```

- Bundle Python, ONNX Runtime, LaMa, ffmpeg and prebuilt Swift helpers.
- No runtime `pip`, `swiftc`, `yt-dlp`, Homebrew or downloaded executable code.
- Optional packs are data only, with SHA-256 and signature.
- LGPL ffmpeg only. No libx264/x265 in the Mac bundle. Use VideoToolbox.

### Sandbox

- `com.apple.security.app-sandbox`
- `com.apple.security.network.client`
- `com.apple.security.network.server` (loopback only)
- `com.apple.security.files.user-selected.read-write`
- `com.apple.security.device.audio-input` only if recording voice-over

### Local server

- Bind `127.0.0.1:0`.
- 256-bit per-launch token.
- Token on every API route.
- No LAN access, no `0.0.0.0`, no query-string tokens.
- No docs/openapi/admin in the release build.

### Payments

- $29 is the App Store app price.
- Optional Render subscription uses StoreKit 2 auto-renewable products.
- `appAccountToken` maps an anonymous install to quota.
- Restore, manage subscription, refunds, grace period and revocation are handled.
- No external purchase link in v1.

### Privacy

- `PrivacyInfo.xcprivacy`.
- App Privacy label: local app collects nothing.
- Cloud render discloses user content and purchase history only when used.
- Name subprocessors if cloud render ships.
- No training, no sale, no tracking.

### Review risks

- Downloaded model that enables a core feature → bundle core models.
- Runtime Swift compilation → prebuild and sign helpers.
- GPL ffmpeg → LGPL build.
- License key or custom DRM → StoreKit only.
- Local server → review note explaining loopback and token.
- Watermark removal → own-footage notice; no platform-watermark marketing.

## 4. Updates

- App Store updates only.
- $29 includes 1.x bug fixes and macOS compatibility.
- New features may be paid updates or a later major version.
- No silent model replacement. A model update creates a new artifact ID; old renders stay playable.

## 5. Release gates

- Clean-Mac install without Terminal, Homebrew or network.
- Sandbox and local API token verified.
- StoreKit purchase, restore, cancel and manage subscription.
- 20 real clips: dissect, detect, clean, voice, dub, captions.
- 1080p 24/30 export on M1 8 GB.
- Privacy manifest and review notes.
- No downloaded code, no GPL ffmpeg.
- App Review approved.

## 6. Not in DuckSuite distribution

- VibeCut direct DMG.
- VibeCut Cloud Private.
- Hosted tenants.
- Sparkle.
- License keys.
- Classic or Voice Room in the same bundle.
- URL/XHS ingest.
