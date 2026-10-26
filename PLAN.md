# VibeCut — Paid v1 Execution Plan

**Status:** Draft for founder approval. Release verdict: **ALPHA ONLY** until all five gates pass.  
**Owner:** Founder/CEO. **Product:** Senior Product Lead.  
**Version:** 1.1 · **Date:** 2026-10-26  
**Related:** [PRD.md](PRD.md) · [ROADMAP_V1.md](ROADMAP_V1.md) · [round_3.md](round_3.md)

---

## Intent

Turn the alpha engine into a supportable Mac product in 90 days.

The plan is gate-driven, not date-driven. Dates are targets. The five CTO gates are binary. A missed gate means no paid release; it does not mean a smaller paid release.

**Assumed team:** founder/product, one backend engineer, one sysops/platform engineer, contract QA/design. One person may cover multiple roles.

**Paid unit:** one story packet. Paid v1 is the story workflow, not legacy 15/30/60 source batches.

**Commercial shape:** free invite-only alpha; paid v1 only after day-90 gates. $249 one-time; alpha cohort $149; 30-day refund; perpetual 1.x license; 12 months updates; optional $79/year renewal. No subscription, credits, meter, or watermark.

---

## 1. Days 0–30 — Stabilize alpha

**Theme:** Trust Core. No paid path. Make the story and packet trustworthy before packaging.

| Workstream | Owner | Deliverables | Dependencies | Exit criteria |
|---|---|---|---|---|
| Trust/lineage | Backend | Default-deny auth; remove bare `/clip-sets`; remove query token; password-only admin; story stored duration; caption-track selection; 4:5 render; packet pin/persist/list/reload; packet refs; story queue; timeout watchdog; startup reconciler; disk formula/412/507 | CTO decisions | Every P0 stabilization item merged; 0.14.0 alpha; no paid path |
| Job/repost foundation | Backend | Derived job index/search; remove 24-job cap; reopen job/story; re-export without analysis; version labels; `supersedes`; deletion receipt/CAS refcount | Job schema/reconciler | 100-job search p95 <300 ms; old job reopened and re-exported; delete receipt written |
| Product/UX | Founder/product | Six-screen IA; jargon removal; empty/error/loading states; 5-viewport screenshots; keyboard/accessibility; benchmark protocol; pilot recruiting; refund/eligibility copy | 0.14 build | UX checklist signed; benchmark raters recruited; guarantee copy approved |
| Mac package | Sysops | Developer ID; signing/notarization spike; macOS CI; bundled Python/ffmpeg/models; Application Support data path; launchd; diagnostics; license prototype | Apple cert; model licenses | Clean-Mac unsigned test passes; signed build in progress |
| QA | Contract QA | `node --check` all JS; Playwright screenshots; auth, disk, crash, lineage, version, purge tests | CI | Tests run on macOS, not only Linux |
| Gate review | Founder/CTO | Written day-30 review: what passed, what slipped, no paid decision | Evidence | Review filed; go/no-go for beta |

**Cut from this phase:** chapters, hook/cover matrix, legacy batch UI expansion, LAN/WAN, admin email, full repost ledger.

**Exit:** All P0 stabilization items merged. Day-30 written review. No payment collected.

---

## 2. Days 31–60 — Packaged beta

**Theme:** Mac Beta. Ship a clean-Mac install, prove the story workflow, run the pilot and benchmark.

| Workstream | Owner | Deliverables | Dependencies | Exit criteria |
|---|---|---|---|---|
| Mac package | Sysops | Signed/notarized `.app`; bundled runtime/models; launchd; offline license/trial; clean-Mac installer; backup/migration; rollback build; diagnostics bundle | Developer ID; notarization | 3 clean Macs install and run without Terminal; reboot keeps data; rollback tested |
| Story workflow | Backend | 10-story-item queue end-to-end; packet history/reload; 4:5 immutable artifacts; retry/recovery; packet refs; version labels; delete receipt; job index/search | 0.14 fixes | 10-item queue recovers; 4:5 never overwrites 9:16; old/new links labeled; delete receipt passes |
| Beta program | Founder/product | 10 pilot creators; 20-source benchmark; founder dogfood; evidence pack; support runbook; known issues; pricing/EULA/refund | Signed beta | 10 pilot Macs; benchmark complete; no P0 |
| Support | Founder | Founder primary first 50 seats; named support engineer hired/contracted before seat 51; same SLA seat 1 and 51; pause sales before SLA drops | Beta launch | Support runbook and named backup in place |
| QA | Contract QA | Clean-Mac matrix; 5-viewport matrix; crash/timeout; packet reload; auth; disk 10.4 GB; network-off audit; version handoff; delete receipt | Beta build | All tests pass or have signed waivers |
| Gate review | Founder/CTO | Written day-60 review: beta evidence, benchmark, open P0s | Evidence | Review filed; go/no-go for paid gate |

