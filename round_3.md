# VibeCut architecture and paid-release review — Round 3

**Date:** 2026-10-26  
**Question:** Is VibeCut's architecture ready for a paid release, and what must change before money is collected?  
**Method:** Three independent 15-year specialists — backend, sysops/platform, system architecture — plus a separate CTO above them. Three loops: independent evaluation, cross-reading, final positions. Read-only. No code changes during the review.  
**Product state:** `main` at `366bd74`; 757 tests pass; CI green; internal alpha, not paid release.  
**Inputs:** [round_1.md](round_1.md), [round_2.md](round_2.md), current code at `366bd74`, the recorded UX gap list, tests, README, CI, and the live UI smoke.

**Status of this file:** The original `round_3.md` was not found in the repository or OpenCode storage. This is a retrospective record reconstructed from the three-loop review transcript and the current code. It is not a recovered contemporaneous UX transcript. Every claim below is tied to code or the recorded review; the missing original round is itself a finding.

---

## Key highlights

> **Key highlight:** VibeCut has a credible artifact spine and an unfinished paid product. The blocker is not a broken architecture; it is the absence of a shippable Mac product and a trustworthy end-to-end delivery lineage.

> **Key highlight:** All three specialists and the CTO voted **ALPHA ONLY**. No reviewer voted to sell today.

> **Key highlight:** The first paid-release blocker is a signed, notarized, no-Terminal Mac application with launchd startup and an offline license/trial. `run.sh` is a developer entry point, not an installer.

> **Key highlight:** The deeper blocker is lineage: an edited story, its caption track, its rendered artifact, its SRT, and its Publish Packet must remain the same object after retry, crash, reload, and aspect change.

> **Key highlight:** Paid v1 is the story workflow, not the legacy 15/30/60 source batch. Legacy batches remain readable and finishable; they are not the paid unit.

> **Key highlight:** `job.json` is not the paid blocker. Reconciliation and lineage are. Keep the aggregate, add indexes and a reconciler, and extract sidecars only when size/latency proves the need.

> **Key highlight:** The disk reserve is wrong for ordinary Macs. `max(5 GiB, 5% of volume)` blocked a valid ~76 MB render at 10.4 GB free on this machine.

> **Key highlight:** The missing `round_3.md` blocks a paid gate. Finish and UX cannot be certified without versioned screenshot evidence and a defect table.

---

## Product constraints

VibeCut remains:

- local-first, proprietary, closed-source;
- one long source → 3–6 editable Clip Set stories;
- speech-timed captions, editable in Caption Studio;
- one local Mac, one owner;
- admin: one **password-only** local account under `/_ductator/`;
- no SMTP, magic link, signup, accounts, cloud sync, or user login;
- export-only: no publishing, scheduling, OAuth, platform APIs, analytics, or virality scores;
- no cloud render farm, no external queue service, no team workspace.

The review treated those as hard constraints, not preferences.

---

# Loop 1 — independent evaluations

Each specialist read the same code and round records, without seeing the other two reports. The full reports are compressed here; the evidence and the disagreements are preserved.

## 1.1 Senior backend engineer

### Core claim

The artifact model is strong, but retry, recovery, packet protection, and media serving do not yet preserve the delivery contract.

### Evidence

- Retry accepts only 15/30/60 targets and drops the caption track/style: `routes_batches.py:244-246`, `routes_batches.py:292-311`.
- Render records do not store `story_id`; pruning groups every record under the job's story: `app.py:6640-6677`, `app.py:2313`. Manual plans drop story metadata: `app.py:4768-4781`.
- Legacy adoption writes a regenerated SRT and stores `caption_warning`, but public output omits warning, source, and track: `app.py:1401-1418`, `app.py:1465-1469`, `artifacts.py:775-809`.
- Artifact media is served on file existence alone with a year-long immutable cache: `app.py:4466-4486`. Media is published in place by `complete_artifact`: `artifacts.py:697-718`.
- Batch analysis/render timeouts raise without cancelling the job: `batch.py:777-780`, `batch.py:803-806`, `batch.py:817-828`.
- Admin models and login require email despite the password-only contract: `admin/routes.py:36-49`, `admin/routes.py:304-346`; `README.md:198-233`.
- The queued manifest is written before its render projection, with no recovery reconciliation: `app.py:6626-6638`, `app.py:6679-6683`, `app.py:1968-2045`.
- Packet artifact references are never persisted, so packet protection is dead: `app.py:2120-2126`, `app.py:4452`, `app.py:6878-6892`.
- Share listing can return all live capability tokens: `app.py:4515-4530`; enshrined by `tests/test_shares.py:282`.

### What is sound

- Artifact IDs hash ordered clips, hook, caption cues/style, audio, quality, aspect, and encoder. Force renders allocate a generation; ready IDs are not overwritten: `artifacts.py:221-238`, `artifacts.py:365-375`.
- Manifest path validation, atomic JSON writes, index rebuild, and pinned-artifact deletion guards are coherent: `artifacts.py:378-405`, `artifacts.py:527-565`.
- Shares pin to one artifact; legacy binding is first-write-wins, and expiry/revocation use a file lock plus atomic replace: `shares.py:207-238`, `shares.py:331-348`, `app.py:1580-1621`.
- Caption burn, SRT, and artifact captions share one cue engine; parity tests exist: `captions.py:1235-1284`, `tests/test_captions.py:505-526`.
- Batch manifests persist, item job IDs are deterministic, and the runner is sequential with pause/resume: `batch.py:227-260`, `batch.py:708-767`.

