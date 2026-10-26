# VibeCut creator strategy — Round 1

**Date:** 2026-10-25
**Question:** What should VibeCut add or change to materially improve content creators' output, and what should it explicitly refuse?
**Mode:** Six-role debate, read-only. No code changes.
**Product state:** VibeCut v0.13.0, local-first FastAPI + vanilla JS, one job per source, in-process analysis/ingest/render pools, no accounts/cloud/durable queue, admin model routes and audit log.

---

## Key highlights

> **Key highlight:** VibeCut's genuine moat is not model access. It is local source privacy, inspectable cuts, and no upload/account/watermark tax.

> **Key highlight:** The creator and marketer want a content-operations system. The product owner and engineer want a private cutting bench. Revenue says own the solo-editor bench first.

> **Key highlight:** Story first, length second. 15/30/60 are export presets, not the creative planning primitive.

> **Key highlight:** The core loop must become boring before it becomes broad: immutable renders, resumable jobs, sequential batch, speech-timed captions.

> **Key highlight:** Packaging is the missing last mile. A thin package kit belongs in the next release, not twelve months later.

> **Key highlight:** Review/approval is a separate product unless a studio buyer prepays. Current bearer links are unsafe because they can silently retarget after a re-render.

> **Key highlight:** No virality scores, trend feeds, auto-posting, platform APIs, cloud accounts, or provider expansion.

---

## The six roles

| Role | Lens | Strongest opening claim |
|---|---|---|
| Successful content creator | Daily short-form, 1M+ followers, editor + VA | VibeCut stops at the cut; the bottleneck is 8–12 packaged, approved, on-brand posts. |
| YouTuber | 250k subscribers, long-form to Shorts | Selection and packaging are the bottleneck; a retention spike without payoff is a fake clip. |
| Video marketer / viral expert | High-volume creative testing | No editing tool makes a video travel; VibeCut can stop good footage dying at second one. |
| Product owner | Scope, segment, retention | VibeCut is a broad AI demo; it needs install, reliability, and a repeatable core loop. |
| Senior engineer | Feasibility, failure modes | Render identity, review links, restart behavior, and captions are less trustworthy than they look. |
| Revenue growth officer | Buyer, pricing, moderation | Own the solo Mac workstation first; do not subsidize an agency review product. |

---

## The central conflict

VibeCut can be:

1. **A private Mac cutting bench** — one long source in, a handful of reliable, editable cuts out, for a technical solo creator-editor.
2. **A content-operations system** — batch volume, brand packaging, collaborative approval, and performance learning for creators and small studios.

The first is reachable now and fits the architecture. The second has higher contract value but requires identity, tenancy, durable comments, notifications, moderation, and support.

The moderator sided with the private cutting bench, but not with a purely engineering-led roadmap.

> **Moderator verdict:** VibeCut should be the private Mac clipping workstation that reliably turns one long source into a handful of editable, legible cuts worth finishing — not a content-operations platform.

---

## Where all six agreed

- **Story before length.** A clip needs setup, claim, payoff. Motion alone is not a story.
- **Fixed scene-level captions are unacceptable.** Speech-timed cues are the minimum.
- **Batch is sequential independent jobs.** No parallel render farm.
- **Export-only.** No direct publishing, scheduling, or platform APIs.
- **No virality score, reach prediction, or fake certainty.**
- **Reliability beats provider breadth.** The app already has more model surface than creator value.
- **Packaging is part of the product.** Covers, titles, filenames, captions, and sidecars are not decoration.

---

## Where they fought

