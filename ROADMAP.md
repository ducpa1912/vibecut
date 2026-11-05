# VibeCut Roadmap

**Status:** R2 atomic trim merged. Tag `refactor-2-done`.
**Main:** `0f68275`
**Suite:** 1491 passed, 7 skipped.
**Release status:** internal alpha; paid release gates remain open.
**Source of truth:** this file replaces all earlier plan and roadmap files. Discussion records and handoffs remain historical.

---

## 1. Where we are now

### Current product

One local Mac workstation for turning long video or a finished cut into short posts:

```text
IMPORT → CHECK → STORIES → EDIT → FINISH
```

- **Check** detects baked text, speech, music, faces, quality and rights, then recommends clean-first or compose-first.
- **Stories** finds sentence-bound stories with hook, payoff and evidence.
- **Edit** is one document per story/aspect: Clean, Reframe, Motion, Color, Text, Captions, Audio.
- **Finish** renders 9:16/4:5, builds packet v2, preflight markers, versions, review links.

Platform: macOS 26+ on Apple Silicon. Local-first; cloud only for explicit music/voice/transcription/text routes with the creator's key.

### Shipped by wave and round

| Wave / round | Tag | Shipped |
|---|---|---|
| Pre-wave 0.1–0.13 | — | Core cut, deep read, render speed, audio replacement, CAS sources, Smart Cut, captions, translation, URL ingest, admin console |
| Wave 1 Foundation | `wave-1-done` | Edit model/versions/compiler, audio split (`stt`/`tts`/`music`), Check backend with OCR boxes and tracklets, Studio shell |
| Wave 2 Engine | `wave-2-done` | Render hooks (`pre/post` filters, motion, layer burn), Transcript v2/word timings, TTS + packs, Studio Edit base |
| Wave 3 Flows | `wave-3-done` | Compose text/FX/LUT/stickers, Clean Flow 1, music/mix/dub, Studio Check/Edit/Clean/Effects/Audio |
| Wave 4 Finish | `wave-4-done` | Packet v2, preflight markers, migration + Classic fallback, Studio Finish/Setup, server Clean auto-fill, music candidates |
| QA round 1 | merged `2564ac8` | 25 QA fixes: captions, scroll, error copy, source-missing, cancel reading, story cards, queue progress, autosave, rights record |
| R1 | `refactor-1-done` | Rights policy module + Studio Rights, story picks/trim handles, render performance + Studio read cache |
| R2 | `refactor-2-done` | Atomic trim transaction, layer/caption ripple, fail-closed stale Edit, both-direction Studio trim, undo/rebind, Playwright drag acceptance |

### Current state

- 1491 tests pass; 7 opt-in skips.
- Studio is the default UI; Classic remains behind `?classic=1` / Settings.
- Rights lock is on by default; watermarks always refused; screen text never cleaned; handles/logos need a per-video tick.
- Clean is on by default; `VIBECUT_ENABLE_CLEANUP=0` disables it.
- Packet v2 and Edit/trim identity are wired.
- R2 trim is browser-tested on synthetic fixtures.
- Wave 5 hardening is not done: no `wave-5-done` tag, no signed/notarized app proof, no 90-minute performance proof, no founder acceptance run.

### Pre-wave version history (compressed)

`0.1` core cut · `0.2` deep read · `0.3` render speed · `0.4` audio replacement · `0.5` storage/speed · `0.6` script/delivery · `0.7` cloud config · `0.8` bilateral crop · `0.9` review/keyboard/translation · `0.10` voice/music/upload · `0.11` rewrite/history/UI · `0.12` URL ingest · `0.13` admin console.

---

## 2. Open items and next steps

### Paid-release gates

- **G1:** signed/notarized Mac app, launchd, offline license, clean-Mac install.
- **G2:** 20-source story benchmark, keeper rate, lineage.
- **G3:** crash/timeout/resume proof.
- **G4:** auth/admin; rights lock is now server-side.
- **G5:** disk reserve behavior.
- Founder acceptance: 10 creators, videos A and B, all manual tables.

### Wave 5 hardening (not done)