### Findings

| Severity | Finding | Impact | Fix |
|---|---|---|---|
| P1 | Retry is narrower than render and loses story/caption identity | Interrupted story renders cannot retry; 15/30/60 story retries can detach from story and restyle with the default track | Persist `story_id`, `set_id`, `caption_track_id`, style; accept story durations; rebuild from stored plan/track |
| P1 | Legacy adoption looks more trustworthy than it is | A v0.13 render can be marked ready with an SRT regenerated from today's plan, not the burned captions | Expose `caption_source`, `caption_warning`, track ID; mark adopted artifacts provisional; block share/packet until acknowledged or byte-verified |
| P1 | Media route ignores artifact readiness and caches immutably | A failed/partially finalized artifact can be served; a retry rewriting the same ID can be hidden by a one-year cache | Serve only a ready manifest; write through temp then rename; key cache to completion |
| P1 | Batch timeouts leave work running | A timed-out render continues on the single worker and blocks the next item | Cancel and drain on timeout; test timeout cascade |
| P2 | Admin requires email | Contradicts password-only constraint; unnecessary PII | Password-only schema/UI; migrate existing row |
| P2 | Crash between manifest and projection leaves an orphan | Recovery marks manifest interrupted but creates no retryable render record | Reconcile manifests back into records at startup; add crash-window test |
| P2 | Packet references never reach the job or manifest | Delete/clean can remove artifacts a packet was built from | Persist packet refs; refresh on packet deletion |
| P2 | Live review tokens are enumerable | Any local API caller can list every share capability | Remove `include_tokens` from public route or gate behind admin session + audit |

### Gate

**ALPHA ONLY.** Retry and recovery must cover every render family; adopted legacy artifacts must be provisional or byte-verified; media must be served only when ready; batch timeouts must cancel and drain.

### Confidence

**Medium.** Code evidence is direct; severity depends on whether legacy adoption and story retry are paid-release requirements.

---

## 1.2 Senior sysops / platform engineer

### Core claim

The process model is honest, but there is no shippable Mac product, and the operational envelope is not supportable for a paying creator.

### Evidence

- Process model is bounded: analysis 1, ingest 2, render 1; render segments up to 4; batch max 10 and sequential (`app.py:80-86`, `render.py:971-972`, `batch.py:48`).
- Restart is treated as interruption, not failure: live jobs/renders/artifacts become `interrupted`; active batches pause; resume requeues paused items and preserves finished outputs (`app.py:1964-2015`, `batch.py:227-260`, `batch.py:518-560`).
- Job writes are atomic; shares fsync and use a file lock; pinned/shared artifacts and jobs with live links are deletion-protected (`app.py:247-254`, `shares.py:94-112`, `app.py:6841-6846`).
- Disk preflight covers upload, path import, URL ingest, batch creation, and render submission (`app.py:3987`, `app.py:4039`, `app.py:4090`, `app.py:6618`). Coverage is good; reserve policy is not.
- Admin bootstrap is loopback-only with Host/Origin/forwarded-header checks; scrypt hashes; HttpOnly/SameSite cookie; CSRF; remote access requires HTTPS (`admin/routes.py:96-117`, `admin/routes.py:185-195`, `admin/store.py:417-440`).
- Packet build stages to a temp directory, probes MP4 integrity, hashes media and covers, and verifies the ZIP before promotion (`packet.py:148-188`, `packet.py:1580-1706`).
- CI is Ubuntu-only, checks `static/app.js` only, and the test disk is synthetic 100 GiB (`ci.yml:9-37`, `tests/conftest.py:33-35`).
- Browser state, not server state, owns the built packet and the new share token; after reload the download is refused and the token is gone (`creator.js:129-130`, `creator.js:2320-2323`, `shares.py:269-287`).

### What is sound

- The capacity promise is honest: one Mac, one analysis, one render, no cloud render farm.
- Crash semantics are deliberate: work is paused/interrupted, not silently failed; resume preserves completed items.
- Artifact identity, pinned shares, expiry/revocation, and deletion guards are materially better than a filename pipeline.
- Admin is correctly separated from creator Setup; no SMTP, signup, or account recovery surface.
- Preflight is advisory and returns a stable shortfall payload rather than deleting files.

### Findings