| Disagreement | Strongest argument for | Strongest argument against |
|---|---|---|
| Solo vs studio buyer | Creator/marketer: work dies at packaging, review, and approval; solving only the cut solves half the job. | Product owner: studio review needs accounts, permissions, notifications, and support; current bearer links are unsafe. |
| In-app review | Creator: approval latency is a real weekly cost. | Engineer: real approval needs identity and durable comments; current links silently retarget after a re-render. |
| Package vs publish-ready | Creator/YouTuber: the last mile is where hours disappear. | Engineer: VibeCut cannot guarantee platform safety, rights, or caption accuracy. |
| Measurement | YouTuber/marketer: retention data should influence the next batch. | Product owner: local CSV is fine; a dashboard is support-heavy and easy to overinterpret. |
| 15/30/60 | Product owner: clients still ask for standard lengths. | Creator/YouTuber: three lengths of one cut is not a week of content. |
| Cobalt/XHS | Existing code and optional sidecars work. | Product owner: fragile credentials, legal exposure, support drag; yt-dlp covers the main path. |
| Caption ambition | Creator: editable word-level captions and saved brand styles. | Engineer: ship speech-timed cues first; no karaoke promise. |

---

## Specialist positions

### 1. Successful content creator

**Core complaint:** VibeCut solves the hard cut and loses at the last mile. The creator's week is 2 long sources plus a client interview, targeting 10–14 clips; the team needs packaged, approved, on-brand posts.

**Top needs**

1. **Caption Studio**
   - Editable word-level captions.
   - 4–6 saved brand styles.
   - Keyword emphasis, 2–4 word line breaks, per-platform safe zones.
   - Profanity mask.
   - Caption-only preview without a full re-render.
2. **Batch queue + variant matrix**
   - Drop 10 sources, queue target/aspect/caption style per source.
   - Pause/retry/resume after restart.
   - One cut × 3 hooks × 3 covers.
3. **Package kit**
   - Cover frame picker with 3 text-overlay covers.
   - Title/hook line, description, hashtags per platform.
   - Filename convention, sidecar JSON + PNG + SRT.
4. **Timecoded review**
   - Comments pinned to timecode, resolve, approve, v1/v2 compare.
   - Expiry and revoke.
5. **Cut texture**
   - Auto punch-ins on emphasis words.
   - Dead-air/filler removal, J/L cuts, SFX at cuts, optional B-roll.
   - One-click “tighten.”

**Non-needs**

- Publishing, scheduling, analytics.
- Cloud accounts, team seats, asset DAM.
- Voice cloning and AI avatars.
- More TTS/music providers and admin knobs.
- Trend prediction, viral scores, auto-posting agents.

**Controversial take:** Kill 15/30/60 as the default. Ship one 20–25s cut with three hooks, three covers, and three titles. Keep 60s as a client deliverable.

**Switch/abandon:** Switch when one 90-minute source becomes 8 publish-ready clips in one batch. Abandon on mandatory account/cloud/watermark, fixed captions, or prioritization of publishing/avatars over throughput.

---

### 2. YouTuber

**Core complaint:** Rendering is not the bottleneck. Selection and packaging are. Retention spikes identify candidates; a spike without payoff is a fake clip.

**Top needs**

1. **Clip Set**
   - One source → six non-overlapping 20–75s self-contained cuts.
   - Each gets its own hook and title draft.
   - Batch render.
2. **Publish Packet**
   - MP4, SRT, 3 titles, 125-character description hook.
   - 3 hashtags, pinned comment, chapter block.
   - Two 1280×720 thumbnail frames.
3. **90s and 180s story targets**
   - Transcript-based self-contained score.
   - Warning when the payoff is truncated.
   - Do not pad to hit a length.
4. **Retention ledger**
   - Import a Studio CSV or enter metrics manually.
   - Store hook, title, frame, length, slot.
   - Show win rate by hook type.
5. **Channel profile**
   - Audience, banned phrases, CTA, hashtag set, title patterns.
   - Feeds hook ranking, rewrite, and title drafts.

**Non-needs**

- Native upload, publish, scheduling.
- Trending sounds and Shorts music-library sync.
- Per-platform watermark and caption skins.
- AI voice replacement as the hero.
- Thumbnail A/B or CTR prediction.