| Item | Owner / note |
|---|---|
| Founder checklists `docs/testing/w3-live-checklist.md`, `w4-founder-checklist.md`, R1/R2 tables | Founder → Claude records |
| Pack install/remove HTTP route; real SHA-256 pins/URLs | Wave 5 packaging |
| 90-minute performance: frame endpoint, proxy, residual sampling | Wave 5 performance |
| Frame/vs/final 60 fps path; overlapping caption fallback | Wave 5 |
| Animation: arrow/underline/sticker draw-on still static | Wave 5 polish |
| Beat snap only within ±120 ms; A/B music preview plays raw bed | Wave 5 |
| Voice-fit not persisted; loudness only when a render exists | Wave 5 preflight |
| Packet cover silently falls back to ffmpeg/poster | Wave 5 bug bash |
| `MAX_CLEAN=32`; Vision sampler once failed | Wave 5 |
| Cloud music unverified: no MiniMax key; Lyria 401 | Founder key |
| HeyGen free tier ends 2026-11-30; fallback to MiniMax | Check after date |

### R2 trim carry-overs

- Classic still changes ranges via `PATCH /clip-sets`; render fails closed with Repair, but Classic has no trim UI.
- Packet stale check is per story, not per aspect: a stale 4:5 blocks a 9:16-only packet.
- Timeline shows the whole ±90 s pool, so a short story can look small.
- `localStorage` job-id reads remain in `shell.js`, `effects.js`, `clean.js`, `audio.js`.
- `story_start` pins keep their output offset when the story becomes shorter.
- Founder R2 manual tables are unrun.
- Deferred: A/B compare, approved-version lock, transcript-range trim, word-boundary trim.
- Rejected: split/merge, multi-range, frame-level freeform trim, silence/beat trim, auto-filler removal, auto-deleting outside layers, cloud/multi-user.

### QA round 1 partials that still matter

- Stickers are not drawn in live playback; browser fonts are approximate; exact frame is truth.
- CJK runs use Arial Unicode/Hiragino regular; ZWJ emoji and flags render as components.
- Loudness gate skips only near-silence; music-only audio still runs STT.
- Older clip sets keep character-share timing until stories are found again.
- First render after upgrade re-encodes once (`layers-v2`/`text_skin` cache keys).
- Founder retest of the 25 QA items remains a manual checklist.

### Post-launch scalability (watch)

- Round 6 panel ran five app servers with Check, proxy and render on one Mac. Check stalled at 63% and a 4:5 render took about 6 min, versus 5–40 s alone.
- This is likely a local-machine limit, not an app bug. After launch, measure concurrent jobs: one ffmpeg/vision worker pool per machine, a queue cap, and an honest ETA that counts the queue ahead.

### R3 founder-session fixes (planned, from round_6.md)

Source: founder session 1 (`docs/testing/founder-session-1/`) and the round 6 panel. Four tracks with disjoint files, so they can be built in parallel and merged T1 → T4.

**T1 Dub and voice workflow** (`static/studio/edit/layers/audio.js`, `audio.py` messages, `story_queue.py` failure reason)
- Dub gets a source-language confirm and a target-language picker; Studio writes `audio.translate`.
- Voice-over and Dub get an editable script box (prefilled from the transcript or translation).
- Queue refuses a Dub with no target, with the reason in place; a failed queue row shows the server's message, never only "Render failed".
- Audio tab order: Voice first, Music second. Dub and Voice-over copy explains the real difference.
- Translated captions stay deferred until Dub renders end to end.

**T2 Finished-video library** (new `routes_library.py`, new `static/studio/library.js`, the `shell.js` video picker)
- `GET /api/artifacts`: every finished render across jobs, with job, story, shape, quality, version, date, and file size.
- Studio "Your videos" splits into Finished and Sources tabs. Finished shows thumbnail, story, shape, version, date, play, download and open in Finish.
- Sources show the job title, not `source.mp4`.
- Read-only over existing render records; no new storage.

**T3 Edit navigation and Finish honesty** (`static/studio/edit/index.js`, `static/studio/finish.js`, `preflight.py`, `app.py` queue route, frame route)
- Sticky Back to Stories and Next: Finish in Edit, with save state beside them.
- Preflight resolves clip-set story ids; never a masked 404.
- Queue is idempotent: Queue all twice attaches to the active item, no failed duplicate row, no extra version.
- Finish summary counts every shape and story queued.
- Render-queue ETA: hidden until there is a measured rate, never 0.0 while running, never jumps back up within one stage.
- Frame request at `t = duration` is clamped to the last frame instead of 422.