**Pilot design:** 10 creators (8 solo, 2 studio operators); 2 sources each; 4 weeks; free, no refund because no payment. Acceptance evidence: screen recording, keeper count, repair minutes, packet reload, crash test, diagnostics, delete receipt. Support <1 business day. Exit interview.

**Benchmark:** 20 sources: 5 long 90–120-minute podcasts, 3 client interviews 30 minutes, 4 courses/screencasts, 4 livestreams, 4 noisy/multi-speaker. Up to six candidates/source. All accepted stories rendered 9:16; top three accepted stories rendered 4:5; 4:5 preflight on each. Three independent blind editors; timed repair; caption errors; raw clips; rater disagreement; OpusClip Pro side-by-side; four “pretty but empty” negatives. Founder dogfood set must pass separately.

**Exit:** Day-60 written review. Clean-Mac pass. 20-source benchmark complete. No P0. Free beta continues if anything fails.

---

## 3. Days 61–90 — Paid v1 gate

**Theme:** Postable Set. Feature freeze day 61. Fix only. Run the five gates, benchmark, and dogfood. Launch only on pass.

| Week | Work |
|---|---|
| 61–70 | G1 clean Macs and license; G4 auth/admin; G5 disk; version labels; purge receipt |
| 71–80 | G2 lineage and 20-source benchmark; founder dogfood; G3 crash/timeout/queue |
| 81–90 | Re-run all gates; release checklist; paid launch or delay |

**Launch:** $249 one-time, 12 months updates, 30-day refund; alpha cohort $149 locked. Single Mac, one owner. No subscription, credits, meter, or watermark. Merchant of Record handles tax; license is offline.

**No paid release if:** any gate fails; benchmark misses the per-source floor/mean/repair threshold; founder dogfood fails; fail twice; or the schedule slips past day 90. Alpha stays free.

---

## 4. Pilot and benchmark acceptance

### Pilot

- 10 creators: 8 solo, 2 studio operators.
- 2 sources each: one long, one client/interview.
- 4 weeks.
- Free.
- Evidence: screen recording, keeper count, repair minutes, caption errors, packet reload, crash resume, delete receipt, support notes.
- Exit interview with founder.

### Benchmark gates

- No eligible source below floor: ≥3 postable for 30–120 min; ≥2 for 20–29 min.
- Mean ≥4/6; within 0.5 of OpusClip Pro.
- ≥80% of postable stories are clean (≤5 minutes repair).
- Zero caption/lineage/version mismatches.
- Packet reload, crash resume, and delete receipt pass.
- Founder dogfood: 94-minute podcast, 30-minute client interview, 2019 repost.

**Raters:** three independent working editors per clip; blind, randomized; founder as buyer-rater. Report scores and disagreement. Raw clips retained. Evidence pack visible to alpha before payment.

---

## 5. Test matrix