**Controversial take:** Kill 15/30/60 as the primary choice. Find six distinct stories, then derive lengths.

**YouTube boundary:** Integrate read-only Studio retention CSV and copy-ready packaging. Stay export-only for upload, scheduling, comments, playlists, end screens, thumbnail tests, monetization, and Analytics API. Export dub audio as M4A/WAV.

---

### 3. Video marketer / viral expert

**Core complaint:** No editing tool makes a video travel. Travel = demand × packaging × retention × distribution luck. VibeCut has leverage on packaging and retention only.

**Top needs**

1. **Hook set builder**
   - Five genuinely different openings: cold visual, question, stakes claim, contrarian, in-media-res.
   - 1.5–4s each.
   - Optional first-frame text.
   - Batch render.
2. **Semantic beat roles**
   - Claim, proof, conflict, reveal, reaction, instruction, punchline.
   - Require at least one claim and one payoff.
   - Flag “pretty but empty.”
3. **Muted-first preflight**
   - Caption characters/sec, line length, contrast, safe zone.
   - Speech/music masking, loudness, first-frame text.
   - One-click fixes.
4. **Series recipe**
   - Saved length, aspect, caption style, intro pattern, beat structure, audio bed, CTA.
   - Apply to many sources.
5. **Loop/payoff ending**
   - Analyze first and last two seconds.
   - Suggest trim or line order so the ending recontextualizes the open.
   - Flag “no payoff.”

**Non-needs**

- Virality score or predicted reach.
- Trend feed or trending-audio browser.
- Auto-posting or scheduler.
- Platform APIs.
- Analytics theater: best-time, hashtag generators, competitor scrapers, dashboards implying causality.
- AI hooks that invent claims.

**Controversial take:** Stop A/B testing like science. One post per variant is n=1. Use A/B for hypotheses and blinded human panels for validation. Make rejection cheap, not victory certain.

**Measurement:** Local CSV plus an eight-field manual post log (platform, date, views, 3s hold, average watch, shares, saves, comments), joined to render/hook/recipe IDs. Show median, range, n; “insufficient data” under five posts. No composite score, no leaderboard, no p-values.

---

### 4. Product owner

**Thesis:** VibeCut should be the private clipping workstation for people who already make long video. It should not be a broad AI demo with 61 routes, 8 keys, 7 workflows, admin audit, one analysis/render worker, and no resume.

**Ideal segment:** Technical solo creator-editor on Apple Silicon; podcast, interview, course, or livestream; 20–120 minute sources; 3–10 shorts/week; sometimes a second language. Secondary: a 2–5 person studio with one operator.

**Top bets**

1. **Install + activation** — signed Mac launcher, dependency check, sample project, first cut without terminal.
2. **Trust the core loop** — faster analysis, ETA, resumable jobs, batch queue, per-stage retry.
3. **Transcript-first editing + taste controls** — edit/delete/reorder lines, remove filler, lock/ban beats, “more/less like this,” captions follow.
4. **Platform pack** — 15/30/60, 9:16/16:9, cover frame, SRT/VTT, time/size estimate.
5. **Localization QC** — conditional on a paying cohort.

**Refuse or freeze**

- Cloud, accounts, team workspaces, review/approval, analytics, social publishing.
- Provider/admin expansion.
- Pro audio, mixer automation, beat sync, stem buses, mastering, SFX, voice cloning.
- Render matrix as default.
- Cobalt/XHS sidecars, playlist bulk, Docker promises, Windows parity.

**Releases**

- **v0.14 “First cut, every time” (4–6 weeks):** signed launcher, dependency check, sample project; analysis target; resumable jobs; batch up to 10; cancel/retry.
- **v0.15 “The cut you’d post” (6–8 weeks):** transcript-first editing, filler/silence removal, lock/ban beats, captions follow, taste controls, channel preset, one-click pack.

