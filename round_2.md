# VibeCut creator strategy — Round 2

**Date:** 2026-10-26
**Question:** After researching six competitors and cross-reviewing each other, what should VibeCut build, defer, or never build for content creators?
**Method:** Six read-only agents. Public web research on 2026-10-26. Each specialist then received the other five positions and issued a final stand. The revenue growth officer moderated.
**Round 1 record:** [round_1.md](round_1.md)
**Product state:** VibeCut v0.13.0, local-first FastAPI + vanilla JS, one job per source, in-process analysis/ingest/render pools, no accounts/cloud/durable queue, admin model routes and audit log.

---

## Key highlights

> **Key highlight:** Competitor evidence moved finish parity from “next” to “now.” OpusClip, Submagic, Klap, Descript, VidIQ, and Restream already bundle captions, reframe, packaging, publishing, and batch capacity at $14–$29/month.

> **Key highlight:** Private batch is table stakes, not a moat. Every competitor has batch capacity. VibeCut’s defensible difference is local source custody, flat cost, immutable artifacts, and one-pass finish.

> **Key highlight:** The buyer will not pay for worse cuts. Selection quality is the top willingness-to-pay risk. Bad captions and missing packets cause refunds even when selection is good.

> **Key highlight:** Closest threat is OpusClip, not Descript. Opus owns the same “long source to post-ready clips” job and price anchor. Descript is the adjacent transcript-editing threat.

> **Key highlight:** The unit is a Clip Set plus Publish Packet, not one 15/30/60 reel.

> **Key highlight:** 90/180-second targets, timecoded review comments, retention dashboards, blinded panels, publishing, analytics, and virality scores are out.

> **Key highlight:** Do not launch paid on a privacy story while losing the selection benchmark. Privacy cannot rescue worse cuts, and packaging cannot rescue a weak first minute.

---

## Competitor matrix

Public list prices observed 2026-10-26. Vendor claims about users, accuracy, virality, and view lift are unaudited.

| Competitor | Position | Core clip workflow | Captions / reframe / package | Team, batch, publishing | Visible price | Main weakness |
|---|---|---|---|---|---|---|
| **Submagic** | Caption-first short editor for creators, agencies, teams | Upload or YouTube → Magic Clips → text-based trim, silence removal, B-roll, auto-zoom | 123-language styled captions; auto-zoom/eye-contact; AI hook titles/descriptions; no clear cover tool | Shared workspace; scheduler/analytics; 15/40/100 videos per month; 2/5/30-minute source caps | $19/$39/$69 per member/mo; annual $12/$23/$41; Magic Clips add-on reported at $19/mo for 10 long uploads | Long-source workflow is an add-on with caps; commodity cloud editor |
| **Klap** | Cheap clip volume for creators and teams | YouTube/file → AI topics → clips; virality score; AI Reframe 2; light editor | 52 languages; styled captions; split-screen/screencast/gaming layouts; recommended copy; cover/title support not verified | 100/300/1,000 clips/mo; Pro+ “for teams” but seats not stated; publish/schedule; API/MCP/Zapier | Annual $14/$39/$94 per month; monthly reported $23/$63/$151; trial, no permanent free tier shown | Clip-count meter; annual-first pricing; opaque score; shallow editor |
| **OpusClip** | Category leader: any-genre AI clipping plus publishing | Local/URL → ClipAnything uses speech, visual, sound, emotion; virality score; prompt/reprompt; text/timeline edit | Animated captions; object-tracking reframe; 9:16/1:1/16:9; auto hook; title/description/hashtag; brand templates | Team workspace; scheduler; API/MCP; bulk export; credits/minutes; free watermarked/expiring exports | Free limited/watermarked; Starter $15/mo; Pro $29/mo; Business custom | Credit meter; feature sprawl; unverifiable virality claims; cloud custody |
| **Descript Clips** | Full editor with clips attached; podcasters and teams | Import/record → transcript → Underlord finds clips → full NLE edit → comments/collab | Dynamic captions; manual aspect/crop/layout; social copy, YouTube descriptions, chapters; no cover tool | 1–5 seats; comments/live collaboration; share pages; no social scheduler verified; media-hour pricing | Free 1h/720p; Hobbyist $16; Creator $24; Business $50 per person/mo annual; enterprise custom | Clipping subordinate to heavy NLE; per-seat/media-hour cost; cloud |
| **VidIQ Clipping** | YouTube growth suite with clipping bolt-on | YouTube only → AI moments → cut/crop/caption; light editor | Caption presets/custom; safe-zone placement; speaker focus; title/keyword/best-time tools; thumbnail maker separate | Individual plans; enterprise roles; no visible review workflow; credit-metered clipping | Free 150 credits; Boost $19/mo or $199/yr; MAX $49/mo or $468/yr; clipping reported at 9 credits per input minute | YouTube-only; credit-gated; shallow editing; analytics-suite scope |
| **Restream Clips** | Live-first streaming suite with clips add-on | Stream/upload → speech-cue highlights → five auto clips → edit-by-text, auto B-roll, multi-aspect | Auto captions, 52 languages; auto reframe/cut between speakers; no hook/cover/package verified | 50/100/250 clips add-on; 5 auto clips/source; 2 seats Business; social posting; no review verified | Clips +$19/+$29/+$59 on Standard $19 / Professional $49 / Business $239; no free clips | Add-on locked to streaming; shallow finish; live-first |