| Severity | Finding | Impact | Fix |
|---|---|---|---|
| P0 | No shippable Mac install or Mac release gate | Fresh Mac needs Python 3.11, ffmpeg, Swift CLT, Terminal; `run.sh` may pip-install into system Python; data defaults inside the code tree; closing Terminal kills the server; no `.app`/launchd/signing/notarization; Mac paths never CI-tested | Signed/notarized `.app`; launchd; data under `~/Library/Application Support/VibeCut`; bundled/verified ffmpeg/helpers; first-run dependency doctor; update path preserving data; macOS runner |
| P1 | `max(5 GiB, 5% volume)` reserve blocks ordinary Macs | On a 1 TB volume at 10.4 GB free, reserve is ~50 GB; every upload/path/URL/batch/render returns 412. Tests use fake 100 GiB and hide it | Cap the reserve; return 507 with exact shortfall and reclaim action; test 1 TB/10 GB free |
| P1 | Render intent is hardcoded; retry loses caption identity | Batch UI produces silent 9:16 finals with captions off; story render ignores the edited Caption Studio track; retry rebuilds a default track/SRT | Add quality/aspect/captions/track options; persist track/style; pass them on retry |
| P1 | Packet and review outputs are session-bound and incomplete | Pin comment is copy-only; cover previews are approximate; closing the tab loses the packet; review token is only copyable at creation | Persist packet refs and pin comment; list/latest packet; exact cover preview; owner-gated token re-copy |
| P1 | Recovery is pause-only and operationally blind | Batch sits paused until someone resumes; stale queued/running manifests have no watchdog; corrupt jobs skipped silently; 24-job cap; stderr logs vanish from Finder | Startup/periodic reconciler; optional auto-resume; log recovery failures; rotating file log; job index; diagnostics ZIP |
| P1 | Deleting a job does not purge uploaded footage; retention can delete packets | Client footage remains in content-addressed store 30 days or forever; delete UI does not disclose; retention can delete a job with a packet because packet refs are never persisted | Reference-count source store; purge on last job deletion or prompt; persist packet refs |
| P2 | Visual/caption verification is approximate | Contrast samples a fixed lower zone at 0.5 s, not actual style/cue; fix links open without exact artifact; legacy adoption warning not public | Return artifact/style/cue from preflight; open exact track/frame; expose caption provenance; screenshot acceptance |
| P2 | Admin and secret handling drift from constraint | Admin requires email; docs contradict; secrets plaintext and direct-write, chmodded after creation | Password-only schema/UI; Keychain where possible; atomic temp+fsync+0600 before replace |

### Gate

**ALPHA ONLY.** Clean-Mac proof; final-mile durability; operational evidence: capped reserve/507, logs/diagnostics, macOS CI/notarization, 20-source visual acceptance.

### Confidence

**Medium.** Static read-only review; no Mac runtime, no paid-install test.

---

## 1.3 Senior system architect

### Core claim

No structural collapse. The release blockers are trust-boundary and finish-contract defects, not an architecture collapse.

### Evidence

- Token/bind guard covers only `/api/*` when `VIBECUT_TOKEN` is unset (`app.py:2661-2672`). Clip-set mutation and plan routes sit at bare `/clip-sets/...` (`app.py:5306`, `app.py:5335`); the UI calls them (`static/creator.js:1366`, `static/creator.js:1754`).
- One `job.json` holds source, analysis, variants, clip sets, render projections, and artifact summaries. Reads/writes are whole-file under a process-local lock (`app.py:229-267`); finding a clip set scans every job (`app.py:5213`); schema is repaired on read (`artifacts.py:728-768`).
- Queueing writes a queued manifest, then the job record, history, and finally the artifact (`app.py:1791-1890`). Finalize errors are swallowed (`app.py:1880-1889`); startup marks leftover manifests interrupted (`app.py:2030-2041`) without creating a retryable render record.
- Packet reimplements plan reconstruction and falls back to disk when `artifacts` is absent (`packet.py:515-520`, `packet.py:573-902`). Preflight has a second copy (`preflight.py:342-499`, `preflight.py:674-746`); `app.py` has a third legacy-adoption path (`app.py:1349-1480`).
- Story length is 20–75s (`clipset.py:22-23`); story render accepts 1–180s (`app.py:5394-5395`). Batch and disk accept only 15/30/60 (`batch.py:53`, `batch.py:116-133`, `disk.py:19`).
- Reserve is `max(5 GiB, 5% of volume)` (`disk.py:17-18`, `disk.py:115-118`). At 10.4 GB free on a 1 TB volume, reserve is 50 GB and preflight returns 412 (`disk.py:136-156`; callers `app.py:6618`, `routes_batches.py:96`).
- Packet request/manifest carry titles, description, hashtags, and covers only (`packet.py:96-105`, `packet.py:1670-1689`). Pin comment is a textarea/copy button (`static/index.html:755-762`); cover preview uses poster/scene thumb (`static/creator.js:2190-2206`), not the server-extracted cover.
- CI syntax-checks `static/app.js` only, then runs pytest (`ci.yml:30-37`); `creator.js` and `admin.js` are unchecked, and no browser test exists. README says 612 tests (`README.md:1010`); current suite is 757. Share tokens are hidden after creation (`static/creator.js:2483-2485`) although the API supports `include_tokens` (`app.py:4516`); preflight fix targets are hardcoded client-side (`static/creator.js:2343-2350`).
- Admin bootstrap/login requires an email (`admin/store.py:474-480`, `admin/routes.py:37-49`), while the product constraint is a password-only local account.

### What is architecturally sound

