# Duck Roadmap

**Status (2026-11-07):** Phase 1 DuckSuite is the only active build. VibeCut Studio is the codebase/legacy name. The old $249 VibeCut Studio plan is historical; this file supersedes it.

**Clock:** agent-native. One implementation phase per day is the target. External gates — App Review, StoreKit propagation, clean-Mac signing, model quality, HF capacity, legal/license review — run in parallel and are not coding days.

**Source of truth:** this file. Product record: `PRODUCT.md`. Distribution: `docs/duck/DISTRIBUTION.md`. Commercial: `docs/duck/COMMERCIAL.md`. Detailed Phase 1 steps: `docs/handoff/ducksuite-phase1-plan.md`. Design system: `DESIGN.md`. Testing: `docs/handoff/ducksuite-testing.md`.

## 0. Build status (2026-11-07)

| Day | Status | Note |
|---:|---|---|
| 1 | **Shell done; StoreKit/render pending** | `duckcore` sidecar, token handshake, static shell, SwiftUI shell, dev `.app`, LaMa model copy, tests |
| 2 | **Projects/import done** | SQLite project index, native import bridge, project cards, delete, dev fallback |
| 3 | **Check, full edit, story builder, smart cut, clean layers built** | Background Check runs scenes, transcript, OCR tracklets and smart stories. Full-video edit comes first; manual story builder and smart cut follow. Clean layers are generated from Check with Fill/Blur/Off. Render/queue next. |

Day 1 remaining: LGPL ffmpeg bundle, full Xcode build, StoreKit test, sample 1080p render.

---

## 1. Phase 1 clock

| Day | Build | Gate |
|---:|---|---|
| **0** | Freeze scope, pricing, model list, App Store decisions | G0 |
| **1** | Sandboxed SwiftUI shell + bundled `duckcore` + LGPL ffmpeg + LaMa ONNX + local API + StoreKit test | Clean-Mac launch; no downloaded code |
| **2** | New DuckSuite shell, Home/Projects, Import, native file access | Import → project on 3 real clips |
| **3** | Analyze: Dissect + Detect | Scenes, transcript, text/face/music evidence |
| **4** | Edit: Cut, Frame, Captions, Text, Clean | First clean render on 5 clips |
| **5** | Voice-over + **Dub** | Voice and dub preview; 3 languages |
| **6** | Render + Export + Queue + Model Manager + Settings | Full 1080p export; model verify |
| **7** | App Store packaging, privacy manifest, IAP, TestFlight | TestFlight build; review submit |
| **8–9** | HF free CPU broker + Space + consent + retention | Free CPU cost/time measured |
| **10–11** | Paid CPU + StoreKit subscription + quota + 3 concurrent | Purchase/restore/refund test |
| **12–13** | CUDA path + GPU benchmark on HF/Beam/Modal | Render Plus yes/no |
| **14** | Bugfix, docs, 10-creator beta | Launch gate |

This is 14 implementation days plus Apple review. Local-only TestFlight should exist on Day 7.

---

## 2. Phase 1 — DuckSuite

### 2.1 Scope lock

DuckSuite is a **$29 Mac App Store app**, macOS 26+ on Apple Silicon.

Must ship:

- **Dissect:** scenes, transcript, local OCR, smart story candidates with hook/payoff evidence, manual moment builder.
- **Detect:** text, faces, saliency, speech, music, quality warnings.
- **Clean:** LaMa AI fill default; explicit Blur; one box per real text; before/after.
- **Voice-over:** local Apple voices + Kokoro.
- **Dub:** Apple Translation + local TTS; editable script; English, Vietnamese, Chinese; beta label allowed, cut not allowed.
- **Edit:** trim, split, reorder, remove silence; 9:16/4:5/1:1/16:9; auto-frame; captions; text; music.
- **Render:** 1080p only; 24/30 fps; MP4 H.264/AAC.
- **Export:** MP4, SRT, cover JPG. No publish kit.
- **Cloud render:** optional free CPU, then paid CPU. GPU is a later gate.

Hard cuts:

- No 720p/2K/4K/60 fps/HDR/ProRes.
- No LUTs, colour grading, effects, motion keyframes, borders.
- No publish kit, review links, versions, packet.
- No URL/path import.
- No voice cloning, cloud keys, generated music.
- No multi-set comparison UI, strength score, queue-all from Moments. Smart story finding stays.
- No STTN/MI-GAN/Telea/Navier-Stokes picker, GPU toggle, follow-camera toggle.
- No admin, Classic, LAN review links, telemetry.

### 2.2 Product shape

```text
Home / Projects
  └── Project
        ├── 1 Import
        ├── 2 Analyze
        │     ├── Moments
        │     └── Footage check
        ├── 3 Edit
        │     ├── Cut
        │     ├── Frame
        │     ├── Captions
        │     ├── Text
        │     ├── Clean
        │     ├── Voice
        │     └── Music
        ├── 4 Render
        └── 5 Export
Render Queue
Settings
```

**UI direction:** “Daylight Bench.” Light chrome, dark video canvas, one amber accent. Native SwiftUI chrome around a WKWebView editor. Minimum 12 px labels, 13 px panel body, 15 px body. WCAG 2.2 AA.

### 2.3 Technical shape

```text
DuckSuite.app (sandboxed)
  SwiftUI shell
    StoreKit 2 · NSOpenPanel/NSSavePanel · WKWebView · process supervisor
          │ 127.0.0.1:random + per-launch token
          ▼
  duckcore (bundled Python 3.11)
    FastAPI · Dissect/Detect/Clean/Voice/Dub/Edit/Render
    LGPL ffmpeg · ONNX Runtime · LaMa · prebuilt Apple helpers
    SQLite queue · project JSON
          │ HTTPS + app token, only on user consent
          ▼
  Render broker
    StoreKit receipt validation · quota · idempotency
    R2 presigned upload/download
    HF / Beam / Modal / RunPod adapters
```