**Pricing:** License, Merchant of Record, offline key, 14-day/3-export trial, no watermark. Solo $129, Studio $299, renewals $49/year. Bring your own keys. Gate seats/support, never cut quality.

**Rulings:** Creator control > collaboration; reliability > model breadth; local file handoff > cloud links; Mac-first > parity.

---

### 5. Senior engineer

**Core warning:** The product has less trustworthy plumbing than the UI suggests.

- Jobs are one `job.json` with no index; `/api/jobs` scans and caps at 24.
- Pools are in-process: analysis 1, ingest 2, render 1.
- Restart marks active work failed and deletes tmp dirs.
- `_render_key` omits clip hash, order, preset, caption margin.
- Master key omits caption text, margin, filter version.
- Output is fixed as `reel_30.mp4`.
- `_prune_renders` ignores hook, so A/B renders delete each other.
- `_find_share_render` picks the newest matching filename, so review links silently retarget.
- Captions are scene-level; transcript segments exist but are unused.

**Top approved**

1. **Immutable render artifacts** — artifact ID hashes target, clips, order, hook, caption text/margin, audio, quality, aspect, encoder. Plan snapshot. Shares pinned to artifact. Legacy alias.
2. **Speech-timed captions** — same cues for burn and SRT; no cue crosses a clip; preview/edit; minimum duration; no karaoke claim.
3. **Browser cut preview** — Range-streamed source, 206, no local path leak, draft fallback.
4. **Batch intake** — N independent jobs plus manifest; no parallel batch render; cap and free-space preflight.
5. **Interrupted, not failed** — persist plan/options at queue time; retry reuses analysis and cached segments.

**Reject or gate**

- Accounts, teams, cloud sync.
- Direct social publishing/scheduling.
- Bulk playlist/50-link ingest.
- Cloud render farm / “4K instantly.”
- Collaborative review comments.

**Reliability hurts more than missing features**

- A/B pruning deletes renders.
- Review links play the newest cut.
- “Render again” reuses the master when only caption margin/text changed.
- Restart discards 20–60 minutes of analysis.
- 24-job history cap hides old work.
- No free-space preflight.
- Same source bytes are re-analyzed as a new job.
- Polling stops when the tab closes; no resume banner.

**Do not promise:** “publish-ready” or “platform-safe.” Promise an inspectable first cut the creator must approve.

---

## Moderator rulings

### Build now

- Immutable render artifacts
- Pinned, expiring, revocable review links
- Interrupted status and retry
- Sequential batch of 10
- Speech-timed caption cue engine
- Signed Mac installer and activation
- Offline license key and trial

### Build next

- Transcript-first editing
- Caption Studio
- Hook/title/cover variant kit
- Minimal claim/payoff checks
- Muted-first preflight
- One local channel preset
- Browser source preview
- Package kit

### Defer

- Collaborative review/approval — only as a prepaid separate SKU.
- Retention CSV/manual ledger — export metadata first.
- 90/180-second targets — use arbitrary transcript ranges.
- Localization QC — keep existing dubbing; wait for a paying cohort.
- Windows — twelve months or 20+ named prepaid prospects.
- Cut texture beyond filler removal and simple punch-ins.
- J/L cuts, SFX, B-roll libraries.

### Never

- Accounts, cloud sync, team workspaces
- Direct publishing, scheduling, platform APIs
- Analytics APIs and dashboards
- Virality scores, trend feeds, auto-posting agents
- Voice cloning and AI avatars
- B-roll/SFX marketplaces
- Parallel/cloud rendering
- Provider/admin expansion

---

## Release plan

### v0.14 — “No lost cuts, no hand-built posts”

**Order**

1. Immutable artifacts and pinned shares
2. Share expiry/revocation
3. Interrupted status and retry
4. Sequential batch of 10
5. Speech-timed caption cues
6. Thin package kit
7. Signed Mac installer and license activation

**Success**