---

## What the market proves

1. **Cloud clipping is a feature bundle, not a category with a moat.** Every product sells the same chain: ingest → clips → captions → reframe → package → publish.
2. **The low end is crowded at $14–$29/month.** Opus owns free acquisition; Klap and Submagic own the cheap monthly bundle; Descript owns editing depth.
3. **The category’s shared delusion is causal virality.** Opus and Klap sell scores; VidIQ sells best-time and trend advice; none publishes calibration. Treat them as marketing.
4. **Long-source caps create a real opening.** Submagic’s 2/5/30-minute caps and Opus’s credit/minute pricing punish 90–120-minute podcasts and livestreams.
5. **Publishing is the last mile, not the moat.** All six have some scheduler/publishing path. Replicating it adds OAuth, token custody, platform churn, retries, and support.
6. **Transcript control is table stakes.** Descript, Submagic, Opus, and Restream all edit clips through text. Scene-level captions and timeline-only editing are not credible.
7. **Finish is the visible gap.** Opus wins because the output is packaged, not because its score is scientifically true. Submagic wins captions; Descript wins editing control; none closes local privacy plus one-pass packaging.

---

## Specialist findings

### 1. Successful content creator

**What the competitors say to this creator**

- Submagic is the best finish stack: captions, auto zoom, B-roll, SFX, brand kit. But Magic Clips is an add-on, and the 2/5/30-minute caps punish long sources.
- Klap has the cleanest trial and transcript editing plus batch export, but clip-count limits punish long sources and the virality score is opaque.
- OpusClip has the most complete post-ready stack: brand templates, auto hook, title/description/hashtag, scheduler, team seats. A 90-minute podcast costs 90 credits before keeping one clip.
- Descript has the strongest editor and review/collaboration, but it is a full NLE with per-seat pricing; social scheduling is absent from the Clips page.
- VidIQ is YouTube-only and credit-gated; Restream is live-first and shallow.

**Final stand**

- **Build now:** Caption Studio; Clip Set batch; Publish Packet.
- **Build next:** transcript-first cut with prompt exclusions; lightweight time-coded review comments; cut texture.
- **Defer:** 90/180-second targets; causal learning/blinded panels.
- **Never:** native publishing/scheduling/analytics; avatars, voice cloning, default stock B-roll.
- **Biggest gap:** finish parity. The same cut must leave with editable captions and a Publish Packet in one pass. Selection is the entry ticket; finish is the gap.
- **Red line:** client footage never leaves the machine or requires an account.
- **Verdict:** companion, not replacement, until captions, batch, and package ship. Then primary for private assembly.