| Test | Pass condition | Owner |
|---|---|---|
| Clean Mac | 3 Macs, no dev tools; install, 90-min import, render, packet, reboot, data intact | Sysops |
| 20 sources | No source below floor; mean ≥4/6; within 0.5 of Opus; ≥80% of postable clean (≤5 min repair) | Product/QA |
| Lineage | Burn cues, SRT, packet captions, cover times, hashes match after edit, retry, 4:5, reload | Backend |
| Version handoff | `v{n}`/supersedes/current; old link plays old cut; no redirect; packet carries version | Backend/product |
| Crash | Kill at item 3; reopen; banner; one-click resume; one output each; no auto-run | Backend/sysops |
| Auth | Remote bind no token: all mutations 401/403; no query token; admin password-only | Backend |
| Disk | 245 GB/10.4 GB free renders 30s; below threshold 412; upload 507 | Backend/sysops |
| Packet | Close/relaunch; list; same ID/bytes; pin persisted; covers exact; expired link errors | Backend |
| Delete/purge | Explicit delete writes receipt; refcount zero; path absent; packets/artifacts protected | Backend |
| 4:5 | Crop/safe-zone/caption checks; separate immutable artifact; 9:16 unchanged | Backend/product |
| UI/a11y | 5 viewports; keyboard only; 200% zoom; empty/error/loading; no jargon | Product/QA |
| Offline | Network off: cut, caption, render, packet work; no telemetry/account | Sysops/QA |
| Rollback | Two prior signed builds; restore; backward-compatible data | Sysops |

---

## 6. Release checklist and rollback

### Checklist

- [ ] Five gate evidence filed
- [ ] Clean-Mac install on 3 Macs
- [ ] Benchmark evidence pack
- [ ] Founder dogfood evidence
- [ ] Zero P0
- [ ] Support runbook and named backup
- [ ] Public known-issues page
- [ ] EULA/privacy/refund
- [ ] Offline license/trial tested
- [ ] Diagnostics redaction tested
- [ ] Network-off audit
- [ ] 24-hour soak
- [ ] Backup/migration tested
- [ ] Rollback tested
- [ ] Release notes/versioned build
- [ ] Seat-51 support coverage confirmed

### Rollback

Keep current and two prior signed builds. Data schema backward compatible for one major version. Test restore from backup. Pull bad download, publish rollback, notify buyers. No auto-update, no telemetry.

---

## 7. Cut order if schedule slips

Cut in this order:

1. Design polish.
2. Legacy batch UI.
3. Packet history filters.
4. Klap from benchmark (keep Opus).
5. Pilot from 10 to 8.

**Never cut:** five gates, signed app, 4:5, lineage, packet reload, disk, auth, benchmark, support, rollback.

If any never-cut item fails, delay paid release; do not ship a reduced promise.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Signing/notarization slips | Start day 0; freeze features; delay paid, never ship unsigned |
| Benchmark fails | No paid launch; one selection iteration; stop after two failures |
| 4:5 client quality fails | Test 10 real client sources; fix crop; do not cut 4:5 |
| Per-source refund exposure | Eligibility; one assisted rerun; claim window first five sources/30 days; reserve |
| Job index becomes rewrite | Derived index only; rebuild from `job.json` |
| Version labels confuse clients | Superseded banner; no redirect; owner Copy current link; version in packet |
| Purge receipt overpromises | App-level proof only; disclose SSD limits |
| Support overload | 50-seat founder cap; named engineer before 51; public issues; pause sales |
| Legacy data breaks | Dry-run migration; old artifacts/shares; no rewrite |
| Installer too large | Bundle required models; optional extras; measure |
| Compatibility fixes become unbounded | Supported macOS list; 30-day fix-or-refund; budget |

---

## 9. What is explicitly not in this plan

- Paid alpha or pre-orders.
- Accounts, cloud sync, login, team seats.
- Review comments/approvals.
- Publishing, scheduling, OAuth, platform APIs.
- Analytics, virality, trends, retention ledger.
- Cloud render, credits, watermark, telemetry.
- Windows/mobile.
- Auto-resume.
- 90/180 targets; 1:1/16:9.
- New 15/30/60 batches.
- Hook/cover matrix, selection v2, chapters before 1.0.
- Full repost library/ledger before 1.0.

---

## 10. Definition of done

Paid v1 is done when all of the following are true:

1. A clean Mac installs a signed/notarized app without Terminal and activates offline.
2. One eligible source yields at least the per-source floor of postable stories.
3. Story edits, captions, 9:16, 4:5, packet, retry, crash, reload, and delete receipt preserve one object.
4. The 20-source benchmark and founder dogfood pass.
5. Support, refund, known issues, and rollback are live.
6. The CTO signs the paid gate.

Until then: **alpha only, no money.**

---

*PLAN 1.1 · Gate-driven · Feature freeze day 61 · Paid launch only on day-90 pass.*
