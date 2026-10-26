# VibeCut — Roadmap V2

**Status:** CTO rebuild for founder approval.  
**Baseline:** `b7596db` (paid-v1 trust fixes), after `dea6515`.  
**Supersedes:** [ROADMAP_V1.md](ROADMAP_V1.md).  
**Verdict:** **ALPHA ONLY** until the five paid-v1 gates pass.  
**Rule:** *Committed* means funded and scheduled. *Conditional* means no date, price, or promise. *Alpha-lab* means not sold.

> **Scope correction 2026-10-26:** Flow 1/2 are superseded by [BUILD_PLAN.md](BUILD_PLAN.md). Flow 2 is the full Compose UI/UX, not retention-only; Flow 1 is the cleanup pre-pass in the same editor. Paid 1.0 remains unchanged.

---

## 1. Current state and paid 1.0

Paid 1.0 is one workflow, no more:

```text
source → 3–6 stories → captions → 9:16/4:5 → packet → reload
```

Legacy 15/30/60 jobs stay readable and finishable. They are not the paid unit. **No cleanup or overlay feature ships in 1.0.**

At `b7596db`, most trust code is in place. **Verify and close, do not rebuild:**

- default-deny auth and no query token;
- password-only admin;
- story caption-track lineage and 4:5;
- version labels/superseded;
- crash/timeout story queue with manual resume and orphan-encoder sweep;
- packet pin, history, and reload;
- derived job index/search;
- delete receipt;
- disk formula and 412/507.

**Still open before paid 1.0:**

- signed Mac app and offline license;
- 20-source proof;
- story-item retry;
- packet artifact refs;
- stale queued-manifest reconciliation;
- review-token re-copy;
- exact cover previews;
- legacy caption-count normalization;
- screenshot QA;
- macOS CI;
- all-JS checks;
- logs/diagnostics.

### Five gates — any failure means no paid release

| Gate | Status at `b7596db` | Exact exit criteria |
|---|---|---|
| **G1 Mac install/license** | **OPEN.** No `.app`, signing, notarization, launchd, or offline license | Clean Mac with no Terminal/Python/ffmpeg/Homebrew: drag signed/notarized app to Applications, launch, activate offline trial/license, import 90-minute source, render one story, export packet, reboot, data intact. `codesign --verify` and `spctl -a` pass. macOS 14+ Apple Silicon |
| **G2 Lineage + keeper rate** | **PARTIAL.** Caption track, 4:5, versions, pin/reload closed; 20-source proof, token re-copy, packet refs open | 20 real sources, 3–6 stories each. Edit clips, captions, style, margin, 4:5; render, retry. Burned cues, SRT, `packet.json`, cue/style hashes, artifact SHA, cover times match. Close/reopen: same packet ID/bytes; review link re-copies. No eligible source below floor; mean ≥4/6; within 0.5 of OpusClip Pro; zero mismatches |
| **G3 Crash/timeout/queue** | **CORE CLOSED.** Story queue, watchdog, manual resume, orphan sweep; crash-window reconciliation open | 10 story items; SIGKILL at item 3. Restart: no auto-run, banner, one-click resume, exactly one output per item. Timeout kills ffmpeg; next item starts; no orphan process |
| **G4 Auth/admin** | **CLOSED; verify** | Bind `0.0.0.0` without token: every creator and admin mutation returns 401/403, including `PATCH /clip-sets/{id}`. No query token. With token, creator works. Password-only admin; no email field; no token in logs |
| **G5 Disk** | **CLOSED; verify** | 245 GB volume, 10.4 GB free: 30-second final render starts and completes. Below `required + reserve`: 412 with exact shortfall. Upload failure: 507, no partial output |

---

## 2. Phase plan

### Phase 0 — Free invite-only alpha (0.14 “Trust Core”, 0.15 “Mac Beta”)

**Committed. No payment, no pre-orders.**

- 10–20 creators.
- 0.14 closes code-level trust gaps above.
- 0.15 ships signed/notarized `.app`, bundled Python/ffmpeg/models, launchd, Application Support data, offline trial, backup/rollback.

**Exit:** 3 clean Macs install without Terminal; 10 pilot Macs; 20-source benchmark complete; no P0; day-60 written review.

**Owners:** sysops (package), backend (lineage/queue), product/QA (pilots/benchmark), founder (support).  
**Depends:** Developer ID, notarization, model licenses.

### Phase 1 — 1.0 “Postable Set” (paid v1)

**Committed, gated.**

**Entry:** Phase 0 exit; G1 build; evidence pack; EULA/refund/support live.

**Scope:** feature freeze; story workflow only, plus gate fixes:

- token re-copy;
- packet refs;
- story-item retry;
- stale-manifest reconciliation;
- screenshot QA;
- macOS CI;
- all-JS checks;
- diagnostics;
- 24-hour soak;
- rollback.

**Exit:** five gates + 20-source benchmark + founder dogfood + no P0 + CTO sign-off.