**T4 Import/Check progress and speech** (`pipeline.py`, `stt.py`, `detect.py`, `static/studio/check.js`, `disk.py`)
- Stage-weighted, monotonic progress; a heartbeat line during crop and speech; an ETA after 10%; a Cancel that stops ffmpeg.
- No 68% "Tracking crop" plateau; copy matches the real length of the source.
- Speech auto-detects language instead of defaulting to `en`; retry speech in place; the warning tells "off" apart from "engine returned nothing".
- Disk refusal shows free, reserve and shortfall in GB; a path import that copies nothing doesn't demand the full reserve.

**Deferred:** client approval and delivery log, the per-source rights record, single shared read between Import and Check, per-workflow Translate/Voice/Music routing in Studio, batch templates.
**Rejected (round 6):** more voice engines, auto-Dub with a cloud default, auto-publish, auto-queueing every shape on import.

**Founder manual test after merge:** rerun the session 1 flow on A, C and B with codegen recording; check Dub with a target, the library after four renders, Back/Next, and Check progress without plateaus.

### Special cuts (planned, not built)

Founder note, 2026-11-05. Today a change of shape crops one picture to fit: Framing sets one zoom and place per scene. A special cut changes the layout when the shape changes, such as a vertical video made into a horizontal story, or the opposite. There can be dozens of templates, for example:

- Split screen, top and bottom, or left and right.
- Focus area: one part of the picture fills the frame.
- Cut to centre.

To work out when this is planned: whether a template applies per scene or to the whole cut, how it fits the Edit document and the fast preview, and how layers stuck to the video behave when one source shows twice in a frame.

### Next order

1. R3 founder-session fixes (Dub, library, Back/Next, honest progress, speech).
2. Run founder manual checks for Waves 3/4, R1, R2 and R3.
3. Wave 5 packaging/performance/bug-bash.
4. Paid-release gates G1–G5 and the 20-source benchmark.
5. Deferred trim features only after paid trim is proven.

---

## 3. Product contracts still in force

### Edit contract

- One `Edit` per story/aspect, schema 1; immutable versions in `jobs/<id>/edits/<edit_id>.json`.
- Pointer: `job["story_edits"]["{set_id}:{story_id}:{aspect}"]`.
- Fields: `id`, `version`, `parent`, `hash`, `renderer_version`, `story_ref`, `aspect`, `clean[]`, `reframe`, `motion[]`, `color`, `graphics[]`, `captions`, `audio`.
- `story_ref.clip_hash` must equal `edits.clip_snapshot_hash(story.clips)`.
- Optional `pin` (`story_start`/`story_end`) and `hidden`; absent fields hash exactly as before. `anchor` is accepted as a trim-input alias; `pin` is canonical.
- Coordinate rule: Clean in source coords; Graphics/Captions in output coords; Motion changes the crop window.
- Hash: sha256 over canonical JSON, includes layer assets and renderer version.
- Stale Edit must never render. Story render/Finish/packet return 409 `edit_stale` when a pointer exists but the Edit is stale/unreadable. Legacy plan path only when no pointer exists.

### Transcript v2

`jobs/<id>/transcript/transcript_v2*.json`; immutable. Fields: `id`, `source_hash`, `engine`, `model`, `language`, `created`, `hash`, `segments[]`, `words[]`, `quality`. Caption tracks record `transcript_id`. Word timings are measured; interpolation only for legacy.

### SourceReport / Check

`POST/GET /api/jobs/{id}/check`. Tracklet:

```text
{id, kind, box{x,y,w,h} source-normalized 0–1, ranges[{start,end}], text_sample, confidence}
```

Kinds: `subtitle`, `title`, `lower_third`, `handle_or_logo`, `watermark`, `credit`, `screen_text`.
`screen_text` is dense UI/document text; never pre-filled for Clean, never counted as baked captions.
Watermark always refused; handle/logo needs the per-video tick; rights not attested locks Clean.

### Rights policy

- `rights.py` is the only policy source; `GET /api/rights/policy`, `job.rights_policy`, `POST /api/settings` `rights.lock`.
- Lock on: import needs the ownership tick; lock off: import open, but handle/logo cleaning still needs the per-video tick.
- Watermark always refused; screen_text never cleaned, with lock on or off.
- No request body or localStorage decides policy. Turning the lock on does not rewrite saved Edits.

### Atomic trim

```text
POST /api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/trim
  expected_revision
  start_sentence
  end_sentence
  dry_run?
```