**Correction after cross-review**

- The unit is a Clip Set, not one 15/30/60 reel.
- Muted-first preflight and promise–payoff audit matter.
- Durable queue is part of quality.
- Transcript is the control surface.
- 90/180 remains a different product.
- Blinded panels are research, not a creator tool.

**Most wrong role:** Product owner. Descript is an NLE with clips attached; Opus and Submagic are the actual competitors because they deliver post-ready clips. Transcript editing is a feature to copy, not a competitor to fear.

**To the moderator:** Price at $129–$349 only after a 90-minute source produces six post-ready clips in one unattended local run.

---

### 2. YouTuber

**What the competitors say to this YouTuber**

- OpusClip is closest to discovery: ClipAnything, prompt/reprompt, 0–15-minute lengths, tracking reframe, auto hook, title/description/hashtags. But it does not read YouTube Studio retention.
- Descript is closer for finishing: transcript editing, comments, Studio Sound, chapters. But it is not batch-first and has no verified social scheduler.
- Submagic, Klap, VidIQ, and Restream all have pieces of packaging, but none closes the YouTube packet: titles, description hook, hashtags, pinned comment, chapters, two covers, SRT, MP4.
- VidIQ has YouTube data but is a clipping bolt-on; Restream is live-first; Klap is volume-first.

**Final stand**

- **Build now:** Clip Set; YouTube Packet; caption parity.
- **Build next:** selection v2 with prompt-to-clip exclusions and multi-signal selection; durable batch/immutable identity; retention ledger + promise–payoff audit.
- **Defer:** channel profile; deep time-coded review.
- **Never:** publishing/scheduling/analytics; virality scores; trends; best-time; avatars; stock B-roll; voice cloning.
- **Biggest gap:** keeper rate on 20–40-minute sources. Four of six publishable means win; two of six means no packet saves it.
- **Red line:** no mandatory cloud upload, account, or per-minute meter for core clipping.
- **Verdict:** remain conditional. Clip Set + Publish Packet or VibeCut becomes a finishing companion to Opus.

**Correction after cross-review**

- Private batch is a sharper wedge than “privacy,” but not unique.
- Durable batch moves up.
- Immutable render identity is product, not plumbing.
- Promise–payoff audit belongs in the retention ledger, not a blinded panel.
- Product owner is right that transcript is table stakes, wrong about the threat.
- 15/30/60 is still a false default.

**Most wrong role:** Product owner. Descript is an editor with clips, not a clipping machine. A YouTuber switches when keeper rate rises, not for a transcript-native timeline. Runner-up: marketer; a solo creator does not have a blinded panel.

**To the moderator:** Fund the private flat-cost Mac workstation that turns one 25-minute upload into six packaged Shorts; not a worse OpusClip.

---

### 3. Video marketer / viral expert

**What the competitors say to this marketer**

- All six sell more clips. None sells causal learning.
- Opus has the best iteration velocity: ClipAnything, prompt-to-clip, custom lengths, bulk export, API. It gives more shots, not a better experiment.
- Klap sells volume plus a score. Submagic sells caption polish. VidIQ sells packaging context. Restream sells live-to-social. Descript sells craft.
- Every score, trend feed, best-time recommendation, and “feed the algorithm” claim is unfalsifiable or confounded.

**Final stand**

- **Build now:** transcript-native cut + speech-timed captions + brand styles; Clip Set + Publish Packet; durable batch/queue + immutable render identity.
- **Build next:** selection audit (semantic roles, promise/payoff, “why this clip” evidence); hook set builder + blinded 2-second panel on review links; muted-first preflight.
- **Defer:** 90/180 and prompt-to-clip exclusions; local CSV/manual post ledger.
- **Never:** virality score, trend feed, best-time, scorecards; auto-posting, scheduler, OAuth, platform APIs, cloud comments; avatars, voice cloning, stock B-roll.
- **Biggest gap:** finish, not discovery. The cuts are competitive; captions, transcript edit, and package are not.
- **Red line:** no feature whose success depends on a platform account or a reach promise.
- **Verdict:** VibeCut is choice for the cut, companion for distribution.