- **Artifact identity** is the best boundary in the code: canonical JSON, source fingerprint, clip/cue/style/audio signatures, resolved encoder, generation, pinned protection, atomic manifests, and safe path validation (`artifacts.py:186-238`, `327-335`, `527-639`). Silent review-link retargeting is structurally addressed.
- **Shares are a separate capability store** with expiry, revocation, atomic writes, advisory locking, and artifact binding (`shares.py:15-17`, `199-238`).
- **Batch has a clean backend Protocol** and durable per-batch manifest, independent of FastAPI, with item-level failure isolation and corrupt-manifest rejection (`batch.py:10-29`, `79-94`, `227-260`).
- **Captions have one deterministic cue engine** and persisted tracks; burn-in, SRT, and previews share the cue path (`captions.py:1235-1275`, `1347-1392`).
- **Packet verification is real**: ffprobe/MP4 checks, SHA-256 copy verification, ZIP integrity, and idempotent packet IDs (`packet.py:148-229`, `1314-1336`, `1456-1505`).
- Admin audit chaining and local bootstrap hardening are solid, but the identity model exceeds the stated product scope.

### Findings

| Severity | Finding | Structural impact | Fix |
|---|---|---|---|
| P1 | Auth boundary is route-shaped, not application-shaped | Any future bare-prefix route bypasses the remote-bind guard; a non-loopback instance without a token exposes creator mutations and plan reads | Mount every creator route on one `APIRouter(prefix="/api")` with router-level auth; delete bare aliases; add a remote-bind/no-token test |
| P1 | `job.json` is database, index, and migration log | Whole-document contention, O(all jobs) lookup, no versioned migration; legacy caption/cue counts normalized at write sites only | Move clip sets/packets/renders/artifact indexes to per-job SQLite or document stores with schema versions and one migration command; keep `job.json` as a pointer |
| P1 | Render record and artifact manifest have no atomic handoff | Crash can leave a job record saying ready while its artifact is queued/interrupted, or leave an orphan manifest with no retry path | Make finalize idempotent/transactional; derive readiness from manifest plus media; add repair command and orphan sweep |
| P1 | Three plan/cue resolvers reconstruct missing history independently | Preflight can validate a synthesized plan that was never rendered; packet can package captions from a different plan | One `resolve_cut(job_dir, ref)` returning artifact, plan, cues, media; fail closed; migrate legacy jobs once |
| P1 | Target domain is split between story duration and 15/30/60 | The product unit is a 20–75s story, but batch and disk cannot estimate or batch it; story-length reels work individually and fail at scale | Shared duration-based render spec; estimate by seconds; accept story targets in batch; or remove arbitrary targets |
| P1 | Static free-space reserve ignores actual write size and volume | A valid render is blocked at 10.4 GB free on a large disk; paid-support incident, not safety | Bound reserve to operation size plus a small floor; expose override; test 1 TB/10.4 GB-free |
| P1 | Packet contract stops before the post | Pin comment lost; cover preview can differ from ZIP cover; packet JSON not a complete reconstruction | Add pin comment, chapters, cover plan to `PacketRequest`, `packet.json`, ZIP; server cover preview using same extraction |
| P2 | Release verification and UI contracts are server-only | Creator UI regressions can ship; preflight actions/share-token recovery are inferred by client, not guaranteed by API | Playwright screenshot matrix for six screens; `node --check` all JS; return finding action objects; allow local token re-copy |

### Gate

**ALPHA ONLY.**

1. Trust boundary: every creator route authenticated consistently; remote-bind/no-token test; idempotent artifact finalize/recovery; 10.4 GB-free render succeeds.
2. Finish parity: pin comment, chapters, cover plan persisted in packet JSON/ZIP; cover preview matches packaged cover; preflight findings carry explicit enabled actions.
3. Release proof: browser screenshot QA for Clip Set, Captions, Preflight, Packet, Artifacts, Queue; CI checks all JavaScript; signed/notarized launcher and offline license/trial.

### Confidence

**High** structural; **medium** paid-release timing and installed-base constraints.

---

# Loop 2 — cross-reading and shared thinking

The specialists read each other's Loop 1 reports. The cross-read changed the severity model.

## 2.1 What each specialist corrected

### Backend

- Treated middleware as an API boundary; bare `/clip-sets` routes bypass the remote-bind guard.
- Missed that paid software has no shippable Mac artifact.
- Framed render intent as retry only; story render also ignores the edited caption track and is UI-fixed to final/9:16/captions, while batch defaults to 9:16 with captions off.
- Conceded that “three plan/cue resolvers” overstates cue duplication: cues have one engine; plan reconstruction is duplicated.

### Sysops

- Treated `VIBECUT_TOKEN` as covering the creator API; it only gates `/api/*` when unset and bound off-loopback.
- Said review tokens were only copyable in the creating session; true in UI, false in the API (`include_tokens=true`).
- Missed that a timed-out batch item raises but leaves its job running, blocking the next item.
- Withdrew “job.json is a paid blocker” and “media P1” as stated; media is hardlinked after render, so partial bytes are less likely, but orphan/cache risk remains.

### Architect