**Price:** $249 one-time; alpha cohort $149; 30-day refund; perpetual 1.x; 12 months updates; optional $79/year renewal. No subscription, credits, meter, or watermark.

### Phase 2 — 1.1 “Same Object” (trust fixes + text guard)

**Committed. Free to 1.x licensees.**

**Entry:** 1.0 shipped 30 days; <5% refunds; no P0.

**Scope:**

- Text Check advisory for detected burned-in text colliding with new captions;
- Safe Crop as advisory framing that keeps old edge text out of 9:16/4:5;
- Caption Rescue OCR-to-SRT draft with low-confidence lines marked and human review required;
- exact cover previews from packaged JPEG;
- legacy caption-count normalization;
- packet metadata persistence audit;
- source-purge/refcount audit;
- rotating logs and redacted diagnostics ZIP;
- full macOS CI matrix;
- screenshot regression suite;
- 100-job search p95 <300 ms.

**Exit:** 30 days no P0; 100% cover preview matches ZIP; 100% legacy counts; 100% diagnostics; zero trust-related refunds.

**Owner:** backend/QA.

### Phase 3 — 1.2 “Overlay Studio” (retention, conditional)

**Conditional. No date, price, or promise.**

**Entry:** 1.1 stable 30 days; usage signal from pilots/support/voluntary survey (target ≥30% of active users request or use manual hook/caption styling); no P0.

**Scope:** new hook/caption overlays, style presets, safe-area preview, burn/SRT/packet parity.

**Hook Cards are killed.**

**Exit:** 100% caption parity; zero drift; pilot retention +10%. If signal is absent, cancel. Included in 1.x, not a paid wedge.

**Owner:** product/backend.

### Phase 4 — 1.3 “Cleanup Kit” (paid expansion, gated)

**Committed only behind gates.**

**Entry:** 1.1 stable; 10 real Mom Tests + paid concierge pilot ($99/10 clips) before code or sale; signed rights attestation; deterministic scope only.

**Scope:** source-less clip cleanup:

- crop;
- cover;
- blur;
- manual masks;
- text detection;
- quality report.

**No:** generative face/logo removal or repair, watermark removal, full-source/4K promise, cloud, team seats.

**Price:** **$149 one-time add-on**; **$99 for v1 owners in the first 90 days**; unlimited local jobs; 30-day refund; no subscription, per-clip, credits, meter, or watermark.

**Exit:** 60 clips / 12 sources / 10 creators:

- zero P0 face/logo smear, ghost caption, caption over mouth, drift;
- ≥90% no visible artifact at 1x;
- 100% static edge text;
- residual OCR ≤0.5%;
- review ≤5 min static / ≤10 min moving;
- completion ≥80%;
- rights attestation.

**Owner:** backend/QA/founder.

### Phase 5 — 2.0 “Selection Edge / Repost / Chapters” (conditional)

Each ships only on its own gate; no bundle promise.

| Scope | Entry | Exit |
|---|---|---|
| **Selection Edge:** selection v2, prompt exclusions | 1.1 stable 30 days; <5% refunds; ≥95% queue; benchmark ≥15% keeper gain without regression | ≥15% gain; no lineage regression |
| **Repost Library:** reopen prior source/story, change aspect/title, re-export without re-analysis; local posted-history ledger | Repeated requests; 1.1 stable | ≥25% active users re-export a prior story; no analytics or platform APIs |
| **Chapters:** chapter block in `packet.json`, optional timestamps, never blocks packet | 1.0 stable; packet reload proven | Used in ≥20% packets |

Price TBD; no subscription.

**Owner:** backend/product.

### Phase 6 — Alpha-lab (experiments, not sold)

**Entry:** 1.0 shipped; separate build; off by default; CTO approval.

**Repair Clip Beta:** manual mask, 720p, ≤10 seconds, 24 GB recommended, off by default, alpha-lab only, not sold.

Other experiments: OCR text detection, overlay prototypes, local model tests.

**Exit:** promote only through a separately gated release, or kill after two cycles.

**No:** generative face/logo, watermark removal, cloud.

---

## 3. Portfolio metrics — 1.0

- floor ≥3 postable per 30–120-minute source; ≥2 for 20–29 minutes;
- mean ≥4/6 and within 0.5 of OpusClip Pro;
- repair median ≤10 min, p90 ≤20;
- ≥80% clean ≤5 min;
- first approved story p50 ≤30 min;
- zero lineage mismatches;
- 100% packet reload;
- 100% crash recovery;
- refunds <5%;
- support first human <1 business day; <4 hours for blocked deadline/data loss/lineage;
- 25 paid seats in 60 days.

---

## 4. Dependencies

| Phase | Dependency |
|---|---|
| 0.x | Developer ID, notarization, model licenses, 10 pilots |
| 1.0 | 20-source corpus, three blind raters, OpusClip Pro |
| 1.3 | Mom Test panel, concierge operator, legal rights sign-off |
| 2.0 | 1.1 stability and usage evidence |

---

## 5. Outstanding ledger