- 70% of new installs export one reel.
- p50 time-to-first-export under 10 minutes.
- 95% of jobs complete without manual retry.
- Zero artifact collisions or review-link retargets.
- 30% week-2 repeat.

**Out**

Transcript editor, full Caption Studio, review/approval, retention ledger, providers, Windows, cloud, publishing, localization QC.

### v0.15 — “The cut you’d actually post”

**Scope**

- Transcript-first editing
- Filler/silence removal
- Lock/ban beats
- Caption Studio and safe zones
- Hook/title/cover variants
- One local channel preset
- Muted-first preflight
- Story-derived lengths

**Success**

- 2+ outputs per source.
- 40% use transcript editing.
- 60% export without opening Advanced.
- 35% four-week retention.
- 30% use the package kit.

**Out**

Review/approval, retention ledger, accounts/cloud, Windows, localization QC, provider expansion, SFX/B-roll, J/L cuts.

---

## Revenue model

Sell a license, not compute.

| Plan | Price | Includes |
|---|---|---|
| Solo | $129 | One Mac, 12 months of updates, batch included |
| Studio | $349 | Three Macs, shared local presets, priority support |
| Renewal | $49 solo / $99 studio | Continued updates/support |
| Trial | 14 days or 3 exports | No watermark |
| Onboarding | $299 optional | Studio setup |

- Bring your own API keys.
- No credits, markup, or per-minute metering.
- Gate seats and support.
- Never gate cut quality, resolution, captions, or export.
- If ten studios prepay $2,000+/year for review, spin out a separate cloud review SKU.

---

## Assistant challenge to the moderator

### 1. Put a thin package kit in v0.14

The creator and YouTuber both said the product stops at the cut. A package kit is low-risk and directly addresses that. Waiting until v0.15 leaves v0.14 as a reliability release that fixes invisible bugs but does not change the creator's day.

Minimum v0.14 package:

- MP4
- SRT
- 3 cover candidates
- 3 title candidates
- one description hook
- 3 hashtags
- safe filename
- `metadata.json`

No publishing. No platform guarantees. Just stop making the creator assemble the post by hand.

### 2. Do not rip out Cobalt/XHS; demote them

“Never supported” is too strong. They already exist, are optional, and are documented. Removing working code creates regression risk and breaks users. Freeze investment, hide them from the default path, and keep them as advanced sidecars.

### 3. Fix review-link integrity now

Collaborative comments can wait. “Review links that point at the approved file” is a reliability requirement, not a collaboration feature. Artifact pinning, expiry, and revocation belong in v0.14.

---

## Five questions that change the roadmap

1. **Who are the first ten paying buyers: solo creators or 2–5-person studios?**
   If studios exceed 40%, review moves from deferred to a prepaid pilot.
2. **Is multi-person review/approval a purchase blocker?**
   If yes, will they prepay for a separate review product?
3. **Is Mac-only acceptable for twelve months?**
   Which named prospects are Windows-only, and how much revenue is at risk?
4. **Is non-English caption/localization required for the first 100 users?**
   Which language, and captions only or dubbing?
5. **Will buyers accept an overnight sequential batch?**
   If same-hour turnaround is a purchase condition, the architecture and business model change.

---

## Round 1 verdict

> **VibeCut should be the private Mac clipping workstation that reliably turns one long source into a handful of editable, legible cuts worth finishing — not a content-operations platform.**

**What that means in practice:**

- Fix the trust layer before adding more intelligence.
- Make the cut editable before making it more automated.
- Make the post package before making the publishing integration.
- Sell a license, not cloud minutes.
- Keep the source local.

**What it does not mean:**

- Do not remain a developer-only script.
- Do not confuse a stable render with a finished post.
- Do not let “local-first” become an excuse to avoid install, onboarding, and packaging.

---

*Round 1 complete. Round 2 compares VibeCut against Submagic, Klap, OpusClip, Descript Clips, VidIQ Clipping, and Restream Clips. No code changes.*