**Correction after cross-review**

- Transcript-native editing is table stakes, not a caption feature.
- The publishing unit is Clip Set + Publish Packet; reject a fixed six, not the set.
- Batch is a trust product.
- Selection quality is the first purchase criterion.
- Hook testing survives inside a set.
- Read-only review links are enough; do not build comments.

**Most wrong role:** Creator. “Private batch is unmatched” is false. Opus has bulk export and an API; Descript is a desktop editor with batch media handling. Privacy is a segment, not a capability moat. Time-coded review pulls VibeCut toward collaboration and contradicts the local wedge.

**Secondary error:** YouTuber’s fixed six-story quota and Studio-retention read contradict the refusal of platform data. Clip Set yes; fixed six no.

**To the moderator:** Build the private flat-cost Mac workstation that turns one long source into a publish-ready set with transcript-accurate captions and honest evidence; no score, scheduler, or six-clip quota.

---

### 4. Product owner

**What the competitors say to the product owner**

- Opus defines the category vocabulary and owns the broadest ingest-to-publish loop. It is the benchmark, not a product to copy feature-for-feature.
- Descript is the closest control threat because it owns transcript editing, the wedge VibeCut needs. Its users are the closest match.
- Submagic owns captions and team workflow; Klap owns cheap volume; VidIQ owns YouTube data; Restream owns live ingest.
- All six have publishing, team/collab, or analytics surfaces that VibeCut cannot match without becoming a different product.

**Final stand**

- **Build now:** selection proof + control (20-source benchmark vs Opus/Klap, lock/ban beats, visible hook/payoff evidence); durable local batch 10–20 with resume/retry/immutable identity; caption parity.
- **Build next:** transcript-first cut editing; Clip Set + Publish Packet; promise–payoff audit + muted-first preflight.
- **Defer:** 90/180 and prompt exclusions; localization/dub expansion.
- **Never:** cloud/accounts/publishing/analytics/review portals; avatars/stock B-roll/eye contact/SFX/voice cloning/scores.
- **Biggest gap:** selection quality. Captions and pack are table stakes; a worse first cut loses before export. Must beat or tie Opus/Klap on 20 real long sources or it is a privacy premium for worse output.
- **Red line:** veto cloud review, publishing, or a virality score before the 20-source selection benchmark passes. No account requirement in the next two releases.
- **Verdict:** viable niche, not category winner; repositioning required.

**Correction after cross-review**

- Packaging unit becomes Clip Set + Publish Packet.
- Reject blinded panel; adopt promise–payoff audit + muted-first preflight.
- Selection quality is the top WTP risk ahead of install.
- Studio price moves to $349.
- Batch is valuable, not a moat.
- YouTuber is second-wrong: Studio retention reads conflict with refusing platform data.

**Most wrong role:** Marketer. Blinded panel and causal learning are research services, not software; one creator, no distribution data, no statistical power. Promise–payoff audit and muted-first preflight are the usable asks.

**To the moderator:** Fund the private flat-cost Mac workstation, but gate the next release on beating Opus/Klap selection on 20 real long sources. Otherwise $129 buys a support burden, not a business.

---

### 5. Senior engineer

**What the competitors say to the engineer**

- Opus has the hardest clipping-specific moat: elastic ingest/render, scoring, reframe, scheduler, team, API in one loop.
- Descript has the deepest editor moat: transcript-native NLE, media graph, collaboration, export surfaces.
- The local product can match most of the cut/caption/reframe core. It cannot match distribution or a full editor without becoming a different product.
- The current plumbing is less trustworthy than the UI suggests: render identity, pruning, share retargeting, captions, restart behavior.

**Final stand**