- “No P0” was wrong: no shippable `.app` is the first paid-release blocker.
- Artifact identity is sound; artifact transitions are not.
- Missed that packet build never writes refs back to the job, so deletion protection has nothing to find.
- Withdrew the claim that story cannot do 16:9/4:5; the route accepts aspect/captions. The remaining story defect is caption-track selection.

## 2.2 Shared positions

### A. Artifact spine and `job.json`

The artifact spine is sufficient for a paid local v1. `job.json` is not a paid P0 if job count is capped, writes stay atomic, and a startup reconciler maps manifests back to render records. It is P1 support/scalability debt, not a reason to build a database before launch.

**Dissent:** the architect held that the aggregate is a paid blocker requiring extracted indexes and schema versions. The CTO later overruled the “full rewrite” reading and accepted reconciliation.

### B. Recovery

Pause-only plus explicit resume is acceptable. Durable auto-resume is not required. A watchdog for stale queued manifests and one-click resume is required.

**Dissent:** sysops wanted auto-resume; backend and architect did not. The CTO later chose one-click resume, never auto-resume.

### C. Mac release

Signed/notarized `.app`, launchd/startup handling, and offline license/trial are P0. Paid launch cannot be CLI-only for this buyer.

### D. Top five paid blockers

1. Mac install/signing/license.
2. Auth boundary.
3. Artifact finalize/recovery/trust.
4. Story/batch target and caption lineage.
5. Disk reserve.

### E. Targets and lineage

Fix lineage now. Do not keep arbitrary 1–180 story targets. Ship one domain: the story's stored duration (20–75s), plus explicit 15/30/60 compatibility exports. Batch and story renders must share it and honor caption/aspect options.

**Dissent:** sysops initially wanted to keep 1–180 story targets; sysops later conceded one target domain.

### F. Packet

Titles, description, hashtags, covers, and pin comment are core metadata. Chapters are optional. ZIP is a handoff convenience, not identity; `packet.json` is canonical. The CTO later required ZIP to be always downloadable but derived.

### G. Auth and admin

Fix now. Authenticate all mutating routes, not just `/api/*`. Make the single admin password-only as specified; email is not a security improvement and contradicts the product constraint.

### H. Disk reserve

The shared engineering position:

```text
reserve = min(5 GiB, max(2 GiB, 5% of volume))
allow only when free - required >= reserve
```

At a 245 GB volume and 10.4 GB free, reserve is 5 GiB, leaving 5.4 GiB; a 30-second final render must succeed. Current `max(5 GiB, 5%)` demands 12.25 GiB and falsely blocks.

### I. Missing `round_3.md`

Yes, confidence drops. The remedy is not another opinion round; it is an evidence-only addendum with screenshot QA and 20-source acceptance. Absence should block the paid gate.

## 2.3 Loop 2 revised findings

| Severity | Finding | Evidence | Gate |
|---|---|---|---|
| P0 | No shippable Mac install or Mac release gate | `run.sh:5-13`; `ci.yml`; `README.md:16-50` | Block paid release |
| P1 | Auth boundary is route-shaped: `/api/*` guarded, bare `/clip-sets` reachable | `app.py:2661-2672`, `5306`, `5335`; `creator.js:1366,1754` | Block paid release |
| P1 | Artifact finalize/recovery/provenance is not transactional | `app.py:1791-1890`, `6626-6683`, `1401-1469`; `artifacts.py:775-809` | Block paid release |
| P1 | Render intent/lineage split: story ignores edited track; batch defaults; retry drops identity | `app.py:5410-5422`, `5113-5117`; `routes_batches.py:480-493`, `244-246`, `292-311` | Block paid release |
| P1 | Disk reserve rejects ordinary work at 10.4 GB free | `disk.py:17-18`, `115-118`; `app.py:6618` | Block paid release |
| P1 | Packet final mile is session-bound and incomplete | `packet.py:96-105`, `1670-1689`; `creator.js:2190-2207`, `2320-2323`; `app.py:2120-2126` | Block paid release |

## 2.4 Remaining dissent after Loop 2

- **`job.json`:** backend and sysops called it P1 debt; architect called it a paid blocker. CTO later: keep it; reconciliation is the blocker.
- **Auto-resume:** sysops wanted it; backend and architect preferred one-click. CTO later: never auto-resume.
- **Story targets:** sysops initially kept 1–180; backend and architect removed it. CTO later: stored duration only.
- **ZIP:** backend called it convenience; sysops and architect called it core. CTO later: derived but always downloadable.
- **Admin email:** backend and architect said fix now; sysops called it P2. CTO later: remove it; password-only.
- **Paid batch scope:** no consensus. CTO later: story-only paid v1; legacy batch compatibility only.

---

# Loop 3 — final specialist positions

All three independently voted the same gate. No specialist moved to SHIP.

| Role | Final gate | One-line reason |
|---|---|---|
| Backend | **ALPHA ONLY** | Install requires Terminal; artifact/render lineage is not trustworthy |
| Sysops | **ALPHA ONLY** | Credible private alpha; not a supportable paid Mac product until install, auth, lineage, disk, and packet finish are proven |
| Architecture | **ALPHA ONLY** | Credible spine; no paid-shippable Mac product; delivery/lineage contract not trustworthy |

## 3.1 Backend final

**Top five must-fix**