No HF token in the Mac app. No downloaded executable code. Core models bundled.

### 2.4 Phase 1 gates

- **G0 — Scope:** one-page scope signed; $29/$5/$20 locked; model licenses reviewed; macOS 26 decision.
- **G1 — Shell:** clean Mac install; sandbox; bundled Python/ffmpeg/LaMa; local API token; StoreKit test purchase.
- **G2 — Local flow:** Import → Analyze → Edit → Render → Export on 3 real clips.
- **G3 — Quality:** 20 real clips; clean, voice, dub, captions pass; no silent blur.
- **G4 — App Store:** privacy manifest, App Privacy label, IAP, restore, review notes, TestFlight.
- **G5 — Free CPU:** cost/hour measured; queue fair; retention and deletion work; abuse controls.
- **G6 — Paid CPU:** purchase/restore/refund; 3 concurrent; margin >50%.
- **G7 — GPU:** >2× faster than CPU and cost <$0.50 per 90 s render; otherwise no Render Plus.
- **G8 — Launch:** 10 creators; activation, refunds, crash-free, support load targets.

---

## 3. Phase 2 — DuckClean

**DuckClean ships from the Classic lane, not Studio.**

- Branch/lane: `classic` and `classic_app.py`; not `studio_app.py`.
- New `DUCKCLEAN` profile composed from `CLASSIC` in `core/profiles.py`.
- Reuses Classic `check`, `cleanup`, `ai_fill`, render pieces.
- No Studio page, no stories, no Edit document, no Studio queue.
- Flow: upload → detect text → AI fill or blur → download.
- Free trial on HF free CPU; paid CPU; Express T4/on-demand waitlist.
- Linux OCR test: PaddleOCR / EasyOCR / Florence-2 / Qwen-VL on 40–60 clips. Gate: ≥90% text regions clean, no false positives, temporal stability. Fail → Mac OCR worker.
- No accounts before paid; no unlimited; no publish.

---

## 4. Phase 3 — DuckClassic

Cloud clean/quick for operators and automation buyers.

- Credits, API render, templates, batch clean, quick queue.
- Not a pro editor; no colour grading, no multi-track NLE, no publish suite.
- Reuses DuckClean/DuckSuite broker and `duck-render` worker image.
- Start only after DuckClean has paying users.

---

## 5. Phase 4 — DuckStudio

Full cloud suite for non-Mac users.

- Assets, editing, captions, voice, clean, publish, collaboration.
- Shared DuckKit design system, project manifest, model registry, render adapter.
- Do not build shared tenancy, teams or OAuth before DuckSuite and DuckClean are paying.

---

## 6. Product contracts

### Local-first

- DuckSuite works offline after purchase and model install.
- No account, no telemetry, no upload by default.
- Cloud render is opt-in per project with a visible consent sheet.

### App Store

- Mac App Store only for Phase 1. No Sparkle, no license key, no direct DMG.
- Sandbox; user-selected file access; no path import.
- Bundle Python, ffmpeg LGPL, ONNX Runtime, LaMa, prebuilt Swift helpers.
- No downloaded executable code. Optional packs are data with SHA-256 + Ed25519 signature.
- StoreKit 2: $29 app; Render subscription; restore; manage subscription.
- Privacy manifest + App Privacy label; subprocessors named.
- Local server: `127.0.0.1`, random port, token every route.
- Watermark removal only with own-footage attestation; no watermark-removal marketing.

### Render

- One manifest for local and remote.
- Artifact ID = SHA-256 of source, edit, masks, model hashes, renderer version.
- Same inputs = same artifact; never overwrite a ready artifact.
- Render hour = one hour of worker wall-clock. Show output estimate from measured speed.
- Failed/cancelled jobs do not consume hours. No auto-overage.

### Models

- `models/manifest.json` with id, version, file, size, SHA-256, license, source, min app.
- Core models bundled. Optional packs data-only.
- Verify signature, size and SHA-256 before activation; verify again after update.
- No silent model replacement. Old renders stay playable.

### DuckClean lane

- **DuckClean is a Classic-lane product.** New profile from `CLASSIC`; new minimal web UI; no Studio imports.
- Classic's Clean behavior is the source, not Studio's story/Edit document.
- If a fix belongs in shared Clean, land it in the shared engine and both lanes use it.

---

## 7. What not to build now

- No 4K/2K/720p/60 fps/HDR/ProRes.
- No LUTs/colour grading/effects/motion.
- No publish kit/review links/versions/packet.
- No URL/XHS/path import.
- No voice cloning, cloud voices, generated music, provider keys.
- No multi-set stories, strength score, queue-all.
- No admin, Classic inside DuckSuite, LAN review.
- No accounts, teams, OAuth, Stripe, multi-tenant control plane.
- No direct DMG until App Store is live or rejected.
- No GPU Render Plus before the benchmark.
- No shared Mac/tenant hosting.

---

## 8. Legacy

- VibeCut Studio remains the codebase name and the source of the engine.
- The old $249 direct-DMG plan, Sparkle updates, license keys and Cloud Private plan are historical.
- `PRD.md` and `docs/handoff/commercial-packaging-plan.md` carry historical banners.
- Existing Studio tests and contracts remain valid for the engine; product-level docs above override the old commercial plan.
