# VibeCut — Paid v1 Roadmap

**Status:** Draft for founder approval. **Current verdict: ALPHA ONLY.**  
**Version:** 1.1 · **Date:** 2026-10-26  
**Related:** [PRD.md](PRD.md) · [PLAN.md](PLAN.md) · [FOUNDER_BRIEF.md](FOUNDER_BRIEF.md) · [round_3.md](round_3.md)

> **Superseded for post-1.0 scope:** [ROADMAP_V2.md](ROADMAP_V2.md) is the CTO rebuild. This file remains the paid-v1 plan and historical record.

---

## One page for the founder

**Read this:** We do not sell the alpha. We give it away until a clean Mac can install it, one eligible source yields at least three postable stories, and the story, captions, render, and packet stay the same object after edit, retry, crash, reload, and version change. Then we charge $249 once, with a 30-day refund. No meter, account, or cloud.

| Phase | When | Version | Price | Scope | Exit gate |
|---|---|---|---|---|---|
| **0. Free invite-only alpha** | Now–day 60 | 0.14–0.15 | Free | 10–20 creators; current workflow plus weekly fixes; no paid promise | 10 pilot Macs; 20-source evidence; no P0 |
| **1. Stabilization** | 0–30 | 0.14.0 “Trust Core” | Free | Auth, admin, story duration/track/aspect, packet pin/reload, queue, watchdog, reconciler, disk, 4:5, job index/search, version labels, purge receipt, license policy | All P0 fixes merged; day-30 review |
| **2. Packaged beta** | 31–60 | 0.15.0 “Mac Beta” | Free | Signed/notarized app, bundled runtime, launchd, offline license/trial, 10-story queue, packet history, repost/re-export, pilot, benchmark, seat-51 support | Clean-Mac pass; 10 pilots; benchmark complete; day-60 review |
| **3. Paid v1** | 61–90 | 1.0.0 “Postable Set” | $249; alpha $149 | Story → captions → 9:16/4:5 → packet → reload. Fix-only | All five CTO gates + benchmark + dogfood pass; day-90 review |
| **4. Post-v1** | After 1.0 + 30 days | 1.1+ | Paid | Selection Edge, Repost Library, Chapters | Entry conditions below |

**If we fail twice or slip past day 90, we do not collect money this cycle. Alpha stays free.**

---

## The promise

> **One eligible 30–120-minute recording in. At least three stories you would post out, each with captions and a packet that is still there tomorrow, on your Mac — or a full refund.**

- 20–29-minute eligible source: floor is two.
- Mean 4/6 is a portfolio target, not the guarantee.
- One assisted rerun; still below floor → refund.
- Claim window: first five eligible sources in the first 30 days.

**Positioning:** the local Mac story workstation for creators who will not upload client footage or pay per clip.

---

## Paid v1 scope

### In

- signed, notarized, no-Terminal Mac app;
- offline license/trial; perpetual 1.x; 12 months updates; optional $79/year renewal;
- launchd/startup; Application Support data;
- 3–6 stories; sentence edit; one caption track;
- story render at stored duration; 9:16 and 4:5;
- packet with pin comment, exact covers, ZIP, history/reload;
- 10 story-item queue; one-click resume;
- preflight for 9:16 and 4:5;
- immutable artifacts; pinned shares with version labels;
- password-only local admin; default-deny auth;
- disk rule; diagnostics; rollback;
- job index/search; reopen and re-export without re-analysis;
- explicit source delete with receipt.

### Out

- chapters;
- hook/cover matrix;
- selection v2 / prompt exclusions;
- review comments, approvals, seats;
- retention ledger, analytics, virality;
- publishing, scheduling, OAuth, platform APIs;
- cloud/accounts/login;
- Windows/mobile;
- auto-resume;
- 90/180 targets; 1:1/16:9;
- new 15/30/60 batches;
- LAN/WAN;
- localization;
- avatars, voice cloning, stock B-roll;
- SFX/J-L cuts;
- full repost library/ledger.

### Compatibility only

Legacy 15/30/60 jobs stay readable and finishable. Existing artifacts and review links play the exact old cut. No new legacy batches. UI labels them **Compatibility**, not the paid unit.

---

## Five gates

Any failed gate = no paid release.