- **Build now:** immutable render artifacts; speech-timed editable captions; transcript-based clip editing.
- **Build next:** durable private batch; Publish Packet; selection/hook lab v2.
- **Defer:** time-coded review/comments/approvals; public API/MCP/Zapier.
- **Never:** social publishing/scheduling/analytics; virality scores, trends, best-time as causal truth.
- **Biggest gap:** postable last mile — accurate captions plus one-click package. Discovery is a quality race; captions and packaging are the credibility gate.
- **Red line:** veto any batch, review, or share expansion until render identity and queue recovery are fixed. No “ready to post” while cues are whole-scene.
- **Verdict:** local power tool, not cloud suite. Cannot match Opus distribution or Descript NLE.

**Correction after cross-review**

- Transcript-based cut editing moves to build-now.
- Private batch moves to build-next.
- Descript is the closest control threat; text-first selection is cheaper parity than a 20-source queue.
- Accept Clip Set + Packet framing; flat local pricing defensible.
- Publishing, teams, and virality scores remain structural traps.

**Most wrong role:** Creator. Private batch is not unmatched; all six have batch/queue, and local batch is one Mac. Twenty long sources through one analysis worker with no durable queue is an outage, not a moat. Product owner is second-wrong: match transcript editing should mean sentence-safe clip selection, not a transcript NLE.

**Fact corrections**

- Descript Free watermark is not explicit on the pricing page.
- Klap transcript editor and batch export are unverified on the public pages fetched.
- OpusClip Pro $29/mo omits the annual equivalent.
- “Category leader” and “virality score” are marketing claims, not verified efficacy.
- Creator’s “private batch unmatched” is contradicted by competitor batch/credit models.

**To the moderator:** Fund a flat-price local workstation that wins the postable last mile — captions, transcript cut, immutable outputs — not a worse OpusClip.

---

## Cross-review: what changed

| Role | Changed position | Did not change |
|---|---|---|
| Creator | Clip Set is the unit; muted-first and promise–payoff matter; queue is quality; transcript is control | 90/180 is a different product; no publishing; no score; finish is the gap |
| YouTuber | Private batch moves up; immutable identity is product; promise–payoff audit belongs in retention | Clip Set #1; YouTube Packet; caption parity; no publishing/score |
| Marketer | Transcript editing is table stakes; Clip Set + Packet; batch is trust; selection quality is first purchase criterion | No score/trends/auto-posting; local CSV only; read-only review |
| Product owner | Clip Set + Packet; reject panel; selection is top WTP risk; Studio $349 | No cloud/publishing/teams; transcript/captions table stakes; batch not moat |
| Engineer | Transcript cut moves to build-now; batch moves to build-next; Descript is control threat | Artifact identity and captions prerequisites; no publishing/teams/score |

---

## Moderator final ruling

### What changed from Round 1

Round 1 treated caption/package parity as v0.15 work and “private batch” as a wedge. Competitor evidence reverses that:

- Finish parity is table stakes and moves into v0.14.
- Private batch is demoted from moat to expected infrastructure.
- OpusClip replaces Descript as the benchmark.
- Transcript editing moves up because competitors normalize it.
- Review comments, retention dashboards, blinded panels, and 90/180 targets move out.
- The $129–$349 license remains defensible only as flat-cost ownership plus local custody, not feature superiority.

### Final consensus

1. The unit is a **Clip Set plus Publish Packet**, not one 15/30/60 reel.
2. Speech-timed captions, transcript control, packaging, and immutable artifacts are table stakes.
3. No cloud accounts, publishing, platform APIs, analytics theater, or virality scores. Local flat-cost Mac remains the segment.

### Unresolved conflicts

1. **Selection vs finish:** Creator and marketer say the last mile is the gap; product owner and YouTuber say bad selection makes packaging worthless.
2. **Review vs handoff:** Creator wants comments next; marketer says read-only links suffice; product owner and engineer refuse collaboration.
3. **Set shape:** Creator wants six; marketer wants variable 3–6; YouTuber wants keeper rate over quota; 90/180 and prompt exclusions remain contested.