1. P0 shippable Mac release.
2. P1 auth boundary.
3. P1 artifact finalize/recovery/provenance.
4. P1 story/batch caption-target lineage.
5. P1 disk reserve.

**Binding choices**

- Keep `job.json`; add extracted index/reconciler; no storage rewrite.
- No auto-resume; one-click resume.
- Render at stored story duration; remove arbitrary 1–180; 15/30/60 are compatibility exports.
- Pin comment core; ZIP core; chapters optional.
- Reserve `min(5 GiB, max(2 GiB, 2% of volume))`.
- Password-only admin; no email.

**Dissent:** sysops on auto-resume/arbitrary targets/legacy batch domain; architect on `job.json`/chapters.

**Falsifier:** 10 clean Mac pilots; 95% batch completion; zero collisions/retargets; 10.4 GB-free render; 20-source visual acceptance.

**Confidence:** medium. Missing round 3 lowers finish/packet confidence.

## 3.2 Sysops final

**Top five must-fix**

1. P0 Mac install/signing/license.
2. P1 auth boundary.
3. P1 render/caption lineage and timeout.
4. P1 disk reserve.
5. P1 packet final mile.

**Binding choices**

- Keep `job.json`; extract indexes; P1 debt, not blocker.
- One-click resume, not auto.
- One target domain at stored story duration; batch by `story_id`.
- Pin and `packet.json` core; ZIP on demand; chapters optional.
- Reserve `min(5 GiB, max(2 GiB, 5% of volume))`.
- Remove admin email; password-only.

**Dissent:** architect on `job.json`/chapters; backend on ZIP convenience/1 GiB floor.

**Falsifier:** five acceptance tests on a clean Mac; auth bypass, data loss, or packet/retry mismatch moves to HOLD.

**Confidence:** medium. Missing round 3 lowers finish/UX confidence.

## 3.3 Architecture final

**Top five must-fix**

1. Mac package/signing/license.
2. Delivery and packet identity.
3. Recovery and timeout semantics.
4. Disk reserve.
5. Auth and admin identity.

**Binding choices**

- `job.json` is a paid blocker; keep as pointer, extract indexes, no rewrite.
- No auto-resume; one-click plus watchdog cancels stale work.
- Remove arbitrary 1–180; story stored duration; batch by story ID.
- Pin core; chapters optional; ZIP core; `packet.json` canonical.
- Reserve `min(5 GiB, max(2 GiB, 5% of volume))`.
- Remove admin email; password-only.

**Dissent:** backend on `job.json`/ZIP/1 GiB floor; sysops on auto-resume/arbitrary targets/admin email.

**Falsifier:** signed notarized clean-Mac build; 20-source acceptance ≥4 publishable/source; 95% no-retry; zero caption/artifact hash mismatch; 10.4 GB-free render.

**Confidence:** medium-high code facts; medium paid timing. Missing round 3 lowers finish/UX confidence.

---

# CTO final consolidation

## 4.1 CTO verdict

**ALPHA ONLY.**

All three specialists are right about the artifact spine and right that the missing Mac package, signing, and license is the P0. The deeper paid blocker is not any single disagreement: VibeCut cannot yet prove that an edited story, its captions, its rendered artifact, and its Publish Packet remain the same object after retry, crash, reload, or aspect change. The 757 tests and artifact hashes are real strengths, but they cover an engine, not a sellable Mac product.

The CTO overruled the architect on `job.json`: storage shape is not the blocker; reconciliation and lineage are. The CTO overruled the backend and sysops on legacy batch: paid v1 is story-based only.

## 4.2 Binding decisions

### 1. `job.json` — keep; not a paid blocker

It stays the aggregate/pointer. Artifact manifests and the per-job index are the source of truth. Writes are already atomic (`app.py:247-254`); the artifact index exists (`artifacts.py:583-614`) and is merged into the job (`artifacts.py:737-745`). Add render/packet summaries, schema versions, and startup reconciliation.

Extract render/clip-set sidecars only if `job.json` exceeds 2 MiB or p95 save exceeds 25 ms. The architect's “full rewrite before paid” is overruled; the reconciliation concern is accepted.

### 2. Auto-resume — never

Startup marks active work interrupted (`app.py:1974-1993`), shows a banner, and offers one-click resume. No automatic re-execution: it can spend model/render time and overwrite user intent.

Add a watchdog that cancels the child process group on timeout. Current batch timeout raises without cancelling (`batch.py:803-805`), leaving a render alive while the next item starts.

### 3. Story target — stored story duration, never 1–180

Paid story render uses the Clip Set story's duration. The current default is 30 seconds, not the story, and silently clamps to 180 (`app.py:5393-5395`; `clipset.py:1614-1616`). That creates an artifact whose `target` disagrees with its output length.

Reject stories over 180 seconds with an actionable error; do not clamp. Aspect is explicit and preserved; captions default on; quality is `final` by default, `draft` allowed. Legacy 15/30/60 Quick Cut remains compatibility only, outside the paid story flow.

### 4. Batch — story-only, max 10, sequential

One item is `(job_id, clip_set_id, story_id)`, rendered at stored duration with the story's current caption track and chosen aspect. No 15/30/60 paid batch.