| Item | Status at `b7596db` | Phase |
|---|---|---|
| Signed `.app`, notarization, offline license, launchd, Application Support | Open; no `.app` | 1.0 |
| Auth/admin, disk, story caption lineage, 4:5, versions | Closed; verify | 1.0 gate |
| Crash/timeout/queue, packet pin/reload, job index/search, delete receipt | Closed; verify | 1.0 gate |
| Story-item retry for non-15/30/60 renders | Open; retry route skips story targets | 1.0 |
| Packet artifact refs written back | Open; refs read but never persisted | 1.0 |
| Stale queued-manifest reconciliation | Open; marks interrupted, no retry record | 1.0 |
| Review-token re-copy | Open; token only at creation | 1.0 |
| Screenshot-level QA, macOS CI, all-JS checks, 24h soak, rollback | Open | 1.0 |
| Logs/diagnostics ZIP | Open; stderr only | 1.0 |
| Exact cover previews | Open; poster approximation | 1.1 |
| Text Check, Safe Crop, Caption Rescue | Open | 1.1 |
| Legacy caption-count normalization | Open | 1.1 |
| Packet metadata persistence | Partial: `packet.json`/pin/history survive; refs above | 1.1 |
| Source purge / CAS refcount audit | Closed; verify | 1.1 |
| Hook Cards / hook-cover matrix | Killed | — |
| Overlay Studio | Conditional | 1.2 |
| Cleanup Kit | Committed, gated | 1.3 |
| Repair Clip Beta | Alpha-lab | 6 |
| Selection Edge, Repost Library, Chapters | Conditional, separate gates | 2.0 |

---

## 6. What changed from ROADMAP_V1

1. V1 had four phases; V2 has seven and separates paid 1.0 from post-sale trust fixes.
2. V1 made 1.1 “Selection Edge”; V2 makes 1.1 trust fixes plus Text Check, Safe Crop, and Caption Rescue. Selection Edge moves to conditional 2.0.
3. V1 put Repost at 1.2 and Chapters at 1.3; V2 makes both conditional 2.0 items.
4. V2 adds Overlay Studio as conditional retention and Cleanup Kit as a gated $149/$99 paid add-on. Neither was in V1.
5. Hook/cover matrix and Hook Cards are killed. Overlays replace them, but only if usage earns them.
6. `b7596db` closes most trust code; 1.0 narrows to G1 packaging, 20-source proof, residual refs/retry, and release evidence. No new promises for conditional work.

---

## 7. Founder summary

Do not sell the alpha. The engine is credible; the product is not yet packaged or proven.

1.0 remains the story workflow only: signed Mac, captions, 9:16/4:5, packet, reload. Fix trust in 1.1. Add overlays only if creators use them. Sell cleanup only after 10 Mom Tests and a paid concierge pilot prove deterministic quality. Selection, repost, and chapters stay conditional. Hook Cards are dead.

No cloud, team seats, watermark removal, or generative face/logo repair — ever.

> **CTO quote:** “The code is ready to be trusted; the product is not yet ready to be sold. Ship the signed Mac, prove the same object through edit, retry, crash, reload, and 20 real sources, and only then take money. Everything after 1.0 must earn its way in.”

---

## 8. Not now / never

### Not now

- chapters;
- Selection Edge;
- Repost Library;
- Overlay Studio;
- Cleanup Kit;
- 2.0 upgrade pricing;
- Windows;
- LAN/WAN;
- 16:9/1:1;
- 90/180 targets;
- new 15/30/60 batches;
- full posted-history ledger;
- Smart Cut/Moments UI revamp;
- music/TTS/translation backlog;
- cloud-key live tests;
- uploaded-voice alignment.

### Never

- accounts, cloud sync, team seats;
- subscription, per-clip pricing, credits, meter, watermark;
- publishing, scheduling, OAuth, platform APIs, analytics, virality scores;
- watermark removal;
- generative face/logo removal or repair;
- full-source/4K promise;
- auto-resume, auto-posting;
- telemetry;
- voice cloning, avatars, stock B-roll;
- silent retargeting;
- overwriting approved artifacts;
- Hook Cards;
- cleanup or overlay in 1.0.

---

## 9. Open decisions

1. **Mac packaging route:** native Swift launcher vs bundled Python runtime; Developer ID/notarization owner; confirm macOS 14+ and 8 GB minimum.
2. **1.0 pricing:** confirm $249 / alpha $149; decide 2.0 upgrade price and whether renewals include it.
3. **Benchmark and pilots:** budget/owner for 20-source corpus, three blind raters, OpusClip Pro; recruit 10 pilot Macs.
4. **Cleanup legal:** final rights-attestation wording, add-on EULA, refund handling, start date for the 90-day $99 window.
5. **Overlay trigger:** confirm ≥30% usage signal and whether Overlay Studio remains free for all 1.x owners.
6. **Support and tax:** named support engineer before seat 51; Merchant of Record and refund processor.

---

*ROADMAP_V2 · CTO rebuild · 2026-10-26 · No paid release until all five gates pass.*