### Rulings

- **#1 WTP risk: selection quality.** Buyers will not pay for worse cuts.
- **#1 release risk: finish parity.** Bad captions and missing packets cause refunds even when selection is good.
- Ship both. Do not trade one for the other.
- **Closest threat: OpusClip.** It owns the same job, price anchor, and “post-ready” promise. Descript is the adjacent control threat, not the benchmark.
- **Private batch: table stakes.** Every competitor has batch capacity. Build it; never market it as unmatched.
- **Moat:** local source custody, flat cost, artifact integrity, one-pass finish.
- **90/180s: DEFER.** Keep arbitrary export lengths in the transcript editor; no dedicated targets in the next two releases.
- **Timecoded review comments: NEVER in VibeCut core.** Read-only links pinned to artifacts with expiry/revocation. Separate paid review SKU only after ten studios prepay.
- **Retention ledger: DEFER.** Export render metadata as CSV; no in-app analytics, platform APIs, or post log.
- **Blinded panel: REJECT as software.** Use blinded raters internally for selection benchmark, not as a customer feature.
- **Mac-only: YES for 12 months.** Windows only with 20 named prepaid prospects.
- **Pricing:** $129 Solo / $349 Studio, 12 months updates, $49/$99 renewals, 14-day trial with 3 exports, offline key, no watermark, no account. Studio buys three Macs and onboarding, not collaboration.

---

## Final build list

### BUILD NOW — 5

1. **Trust core**
   - Immutable artifact identity: clips, order, hook, caption text/margin, audio signature, quality, aspect, encoder.
   - Hook-aware pruning.
   - Pinned, expiring, revocable shares.
   - Durable sequential batch of 10.
   - Resume/retry.
   - Free-space preflight.

2. **Caption Studio**
   - Speech-timed editable cues.
   - Brand style and safe zones.
   - Caption-only preview.
   - Identical cues for burn-in and SRT.

3. **Transcript-native Clip Set**
   - 3–6 non-overlapping stories.
   - Sentence select/reorder/exclude.
   - Lock/ban beats.
   - Visible hook/payoff evidence.
   - Variable count, not fixed six.

4. **Publish Packet**
   - MP4s, SRTs.
   - Three titles.
   - Two cover frames.
   - 125-character description hook.
   - Hashtags.
   - Filenames and sidecar JSON.

5. **Mac launcher and license**
   - Signed app.
   - Dependency check.
   - Sample project.
   - Offline trial/license.
   - No terminal.

### BUILD NEXT — 4

1. **Selection v2:** multi-signal ranking, prompt exclusions, three hook candidates per story, explainable evidence.
2. **Hook/cover matrix:** three hooks and three covers per story, sequential and artifact-safe.
3. **Promise–payoff audit + muted-first preflight:** dangling claims, truncated payoff, caption density, safe-zone contrast, loudness.
4. **Tighten:** filler/silence removal and simple punch-ins. No J/L cuts, SFX library, or B-roll.

### DEFER

- 90/180 targets
- Retention ledger
- Channel profiles
- Localization/dub expansion
- Windows
- Browser preview

### NEVER

- Cloud accounts/teams/review portals
- Publishing/scheduling/OAuth/platform APIs
- Analytics/virality/trends
- Avatars/voice cloning/stock B-roll
- New provider/admin expansion
- Cobalt/XHS
- Parallel/cloud render

---

## Competitive position

Against **OpusClip**, win on private source custody, flat cost, no credits, immutable local artifacts, and one-pass packaging; lose on breadth, free acquisition, publishing, and brand.

Against **Submagic**, match caption quality and brand kits; beat its long-source caps and add-on stacking.

Against **Klap**, beat transparent selection and finish; ignore its score.

Against **Descript**, match transcript control; beat focused Clip Sets and batch; ignore NLE collaboration.

Against **VidIQ**, be source-agnostic and finish better; ignore YouTube analytics.