- One `update_job` commit; story range + Edit versions + caption track + pointers commit together or not at all.
- Revision bump on every range change; mismatch is 409 `revision_mismatch`.
- Pool is the contiguous source range between neighbouring stories, ±90 s; both directions.
- Time mapping through old/new clips: inside moved, partly clipped, fully outside kept as `hidden` with old times, never deleted.
- Captions rebuild/reflow in the same transaction; manual text kept; cached track rejected on clip-hash mismatch.
- Receipt: old/new range, moved/clipped/outside/pinned layers, caption counts.
- Undo restores range/Edit/captions as a new version with a new undo token. Artifacts and review links never change.
- Finish fails closed; no plan fallback while an Edit pointer exists.
- `GET trim`, `POST trim/undo`, `POST trim/rebind`; `dry_run` writes nothing.

### Packet v2 / identity

- Packet includes `edit.json`, `audio.json`, `music.json`, layer assets, frame-endpoint covers.
- Artifact identity covers `edit.hash`, `transcript_id`, audio/music hashes.
- Review links show `Edit vN`.
- Packet route: `POST /api/jobs/{job_id}/artifacts/{artifact_id}/packet`.

### Never-list

- No accounts, cloud sync, team seats, subscription, credits, per-clip meter.
- No publishing, scheduling, OAuth, platform APIs, analytics, virality scores.
- No watermark removal.
- No generative face/logo repair, avatars, voice cloning, stock B-roll.
- No full-source 4K cleanup, auto-resume, auto-posting, telemetry.
- No silent retargeting, overwriting approved artifacts, or plan fallback when an Edit exists.
- Do not delete layers or artifacts during trim.

### Local/offline rule

Import, Check, Stories, Edit, render and packet work with the network off. Cloud is explicit: music generation, cloud voices, optional STT and AI text. Cloud uses the creator's own key.

---

## 4. Superseded history

| Old file | What it planned | What replaced it |
|---|---|---|
| `PLAN.md` | Paid-v1 execution: stabilize, package beta, paid gates, pilot, benchmark | Wave/Studio work; paid gates remain in §2. Contracts and gates absorbed here. |
| `BUILD_PLAN.md` | Detect → Dissect → Compose, Flow 1/2, SFX, filters, music, sub-agent waves | Superseded by studio revamp; the workflow is now Check → Stories → Edit with Clean/Text/Captions/Effects/Color/Audio. |
| `REVAMP_PLAN.md` | Studio product plan: Edit document, Check, STT/TTS/music, packs, UI, milestones | Executed through Waves 1–4, R1/R2; lasting contracts are in §3. |
| `WORKPLAN.md` | Wave roles, ownership, review rules, handoffs | Waves complete; no ongoing planning authority. Handoffs remain historical. |
| `ROADMAP.md` (old) | Engineering version history, shipped checklist, provider notes, future cloud proposals | This file. Old cloud/open-core proposals are dropped. |
| `ROADMAP_V1.md` | Paid-v1 product roadmap | Superseded by Studio work; paid gates remain. |
| `ROADMAP_V2.md` | Paid-v1 + conditional cleanup/overlay roadmap | Superseded by revamp and R1/R2. |
| `docs/REFACTOR_PLAN.md` | R1 rights lock, Studio rights, story picks/trim, performance | Executed in R1; rights/trim/perf contracts remain. |
| `docs/R2_TRIM_PLAN.md` | Atomic trim transaction, caption reflow, fail-closed render, Studio trim, acceptance | Executed in R2; atomic trim contract remains in §3. |
| `docs/cloud-plan.md` | Open-source + cloud control plane, queues, multi-tenant, billing | Design exploration, never implemented. Product remains local-first; no cloud accounts or hosted control plane. |

---

## 5. Pointers

- Discussion records: `round_*.md`.
- Wave/round handoffs: `docs/handoff/**`.
- QA evidence/checklists: `docs/testing/**`.
- Product brief: `FOUNDER_BRIEF.md`; paid-v1 PRD: `PRD.md`; setup and feature docs: `README.md`, `docs/*.md`.
- Tags: `wave-1-done`, `wave-2-done`, `wave-3-done`, `wave-4-done`, `refactor-1-done`, `refactor-2-done`.

**Rule:** this roadmap is the only active plan/roadmap. If a proposal is not in §2 or a contract in §3, it is historical.