Existing alpha 15/30/60 batches remain readable and finishable; no new ones. Current batch accepts only 15/30/60 (`batch.py:53`, `batch.py:120-133`), and retry skips anything else (`routes_batches.py:244-246`). That cannot carry the paid unit.

### 5. ZIP, pin, chapters

`packet.json` is canonical; media, captions, and covers are copied and hashed from the artifact. ZIP is derived and always downloadable; keeping the current eager build at finalize is acceptable, but never treat ZIP as identity.

Add the pinned comment to `PacketBody`, `packet.json`, the sidecar, and reload. Artifact pinning remains the deletion protection. Chapters are post-v1.

Today the packet has no pin field (`packet.py:1670-1689`; `app.py:6853-6860`), the UI pin is copy-only (`static/creator.js:778,807`), and closing the browser loses the packet (`static/creator.js:604,2320-2323`).

### 6. Disk reserve — exact rule

```text
reserve = min(5 GiB, max(2 GiB, 5% of volume))
allow only when free - required >= reserve
```

Render/batch preflight returns 412 with exact `shortfall_bytes`; upload write failure returns 507.

At 245 GB volume and 10.4 GB free, reserve is 5 GiB, leaving 5.4 GiB: a 30-second final render must succeed. Current `max(5 GiB, 5%)` demands 12.25 GiB and falsely blocks (`disk.py:17-18`, `disk.py:115-118`).

### 7. Admin — password-only

Remove email. Use one fixed local-admin identity, 12+ character password, loopback-only bootstrap, no signup, no SMTP. Current `create_user` rejects any account without an email (`admin/store.py:474-480`), and bootstrap/login require it (`admin/routes.py:311`, `admin/routes.py:324-346`). Migrate the first existing alpha account.

### 8. Auth — default-deny

Every route is denied unless explicitly public. Remove the bare `/clip-sets` aliases (`app.py:5306`, `app.py:5335`) or gate them; stop accepting `?token=` (`app.py:2682`); require bearer auth for every creator mutation when bound beyond loopback. Loopback no-token remains the supported single-user mode.

Admin keeps its own session and CSRF. `include_tokens` stays owner-only and off by default; current listing can enumerate review tokens (`app.py:4516-4529`).

### 9. LAN / remote — local only

Paid v1 supports loopback. LAN review is opt-in, token-gated, best-effort; no WAN, cloud relay, tunnel, or remote admin. The paid promise is one Mac, one owner.

## 4.3 Top five paid-release gates

| # | Gate | Acceptance test | Owner |
|---|---|---|---|
| 1 | **Signed, no-Terminal Mac install + license** | Clean Mac with no Python, ffmpeg, Homebrew, or Terminal: drag signed/notarized app to Applications, launch, activate trial/license, import a 90-minute source, render one story, export packet, reboot, relaunch, data intact; `codesign --verify` and `spctl -a` pass | sysops + product |
| 2 | **Story → artifact → packet lineage + keeper rate** | 20 sources, 3–6 stories each. Edit captions/style/margin, clips, and 4:5 aspect; render; retry; assert burned cues, SRT, `packet.json` captions, cue hash, style hash, artifact SHA, and cover times all match. Close/reopen and download same packet; re-copy review link. At least 4 of 6 stories publishable per source; zero caption/artifact mismatches | backend + product |
| 3 | **Crash, timeout, and batch recovery** | Batch 10 story items; SIGKILL at item 3. Restart: no auto-run, banner appears, one-click resume produces exactly one output per item. Timeout cancels ffmpeg, next item starts, `pgrep ffmpeg` is empty afterward | backend + sysops |
| 4 | **Auth and admin boundary** | With `VIBECUT_HOST=0.0.0.0` and no token, `PATCH /clip-sets/{id}`, every `/api` mutation, and every admin mutation return 401/403. With token, creator works. Password-only bootstrap/login works; no email field; no token in query strings or logs | backend |
| 5 | **Disk preflight honesty** | 245 GB volume, 10.4 GB free: 30-second final render starts and completes. Below required + reserve: 412 with exact shortfall. 20 GB upload below threshold: 507, no partial output | backend + sysops |

Any failed gate means no paid release.

## 4.4 30 / 60 / 90-day plan

### Days 0–30 — Stabilize alpha

Ship only:

- default-deny auth
- remove bare `/clip-sets` aliases and query-token auth
- password-only admin
- story duration/track/aspect fix
- packet pin, persistence, reload
- batch timeout cancellation
- startup reconciler
- disk rule
- macOS CI runner
- `node --check` for `creator.js` and `admin.js`

Cut:

- chapters
- 90/180 targets
- legacy batch UI
- arbitrary targets
- admin email
- LAN/WAN

### Days 31–60 — Package beta

- signed/notarized `.app`
- bundled Python/ffmpeg/models
- offline license/trial
- clean-Mac installer
- backup/migration
- story batch
- 5-viewport screenshot QA
- 10 pilot Macs

Cut: hook/cover matrix, variants, folder-vs-ZIP options, Windows.

Defer: job-store rewrite and auto-resume.

### Days 61–90 — Paid v1 only if all five gates pass