| Gate | Acceptance |
|---|---|
| **G1 Mac install/license** | Clean Mac, no Terminal/Python/ffmpeg: install signed/notarized app, activate offline trial/license, import 90-minute source, render one story, export packet, reboot, data intact; `codesign --verify` and `spctl -a` pass |
| **G2 Lineage + keeper rate** | 20 sources; no eligible source below floor; mean ≥4/6; within 0.5 of OpusClip Pro; burned cues, SRT, `packet.json`, cue/style hashes, artifact SHA, cover times match after edit/retry/4:5/reload; zero mismatches |
| **G3 Crash/timeout/queue** | 10 story items; SIGKILL at item 3; restart shows banner; one-click resume; exactly one output per item; no auto-run; timeout kills ffmpeg; no orphan process |
| **G4 Auth/admin** | `0.0.0.0` without token: every creator/admin mutation 401/403, including `PATCH /clip-sets/{id}`; no query token; password-only admin; no token in logs |
| **G5 Disk** | 245 GB volume, 10.4 GB free: 30s final render starts/completes; below `required + reserve`: 412 with exact shortfall; upload failure 507; no partial output |

---

## Metrics

| Metric | Target |
|---|---|
| Postable stories/source | ≥3 for every eligible 30–120 min; ≥2 for 20–29 min; mean ≥4/6 |
| Per-source remedy | 100% below-floor claims by assisted rerun or full refund within 5 business days |
| Repair minutes/story | median ≤10; p90 ≤20 |
| Clean postable rate | ≥80% of postable stories require ≤5 minutes repair |
| First approved story | p50 ≤30 min from import |
| Lineage/version | 100% matches; zero retargets; superseded banner on old links |
| Packet re-download | 100% same ID/bytes next day |
| Crash recovery | 100% of 10-item queues; one output each |
| Purge | 100% explicit deletes write receipt; zero stale CAS refs |
| Refunds | <5% in 30 days; zero for vanished packets/wrong cuts |
| Support | <1 business day; <4 business hours for blocked deadline/data loss/lineage |
| Disk honesty | zero valid renders blocked at 10.4 GB free |
| License continuity | free compatibility/lineage fix or refund within 30 days |

No product telemetry. Metrics come from benchmark, pilot, support, refunds, and voluntary surveys.

---

## Phase detail

### Phase 0 — Free invite-only alpha (now–day 60)

- 10–20 creators; no payment, no pre-orders.
- Current story workflow plus weekly fixes.
- Named support; private benchmark evidence; locked $149 founding price at v1.
- Written reviews day 30 and day 60.
- If quality is not there, alpha stays free.

### Phase 1 — 0.14 Trust Core (0–30)

- default-deny auth; remove bare `/clip-sets`; remove query token;
- password-only admin;
- story stored duration; caption-track selection; 4:5;
- packet pin/persist/list/reload; packet refs;
- 10 story-item queue; timeout watchdog;
- startup reconciler;
- disk formula 412/507;
- job index/search; no 24-job cap;
- version labels; supersede/current;
- deletion receipt/CAS refcount;
- license policy; macOS CI; all JS checks.

**Exit:** P0 merged; day-30 review; no paid path.

### Phase 2 — 0.15 Mac Beta (31–60)

- signed/notarized `.app`; bundled Python/ffmpeg/models;
- launchd; Application Support; backup/migration; rollback;
- offline license/trial;
- 10-story queue; packet history; 4:5; repost/re-export;
- 10 pilots; 20-source benchmark; founder dogfood;
- named support engineer before seat 51.

**Exit:** clean-Mac pass; 10 pilots; benchmark complete; no P0; day-60 review.

### Phase 3 — 1.0 Postable Set (61–90)

- feature freeze; fix only;
- run five gates + benchmark + dogfood;
- day-90 review;
- paid launch only on pass.

**Price:** $249 one-time; alpha cohort $149; 30-day refund. No subscription, credits, meter, or watermark. Merchant of Record handles tax; offline license.

**Fail twice or slip past day 90 → no paid release this cycle.**

### Phase 4 — Post-v1

| Release | Entry conditions | Scope |
|---|---|---|
| **1.1 Selection Edge** | 1.0 stable 30 days; <5% refunds; no lineage/packet P0; ≥95% queue; benchmark shows ≥15% keeper gain without regression | Selection v2, prompt exclusions, hook/cover matrix, better preflight fixes |
| **1.2 Repost Library** | Repeated user requests; 1.1 stable; local posted-history ledger requested | Reopen/change aspect/title/export; no analytics, no platform APIs |
| **1.3 Chapters** | 1.0 stable; packet reload proven | Chapter block in packet.json; optional timestamps; never blocks packet |

**Never:** accounts, cloud, publishing, team seats, virality scores, auto-resume, 15/30/60 as paid unit.

---

## Not now

Chapters in v1; hook/cover matrix before paid; selection v2 before paid; review comments; approvals; seats; retention dashboards; publishing; scheduling; platform APIs; Windows; mobile; cloud render; credits; watermark; telemetry; avatars; voice cloning; stock B-roll; auto-posting; auto-resume; 90/180 targets; 1:1/16:9; LAN/WAN; full repost ledger.

---

## Founder sentence

> “I do not need more clips. I need the four I will actually post, with the captions and copy already right, from my own machine, tomorrow morning.”