Against **Restream**, serve offline long-form; ignore live streaming.

**One sentence:** VibeCut is the local, flat-cost clipping bench that turns one long source into a small set of private, post-ready cuts with accurate captions and packaging — not a publishing platform, editor suite, or virality oracle.

---

## 20-source selection benchmark

Use 20 real sources, 20–120 minutes:

- 8 podcasts/interviews
- 4 courses/screencasts
- 4 livestreams
- 4 noisy or multi-speaker recordings

Run the same sources through VibeCut, OpusClip Pro, and paid Klap at defaults. Generate up to six candidates per source. Three blind raters score every clip.

A clip is **publishable** only if:

- self-contained
- hook in the first three seconds
- completes its payoff
- no more than two caption errors
- needs no more than five minutes of human repair

### Ship only if

- mean ≥4.0 publishable clips per source
- no worse than 0.5 clips behind OpusClip
- ≥80% of publishable clips need ≤5 minutes repair
- 95% of batch jobs complete without retry

### Stop if

- mean <3.0/6
- more than 1.0 clip behind OpusClip
- >20% of clips need >10 minutes repair

Results between 3.0 and 4.0 get one selection iteration. No launch and no v0.15 scope expansion. Two consecutive failures mean stop the paid launch.

---

## Next two releases

### v0.14 — “Postable Set” (10–12 weeks)

**Scope:** Build-now items 1–5.

**Order:**

1. Artifact identity
2. Queue recovery
3. Caption cue engine
4. Transcript-span mapping
5. Clip Set
6. Packet
7. Installer/license in parallel

**Metrics:**

- selection benchmark gate passes
- 70% of trial installs export one set
- 95% batch completion without retry
- 30% week-2 repeat

**Out:** 90/180, review, ledger, panels, publishing, cloud, Windows, localization, variants, provider/admin work.

### v0.15 — “Selection Edge” (8–10 weeks)

**Only if v0.14 benchmark passes.**

**Scope:** Build-next items 1–4.

**Order:**

1. Selection v2
2. Audit/preflight
3. Hook/cover matrix
4. Cut tightening

**Metrics:**

- keeper rate +15% over v0.14
- 2 post-ready outputs per source
- 40% use transcript editing
- 60% export without Advanced
- 35% four-week retention

**Out:** everything deferred or never above.

---

## The one thing not to do

> **Do not launch paid on a privacy story while losing the selection benchmark.**

Privacy cannot rescue worse cuts. Packaging cannot rescue a weak first minute.

---

## Final verdict

> VibeCut is a viable niche paid product if it becomes the best private, flat-cost way to turn one long source into 3–6 post-ready Mac-made clips. It is a losing bet if it stays a broad local AI demo or chases Opus’s cloud feature set.

---

## Sources

Accessed 2026-10-26. Prices are public list prices, before tax and promotions. Vendor claims are unaudited.

- Submagic: <https://www.submagic.co/> · <https://www.submagic.co/pricing> · <https://www.submagic.co/features/magic-clips>
- Klap: <https://klap.app/> · <https://klap.app/pricing>
- OpusClip: <https://www.opus.pro/> · <https://www.opus.pro/pricing>
- Descript Clips: <https://www.descript.com/clips> · <https://www.descript.com/pricing>
- VidIQ Clipping: <https://vidiq.com/features/clipping/> · <https://vidiq.com/plans/>
- Restream Clips: <https://restream.io/lp/clips> · <https://restream.io/pricing>

**Unverified or conflicting:** Klap monthly prices, seats, free-tier limits, and transcript/batch claims; Submagic permanent free tier, Magic Clips add-on inclusion, and speaker tracking; OpusClip exact credits, annual pricing, Starter seats, and watermark details; Descript Free watermark, monthly prices, and social scheduling; VidIQ lower-tier clipping access, export terms, and direct publishing; Restream Clips watermark, resolution, and scheduling; all vendor counts, accuracy, virality, and view-lift claims.
