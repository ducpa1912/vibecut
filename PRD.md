# VibeCut PRD — Paid v1

**Status:** Draft for founder approval. Release verdict: **ALPHA ONLY** until the five gates pass.
**Owner:** Founder/CEO. **Author:** Senior Product Lead.
**Version:** 1.1 · **Date:** 2026-10-26
**Sources:** [Founder brief](FOUNDER_BRIEF.md), [round_1.md](round_1.md), [round_2.md](round_2.md), [round_3.md](round_3.md), current code at `2228066`.

> **Scope correction 2026-10-26:** Flow 1 and Flow 2 are not a cleanup add-on and a retention sidecar. They are one Check → Stories → Edit workflow. Flow 2 is the full Compose UI/UX; Flow 1 is the cleanup pre-pass. See [ROADMAP.md](ROADMAP.md#1-where-we-are-now). Paid 1.0 scope below is unchanged.

> **Where this stands, 2026-11-06.** The promise, price, gates and decisions below are still the plan for paid v1, and nothing here has shipped. The rest of this section lists what has moved since version 1.1, so the old text stays for reference.
>
> | This PRD says | Today |
> |---|---|
> | Six paid-v1 screens: Import, Stories, Captions, Queue, Packet, Review (§9) | Studio has four steps: Import, Moments, Edit, Finish. Captions live in Edit; Queue, Review and Publish live in Finish |
> | 9:16 and 4:5 only; 1:1 and 16:9 out (§13, §15) | Studio renders 9:16, 4:5, 1:1, 16:9 and 16:10. The paid promise still only depends on 9:16 and 4:5 |
> | Final or draft render (FR-6) | Six quality tiers, 360p to 4K |
> | macOS 14+ (§10) | The current build has been run on macOS 26. The supported list is still an open question |
> | Baseline at `2228066` (§1) | Much of that baseline is fixed. Open gates are in [ROADMAP.md](ROADMAP.md#2-open-items-and-next-steps) |
> | Not listed | Clean and AI text removal, full-video edit and render, and Classic as a second product now exist. They sit outside this paid promise |
>
> Current product record: [PRODUCT.md](PRODUCT.md).

---

## 1. Executive summary

VibeCut has a credible artifact spine and a real story engine. It does not yet have a sellable Mac product. The CTO’s five gates are the release contract: no money until a clean Mac installs it without Terminal, and a story survives edit, retry, crash, reload, and aspect change as one object.

Paid v1 is one workflow:

```text
source → 3–6 stories → sentence/caption edit → 9:16 or 4:5 story render → packet → reload
```

Everything else is compatibility, post-v1, or explicitly refused.

**Baseline at `2228066`:** no signed app; story render UI is fixed to 9:16 and does not pass the edited caption track; packet pin, packet list, and reload are missing; queue accepts only 15/30/60; disk reserve, bare `/clip-sets` routes, query tokens, and email admin still violate CTO decisions.

---

## 2. Product promise and positioning

**Promise:** One eligible 30–120-minute recording in. At least three stories you would post out, each with captions and a packet that is still there tomorrow, on your Mac — or a full refund. For eligible 20–29-minute sources, the floor is two.

**Positioning:** The local Mac story workstation for creators who will not upload client footage or pay per clip.

**One sentence:** VibeCut turns one eligible 30–120-minute recording into at least three stories you would post, each with captions and a packet that is still there tomorrow, on your Mac — or you get your money back.

**Unit:** one story packet. The set is the proof, not a quota of six.

---

## 3. Founder problem

The founder loses 9–11 hours a week to assembly, not editing:

- **90-minute podcast:** 3h40m; 2h10m after analysis. Bad stories open mid-thought or end before payoff. Caption Studio asks 15/30/60 for a 47-second story. Packet disappears on tab close.
- **30-minute client interview:** 2h45m plus 1h20m revisions. 4:5 needs a full rebuild. Client approves an old link after a newer render. Two links, two cuts, no version label. Packet cover differs from preview.
- **Repost job:** 3h15m per source. Re-ingest, re-analyze, re-cut, stale references, caption drift. If the source is old enough, it is no longer findable.

The emotional cost is “clip farm” and looking amateur with client footage.

**Founder quote:**

> “I do not need more clips. I need the four I will actually post, with the captions and copy already right, from my own machine, tomorrow morning.”

---

## 4. ICP, JTBD, buying trigger

### Primary ICP

Technical solo creator-editor on Apple Silicon:

- 20–120-minute podcasts, interviews, courses, livestreams;
- 3–10 shorts a week;
- some client work;
- values local custody and flat cost;
- will not accept Terminal install, watermark, meter, or mandatory cloud.

### Secondary

2–5-person studio with one operator. No seats, comments, or approvals.

### JTBD

> “When I have one long recording and a deadline, help me find the 3–6 stories worth posting, fix them at sentence level, and hand me captions, covers, and copy in one packet, so I do not rebuild the post by hand or open Resolve for a vertical.”

### Buying trigger

Two long sources plus a client deadline, after 20-source evidence shows at least three postable stories per eligible source and a packet that survives reboot.

---

## 5. Goals, metrics, and release gates

### Goals

- Pass all five CTO gates.
- At least three postable stories per eligible 30–120-minute source; two for 20–29 minutes.
- Median repair ≤10 minutes; p90 ≤20.
- First approved story p50 ≤30 minutes from import.
- Zero caption/artifact/packet lineage failures.
- <5% refunds in 30 days; zero refunds for vanished packets or wrong cuts.
- 25 paid seats in the first 60 days after launch.

### Metrics

| Metric | Target |
|---|---|
| Postable stories/source | Floor: ≥3 for every eligible 30–120 min source; ≥2 for 20–29 min. Mean ≥4/6; within 0.5 of OpusClip |
| Per-source remedy | 100% of below-floor claims resolved by assisted rerun or full refund within 5 business days |
| Repair minutes/story | median ≤10; p90 ≤20 |
| Clean postable rate | ≥80% of postable stories require ≤5 minutes repair |
| Time to first approved story | p50 ≤30 minutes from import |
| Caption/artifact lineage | 100% match after edit, retry, reboot |
| Version handoff | 100% of shares labeled; zero retargets; superseded banner on old links |
| Packet re-download | 100% same ID and bytes next day |
| Crash recovery | 100% of 10-item queues; one output each |
| Caption rework | ≤2 cue edits; zero timing drift |
| Purge | 100% of explicit deletes write receipt; zero stale CAS references |
| License continuity | Free compatibility/lineage fix or refund within 30 days |
| Refunds | <5% in 30 days; zero for vanished packets or wrong cuts |
| Support | First human <1 business day; <4 business hours for blocked client deadline/data loss/lineage |
| Disk honesty | zero valid renders blocked at 10.4 GB free |

### Paid-release gates

Any failed gate means no paid release.

| Gate | Acceptance |
|---|---|
| **G1 Mac install/license** | Clean Mac, no Terminal/Python/ffmpeg: install signed/notarized app, activate offline trial/license, import 90-minute source, render one story, export packet, reboot, data intact; `codesign --verify` and `spctl -a` pass |
| **G2 Lineage + keeper rate** | 20 real sources, 3–6 stories each. Edit clips, captions, style, margin, 4:5; render, retry; burned cues, SRT, `packet.json`, cue/style hashes, artifact SHA, cover times match. Close/reopen; same packet downloads; review link re-copies. No eligible source below floor; mean ≥4/6; zero mismatches |
| **G3 Crash/timeout/queue** | 10 story items; SIGKILL at item 3. Restart: no auto-run, banner, one-click resume, exactly one output per item. Timeout kills ffmpeg; next item starts; no orphan process |
| **G4 Auth/admin** | Bind `0.0.0.0` without token: every creator and admin mutation returns 401/403, including `PATCH /clip-sets/{id}`. No query token. With token, creator works. Password-only admin; no email field; no token in logs |
| **G5 Disk** | 245 GB volume, 10.4 GB free: 30-second final render starts and completes. Below threshold: 412 with exact shortfall. Upload failure: 507, no partial output |

---

## 6. Product principles

1. **Story is the unit**, not 15/30/60.
2. **Finish in one pass**; no hand assembly.
3. **One object** through edit, retry, reload, and aspect change.
4. **Local custody**; no meter, account, or watermark.
5. **Show evidence**; never sell a score.
6. **Fail visibly**; never silently block, retarget, or overwrite.
7. **One Mac, one owner**; no collaboration surface.
8. **Boring reliability beats feature breadth.**

---

## 7. User journeys

### 7.1 First run

Download signed app; drag to Applications; launch. Offline trial, no account. Import 90-minute source; see ETA. Get 3–6 stories with hook, payoff, evidence. Accept one, edit a sentence, render, build packet, reboot, reopen, download same packet. No Terminal.

### 7.2 Weekly podcast

Monday import. Reject two bad stories in 30 seconds each. Reorder/exclude sentences; captions follow. Queue four story renders while doing something else. Packet per story. Close app. Tuesday re-download the same packet.

### 7.3 Client interview

Import. Build three stories. Render 9:16, then 4:5 from the same story and caption track. 4:5 is a separate immutable artifact. Send pinned links with version labels. Revision creates a new artifact and link; old link still plays old cut. Packet covers match ZIP. Client sees “v2 · current” clearly.

### 7.4 Repost/reuse

Open prior job or story through search. Change aspect and title. Render without re-analysis. New artifact/packet. Full posted-history ledger is post-v1; reopen/re-export is paid v1.

### 7.5 Packet reload

Open app; select job; Packet shows prior packets with dates, story labels, versions. Download ZIP by `packet_id`; bytes match. Pin comment and covers are the persisted ones.

### 7.6 Failure/recovery

Kill queue at item 3; reopen. Banner shows interrupted items. One click resumes; no auto-run; one output each. Disk shortfall shows exact bytes and reclaim action. Expired or revoked link errors clearly, never falls back to newest.

### 7.7 Delete client footage

Open job; choose **Delete source now**. See CAS references; if packets/artifacts reference it, require cascade confirmation. Delete job link, decrement refcount, delete CAS object at zero, verify path absent, write and show `deletion_receipt.json`. Auto-clean only workfiles, caches, tmp. SSD physical-erase limits disclosed.

---

## 8. Functional requirements

| ID | P | User story | Acceptance | CTO dep |
|---|---|---|---|---|
| FR-1 | P0 | I install and launch like a Mac app. | Signed/notarized `.app`; no Terminal, Python, Homebrew, or ffmpeg install; bundled runtime/helpers; data in `~/Library/Application Support/VibeCut`; launchd; survives reboot | G1 |
| FR-2 | P0 | I can try, activate, and keep using my purchased version offline. | 14-day/3-packet trial, no watermark; signed offline license; one Mac; no phone-home. **License:** perpetual for purchased 1.x; 12 months updates/support; optional $79/year renewal adds new features and support. **Free to all 1.x licensees, with or without renewal:** macOS compatibility fixes for the supported list, caption/lineage/security fixes. If a supported macOS update breaks the build and cannot be fixed within 30 days, full refund | G1 |
| FR-3 | P0 | I get stories I can judge, with a per-source floor. | Eligible source: 20–120 min, ≥70% speech, audible dialogue. Floor: 30–120 min → ≥3 postable; 20–29 min → ≥2. One assisted rerun within 5 business days; still below floor → full refund. Claim window: first five eligible sources in first 30 days. Postable = self-contained, hook ≤3s, payoff complete, ≤2 caption errors, ≤10 min repair; Clean = same with ≤5 min repair. Mean 4/6 is portfolio target, not guarantee | G2 |
| FR-4 | P0 | I fix sentences without breaking the cut. | Include, exclude, reorder; save; duration and cues update; no orphan clip; stored story duration is authoritative | G2 |
| FR-5 | P0 | One caption track follows the story. | Speech-timed cues; edit text/style/margin; burn, SRT, preview, packet use same track ID/style hash; retry/reload preserve; cue/style hashes match | G2 |
| FR-6 | P0 | I render at story length in 9:16 and 4:5. | Stored duration only; no 1–180 override; captions on by default; final/draft; 4:5 preserves story/cues/copy; separate immutable artifact; 9:16 never overwritten | G2 |
| FR-7 | P0 | I get one packet I can find tomorrow. | `packet.json` canonical; MP4, SRT, 3 titles, 125-char description, 3–8 hashtags, pin comment, 2 exact covers; ZIP derived and always downloadable; packet list after relaunch; same ID/bytes; copy blocks ordered. Chapters out | G2 |
| FR-8 | P0 | Ten **story items** run sequentially and recover. | Item = `(job_id, set_id, story_id)` + aspect. Max 10 story items, not sources; items may span jobs. Sequential; exactly one output per story; pause/cancel; one-click resume; never auto-run; watchdog kills timeout | G3 |
| FR-9 | P0 | Preflight tells me what to fix in 9:16 and 4:5. | Findings name story, cue, artifact, aspect, version; severity; one click opens exact editor. Checks: dangling claim, truncated payoff, caption density, loudness, 4:5 crop/safe-zone/caption. 4:5 checks subject/face inside frame, caption block clear of face/UI, no 9:16 reuse. Advisory; block only explicit | G2 |
| FR-10 | P0 | Client handoff has a version label and never retargets. | Every artifact gets monotonic `v{n}` per story/aspect, `created`, `supersedes`. Share pinned to artifact/version. Review page labels `v2 · superseded by v3 on 12 Oct`; old link keeps playing v2; no redirect. Owner sees Versions table with `Current` = newest ready, per-version `Copy link`/`Revoke`. `packet.json` carries version/supersedes. Expired/revoked clear | G2 |
| FR-11 | P0 | Only I can reach the creator API. | Default-deny; all creator routes under `/api`; no bare `/clip-sets`; no query token; loopback no-token supported; remote requires bearer; LAN opt-in/token-gated only | G4 |
| FR-12 | P0 | One password-only local admin. | One fixed local account; 12+ char password; no email/SMTP/signup/recovery email; loopback bootstrap; existing alpha row migrates | G4 |
| FR-13 | P0 | A valid render is not blocked by a false reserve. | `reserve = min(5 GiB, max(2 GiB, 5% of volume))`; allow only `free - required >= reserve`; render/batch 412 with exact shortfall; upload 507; no partial output | G5 |
| FR-14 | P0 | A crash does not lose 40 minutes. | Startup reconciler maps manifests to render records; interrupted banner; one-click resume; no auto; packet refs persisted; timeout process-group kill; `job.json` stays with indexes/reconciler; no storage rewrite | G3 |
| FR-15 | P0 | Core work is offline; diagnostics and rollback exist. | Cut, caption, render, packet work network-off; no telemetry/account/watermark/meter; local redacted diagnostics; rollback build; versioned notes | G1 |
| FR-16 | P0 | I can delete client footage and prove it left the store. | Default retain. `Delete source now` shows CAS refs; blocks if shared/packet refs unless cascade confirmed. Removes job link, decrements refcount, deletes CAS object at zero, verifies path absent, writes `deletion_receipt.json` with job/source hash/bytes/refcount before-after/time/result. UI shows receipt. Auto-clean only workfiles/caches/tmp; never sources/artifacts/packets. SSD physical-erase limit disclosed | G2/G3 |
| FR-17 | P0 | I can find and reopen a prior source/story, then re-export without re-analysis. | Derived job index over `job.json`; no 24-job cap; search by source name, job ID, story title, date; paginated. Reopen job/story; change aspect/title; new artifact/packet; no analysis. Index rebuildable; `job.json` source of truth; no storage rewrite. 100 jobs p95 search <300 ms | G2; release checklist |
| FR-18 | P1 | Old jobs and links still work. | Legacy 15/30/60 jobs readable/finishable; artifacts/shares play exact old cut; no new legacy batches; UI labels Compatibility; no rewrite | G2 |
| FR-19 | P2 | I add chapters to a packet. | Post-v1 only. Chapter block in `packet.json`, optional timestamps, ZIP derived. No work before 1.0 ships | Post-v1 |

---

## 9. UX requirements

### Six paid-v1 screens

| Screen | Job | Empty / loading / error |
|---|---|---|
| Import & Jobs | Import file/path/URL; recent jobs; health; search | Empty: drop zone + sample. Loading: probe/analysis + ETA. Error: codec, disk 507, duplicate |
| Stories | 3–6 story cards; hook/payoff/evidence; accept/reject; sentence edit; aspect | Empty: Build stories. Loading: selection. Error: stale analysis, no stories, source changed |
| Captions | Cue list; text/style/margin; caption-only preview | Empty: Build captions. Loading: cue generation. Error: no speech, unsaved changes |
| Queue | Story items; 9:16/4:5; status; resume | Empty: no renders. Loading: queued/running. Error: interrupted, timeout, resume required |
| Packet | Metadata, exact covers, pin, copy blocks, packet history, ZIP | Empty: render a story first. Loading: building. Error: missing title/hashtag, disk. Reloads history |
| Review | Preflight findings, artifacts, versions, shares | Empty: run preflight. Loading: checks. Error: expired/revoked link, missing artifact, exact fix target |

### UX rules

- No `v1`/`v2`, “Beta read,” “Advanced preview,” “Selection v2,” “legacy render key,” “artifact,” or version jargon in primary UI. Use **Story**, **Cut**, **Captions**, **Render**, **Packet**, **Review link**, **Versions**.
- Keep **Auto Select** and **Read Analysis**; Original/Beta live inside Read Analysis, prompt only in Beta. Two primary selection buttons, plain language.
- Version labels are visible on shares and packets, never silent.
- No drag-only reorder; full keyboard path.
- **Accessibility:** WCAG 2.2 AA; visible focus; 200% zoom; screen-reader labels/live regions for render/queue; color never sole signal; reduced motion. Test 1280×800, 1440×900, 1728×1117, 1024×768, and 200% zoom.
- No horizontal overflow at supported widths.
- Empty states explain the next action; errors carry a route to fix.
- Advisory checks never silently block export.

---

## 10. Non-functional requirements

| Area | Requirement |
|---|---|
| Local-first | No network for cut/caption/render/packet. Optional AI copy off by default, key-based, never required. No telemetry |
| Performance | 90-min 1080p analysis p50 ≤20 min, p90 ≤30 on M1/16 GB; first story ≤30 min; final render ≤2× duration; packet ≤60s; UI <100ms |
| Disk | Exact CTO reserve; 412 render/batch shortfall; 507 upload; storage panel shows use/reclaim |
| Reliability | ≥95% queue completion without retry; 100% crash recovery; zero duplicate outputs; zero share retargets |
| Retention | Default retain until explicit delete. Auto-clean caches/workfiles only, off by default. Sources/artifacts/packets never auto-deleted |
| Support | First human <1 business day; <4 business hours for blocked client deadline/data loss/lineage. Founder answers first 50 seats; named backup engineer from seat 51. Public known issues; no source upload without consent |
| Privacy/security | Loopback default; default-deny; secrets 0600 or Keychain; redacted logs; no tokens in URLs; admin CSRF/CSP; no analytics |
| Data/compat | macOS 14+ Apple Silicon; 8 GB min, 16 GB recommended; `job.json` plus index/reconciler; backup/migration; rollback two versions |

---

## 11. Benchmark proof

### 20-source set

- 5 long 90–120-minute podcasts;
- 3 client interviews, 30 minutes;
- 4 courses/screencasts;
- 4 livestreams;
- 4 noisy/multi-speaker.

Each source: up to six candidates. All accepted stories rendered 9:16; top three accepted stories rendered 4:5; 4:5 preflight on each.

### Raters and evidence

- Three independent working editors per clip; blind, randomized order.
- Timed repair with stopwatch to postable.
- Count caption errors; retain raw clips; report rater scores and disagreement.
- Same sources through OpusClip Pro at defaults.
- Add four “pretty but empty” negative clips; raters must reject; VibeCut must flag ≥3.
- Evidence pack includes raw clips, rater sheets, timed logs, caption ledger, hashes, side-by-side.

### Launch only if

- No eligible source below floor.
- Mean ≥4/6; within 0.5 of Opus.
- ≥80% of postable stories are clean (≤5 minutes repair).
- Zero caption/lineage mismatches.
- Packet reload, crash resume, and delete receipt pass.
- Founder dogfood set — 94-minute podcast, 30-minute client interview, 2019 repost — passes separately.

---

## 12. Pricing, alpha, and license

- **Alpha:** free, invite-only. No paid alpha, no pre-orders. Dated written reviews day 30, 60, 90.
- **Paid v1:** $249 one-time; alpha cohort locked at $149; 30-day refund; no subscription, meter, or credits.
- **License:** perpetual for purchased 1.x; 12 months updates/support; optional $79/year renewal for new features/support. Compatibility, lineage, and security fixes free without renewal.
- **Support:** same SLA seat 1 and seat 51. Founder primary first 50; named support engineer from 51. Pause sales before SLA drops.
- **No telemetry.** No phone-home kill switch. Old packets remain openable/downloadable on that Mac, same bytes, subject to disk.

---

## 13. Scope cuts

**Out of paid v1:** chapters; hook/cover matrix; selection v2 and prompt exclusions; review comments/approvals/seats; retention ledger; publishing/scheduling/OAuth; cloud/accounts/login; Windows/mobile; auto-resume; 90/180 targets; 1:1/16:9; new 15/30/60 batches; LAN/WAN; localization; avatars/voice cloning/stock B-roll; SFX/J-L cuts; folder-vs-ZIP options; full repost ledger.

**Compatibility only:** legacy 15/30/60 jobs readable/finishable; exact old artifacts/links; no new legacy batches.

**Post-v1:** chapters, Selection Edge, Repost Library, hook/cover matrix, better preflight fixes, after entry conditions.

---

## 14. Risks, dependencies, open questions

| Risk/dependency | Mitigation |
|---|---|
| Signing/notarization/bundling slips | Start Developer ID and macOS CI day 0; freeze features; never ship unsigned |
| 20-source selection fails | No paid launch; one selection iteration; stop after two failures |
| Per-source guarantee raises refund/support exposure | Eligibility rules; one assisted rerun; reserve; claim window first five sources/30 days |
| Version labels confuse clients | Superseded banner; no redirect; owner “Copy current link”; version in packet |
| Job index becomes a rewrite | Derived index only; rebuild from `job.json` |
| Purge receipt overpromises | App-level proof only; disclose SSD limits |
| Compatibility promise costs engineering | Supported macOS list; 30-day fix-or-refund; budget it |
| Seat 51 support gap | Staff named engineer before seat 51; pause sales |
| Caption/artifact divergence | Canonical track ID and hash assertions; kill/retry/reload tests |
| 4:5 client quality fails | Test 10 real client sources; fix crop; do not cut 4:5 |
| Installer too large | Bundle required models; optional extras; measure clean-Mac install |

**Open questions:** exact minimum macOS; required model bundle size; benchmark rater compensation; legal wording for SSD deletion; Merchant of Record/refund processing; final supported-Mac list.

---

## 15. Decision log

| Founder question | Decision |
|---|---|
| 1. Alpha/pay? | **Free invite-only alpha; no pre-orders.** Dated written reviews day 30/60/90. Paid launch only day 90 if all five gates, benchmark, and dogfood pass. Fail twice or slip past day 90 → no paid release this cycle; alpha stays free |
| 2. Promise? | **One eligible 30–120-minute recording → ≥3 postable stories, or full refund; 20–29 minutes → ≥2.** Mean 4/6 is a portfolio target, not the guarantee |
| 3. 4:5? | **Yes, P0.** 9:16 and 4:5 only. 4:5 is a separate immutable artifact; never overwrites 9:16. 1:1/16:9 out |
| 4. Who judges publishable? | **Three blind independent editors per clip plus founder as buyer-rater.** Timed repair, raw clips, rater disagreement, negative set, Opus side-by-side. Evidence pack visible to alpha before payment |
| 5. Repost/legacy? | **P0: derived job index/search, no cap, reopen and re-export without analysis.** Full posted-history ledger post-v1. Legacy links pinned; no rewrite; no new legacy batches |
| 6. Support? | **Same SLA seat 1 and seat 51.** Founder primary first 50; named support engineer from 51. <1 business day; <4 business hours for blocked deadline/data loss/lineage. Pause sales before SLA drops |
| 7. Renewal/archive? | **Perpetual 1.x license. 12 months updates/support; $79/year optional.** Compatibility, lineage, and security fixes free without renewal. Supported macOS break with no fix within 30 days → full refund. Old packets remain openable/downloadable |
| 8. Deletion? | **Default retain; explicit source delete; receipt; CAS refcount; packets/artifacts protected; caches only auto-clean.** Receipt proves app-level deletion, not SSD physical erase |
| 9. Known issues/rollback? | **Yes.** Public known-issues page, versioned notes, two prior signed builds, backward-compatible data for one major version, tested rollback. No telemetry; update user-initiated |

---

## 16. Final product sentence

> **VibeCut turns one eligible 30–120-minute recording into at least three stories you would post, each with captions and a packet that is still there tomorrow, on your Mac — or you get your money back.**

---

*PRD 1.1 · Draft for founder approval · Paid v1 blocked until the five CTO gates pass.*