Invite-only paid release with EULA, support, refund path, and renewal.

Ship only:

```text
source → Clip Set → captions → story render → packet → export
```

Cut everything else.

## 4.5 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Signing/notarization or bundled runtime slips | High | High | Freeze features now; start Developer ID and clean-Mac CI immediately; keep alpha fallback; no paid date promises |
| Caption/artifact divergence after edits or retry | Medium | High | One canonical caption-track ID; hash assertions across burn/SRT/packet; kill-and-retry tests; packet SHA verification (`packet.py:1605-1616`) |
| Crash/timeout leaves orphan render or duplicate output | Medium | High | Process-group kill, watchdog, startup reconciler, idempotent record keys, one-click resume only |
| Auth bypass on LAN or token leakage | Medium | High | Default-deny, remove aliases/query tokens, loopback default, owner-only token listing, admin session/CSRF |
| Selection below buyer bar | Medium | High | 20-source blind acceptance; fewer than 4 publishable of 6 means no paid release, regardless of packaging |

## 4.6 Buyer message

**Do not buy VibeCut today.** It is an internal alpha.

What works is real:

- local custody;
- one source → 3–6 editable stories;
- speech-timed captions;
- immutable render artifacts;
- a self-contained packet.

What is missing is the product:

- signed installer that needs no Terminal;
- offline license;
- reliable packet reload;
- crash recovery;
- clean-Mac support story.

VibeCut refuses to promise:

- selection parity with OpusClip;
- “platform-safe” captions;
- virality or reach;
- zero data loss;
- remote review;
- Windows;
- cloud sync;
- auto-publishing;
- chapters;
- 90/180-second targets;
- exact cover previews today;
- review-link recovery today;
- legacy 15/30/60 batch;
- LAN security beyond the token boundary.

## 4.7 The missing round 3

Its absence lowers confidence in **finish and UX**, not in the artifact spine. Code-level gaps were verified: packet loss on reload (`static/creator.js:604,2320-2323`), approximate covers (`static/creator.js:2190-2207`), tokens copyable only at creation (`static/creator.js:2614-2622`), pin absent from the manifest (`packet.py:1670-1689`). Screenshot-level QA, stale queued-manifest behavior, legacy caption-count normalization, and conditional preflight links cannot be verified without the review.

**Process fix:** every review round is a mandatory versioned artifact. No paid gate review without `round_3.md` containing:

- 5-viewport screenshots per screen;
- 10 scripted UX scenarios;
- severity/owner defect table;
- UX-owner sign-off;
- links from every claim to a screenshot or `file:line`.

Absence blocks the gate, not just lowers confidence.

## 4.8 Final CTO verdict

> “VibeCut is a credible private alpha with a real artifact spine, but I will not sell it until a clean Mac can install it without Terminal and prove, after edits, retries, crashes, and reloads, that the story, captions, artifact, and packet are the same object.”

---

# What changed from Round 1 and Round 2

Round 1 and Round 2 established the product direction:

- the unit is a Clip Set plus Publish Packet;
- finish parity is table stakes;
- private batch is expected infrastructure, not a moat;
- local source custody, flat cost, immutable artifacts, and one-pass finish are the defensible difference;
- no cloud accounts, publishing, platform APIs, analytics, or virality scores;
- the Mac launcher and offline license were already in the build-now list.

Round 3 confirms the product strategy but changes the release emphasis:

- the engine is ahead of the product;
- the Mac installer/license is not a parallel nice-to-have; it is the first P0;
- story lineage is the central paid blocker;
- legacy 15/30/60 batch is compatibility, not the paid unit;
- the artifact spine is worth keeping;
- `job.json` is debt, not a rewrite;
- 757 tests are not product evidence.

The CTO’s plan turns the strategy into a paid-release gate rather than more feature scope.

---

# Open questions after Round 3

1. **When does the 20-source selection benchmark run?** Round 2 required it before paid release. Round 3 treats it as part of Gate 2, not a separate research task.
2. **How many alpha jobs predate caption tracks?** If many, legacy SRT mismatch is a P1 trust issue, not P2.
3. **Is 16:9/4:5 required for the first paid cohort?** Story render already accepts aspect; the question is whether the paid UI exposes it at launch.
4. **Will buyers tolerate manual resume after a crash?** CTO says one-click resume is enough; sysops initially wanted auto-resume.
5. **Is LAN review in scope?** CTO says local-only; any LAN path remains opt-in and token-gated.
6. **What is the exact legacy caption byte-parity policy?** CTO requires provisional marking or byte verification; the migration threshold is still a product call.
7. **Does the first paid build include chapters?** CTO defers chapters; the architect called them core packet metadata. Current decision: post-v1.

---

# Review close

**Final gate:** ALPHA ONLY.  
**Paid release:** blocked until all five gates pass.  
**Architecture:** credible artifact spine; lineage, install, auth, disk, and packet finish are the work.  
**Product:** private Mac story workstation, not a content-operations platform.  
**Next move:** execute the 0–30 day stabilization plan, then package beta, then run the five gates on clean Macs and 20 real sources.

*Round 3 complete. Retrospective reconstruction; original round_3.md was not found. No code changes were made during the review.*
