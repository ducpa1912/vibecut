# VibeCut — Founder Brief

**Status:** Source document for PRD 1.1.
**Date:** 2026-10-26.
**Author:** Founder, solo content creator.
**Use:** Raw product input, not market research. This is the buyer’s dogfood report and the basis for the paid-v1 promise, refund triggers, and scope cuts.

> **Raw input note:** two founder asks were deliberately revised after product review. The raw brief asks for a paid alpha; the PRD ships a free alpha until the five gates pass. The raw brief asks for “four of six” as a feeling; the PRD uses a per-source floor of three (two for 20–29 minutes), with mean 4/6 as a portfolio target. Final decisions are in [PRD.md](PRD.md), not in this raw brief.

---

## 1. My week

I run VibeCut and ship one long video plus four shorts a week. This is my dogfood report.

Monday: 94-minute podcast recorded Sunday. Edit long-form in Resolve, publish, open VibeCut. Analysis takes 20 minutes. Auto Select gives five stories; two are dead: one opens mid-thought, one ends before payoff. Forty minutes of sentence surgery. Then one render at a time, because Queue still speaks 15/30/60.

Tuesday: packaging. Three titles, description, hashtags, two covers, pin comment, per story. Build a packet, close the tab, lose it, rebuild. Cover preview is a poster, not the JPEG in the ZIP.

Wednesday: 32-minute client interview. Three vertical clips and one 4:5 by Thursday noon. Story render is 9:16 only, so I rebuild in Smart Cut.

Thursday: guest cancels. I dig a 2019 conference talk off an SSD, re-ingest, wait, cut stale references.

Friday: post eight things manually. Nine to eleven hours gone to work that is not writing, recording, or editing.

## 2. The breaking point

**90-minute podcast.** Trigger: Monday upload; four shorts due Tuesday. Workaround: Auto Select five, sentence edits, Smart Cut for the missing story, four renders. Cost: 3h40m, 2h10m after analysis. Failure: story three opens on “And that’s why...” and ends before the answer; Caption Studio asks 15/30/60 for a 47-second story; packet disappears from the UI on tab close. Emotional: I post three and feel like a clip farm.

**30-minute interview.** Trigger: client wants three clips and two revisions by Wednesday. Workaround: manual Smart Cut, captions, 9:16 render, 4:5 rebuild, email links. Cost: 2h45m plus 1h20m revisions. Failure: client approves the old link after I re-render; two links, two cuts, no version label; packet cover differs from preview. Emotional: I look amateur with their footage.

**Repost job.** Trigger: guest cancels Thursday; a client wants a 2022 webinar reused. Workaround: find master, re-ingest, re-analyze, re-cut, update stale references, rebuild captions because old SRT no longer aligns. Cost: 3h15m per source. Failure: repeat a take already posted; burned-in captions force a bad crop; wrong aspect exports twice. Emotional: attic cleaning, not creating. I postpone, then post nothing.

## 3. What I actually need

Ranked. Cut, packaging, repost.

### Cut

1. One 20–120-minute source in, 3–6 stories I would post out, no scrubbing.
2. Hook, payoff, evidence visible; reject in 30 seconds.
3. Delete or reorder spoken sentences; duration and captions update instantly.
4. One caption track follows the story through preview, burn, SRT, packet; no 15/30/60 remap.
5. Render at story length in 9:16 and 4:5 without redoing edits.

### Packaging

6. One folder: MP4, SRT, three titles, 125-character description, hashtags, pin comment, two exact covers.
7. Close app; tomorrow, download the same packet.
8. Copy the post as ordered text blocks.
9. Know before posting if captions are dense, contrast bad, audio off, a claim dangles, or payoff truncates; jump to fix.

### Repost

10. Reopen a prior source or story, change aspect and title, export without re-analysis.
11. See what I already posted, so I do not repeat the same take.
12. Turn an old talk or client footage into a usable set in minutes, context intact.

## 4. What makes me switch and pay

Trigger: a week with two long sources and one client deadline, when the choice is sleep or clips. I switch when the 94-minute podcast yields four postable stories before midnight, captions and copy attached, and I never open Resolve for a vertical.

Price: $149 one-time paid alpha seat, 30-day refund; $249 when it earns v1. Not $29/month. I pay for local custody and no meter, not more clips.

Proof: clean Mac, no Terminal, 90-minute file to four stories and a packet, reboot, re-download; edit, retry, kill, reopen, and burn, SRT, packet, hashes match; 20 real sources with keeper count and repair minutes vs OpusClip; a named human on support.

I refund on: fewer than three of six stories I would post; captions drift after edit; packet or render disappears; mandatory account, cloud, telemetry, watermark, meter, or auto-renewal; Terminal install; crash loses 40 minutes; support calls lineage a known limitation; upgrade breaks old jobs.

## 5. Red lines

Never: accounts, cloud sync, team seats; publishing, scheduling, OAuth, platform APIs; analytics, virality scores, trends, best-time; credits, cloud render, watermark, telemetry; avatars, voice cloning, stock B-roll; auto-post, auto-resume, invented facts; silent retargeting, overwritten approved artifacts, unreadable AI scores.

I do not want OpusClip’s credit meter and virality number, Submagic’s caps and add-ons, Klap’s clip-count plan, Descript’s per-seat NLE, VidIQ’s trend advice, or Restream’s live-first bundle.

## 6. Ten product requirements for paid v1

I accept the ALPHA ONLY gate. These are my bar for calling it v1.

1. **Signed Mac app, no Terminal.** Acceptance: a clean Mac with no developer tools installs, imports a 90-minute source, renders one story, exports a packet, reboots, and keeps its data.
2. **Stories I can judge.** Acceptance: 3–6 non-overlapping 20–75 second stories with visible hook, payoff, and evidence; four of six pass blind “would post” review with ten minutes or less repair.
3. **Sentence-level edit.** Acceptance: include, exclude, or reorder, save, re-render; duration and cues update with no orphan clip.
4. **One caption lineage.** Acceptance: preview, burn, SRT, and packet share one story cue track and hash-match after edit, retry, and reload.
5. **Story render, 9:16 and 4:5.** Acceptance: 4:5 after 9:16 preserves story, cues, and copy, creates a separate immutable artifact, and never overwrites the first.
6. **Packet I can find tomorrow.** Acceptance: MP4, SRT, three titles, description, hashtags, pin, two exact covers, and a ZIP that re-downloads byte-identically by packet_id after relaunch.
7. **Story queue with recovery.** Acceptance: ten items run sequentially; kill at three, reopen, one-click resume, exactly one output per item, no duplicate, no auto-run.
8. **Preflight routes to fix.** Acceptance: each finding names story, cue, or artifact, carries severity, and opens the exact editor in one click; advisory checks never silently block export.
9. **Immutable artifacts, pinned shares.** Acceptance: re-render never changes what an existing review link plays; an expired or revoked link errors clearly, never falls back to newest.
10. **Local honesty.** Acceptance: no account or network for cut, caption, render, or packet; a 245 GB volume with 10.4 GB free renders a 30-second final; diagnostics bundle and rollback build exist.

## 7. Five things not to build before paid v1

1. Hook/cover matrix, 3x3 variants.
2. Selection v2, prompt exclusions, LLM re-ranking.
3. Review comments, approvals, seats.
4. Retention ledger, analytics.
5. Publishing, scheduling, platform APIs.

Also not: Windows, mobile, cloud.

## 8. Metrics that would make me trust the product

- Publishable stories per source: blind-rated, after repair, at least four of six and no worse than 0.5 behind OpusClip.
- Repair minutes per accepted story: median 10 or less, p90 20 or less.
- Time to first approved story: p50 30 minutes or less from import.
- Lineage: 100% match for burn, SRT, packet captions, cover times, and hashes after edit, retry, reboot.
- Packet recovery: 100% re-download, same ID and bytes next day.
- Crash recovery: 100% of interrupted ten-item queues resume with one output per item.
- Caption rework: two cue edits or fewer per accepted story; zero timing drift after edits.
- Refunds: under 5% in 30 days; zero for vanished packets or wrong cuts.
- Support: first human response under one business day; no “known limitation” on lineage.
- Disk honesty: zero valid renders blocked at 10.4 GB free.

## 9. Founder quote

> “I do not need more clips. I need the four I will actually post, with the captions and copy already right, from my own machine, tomorrow morning.”

## 10. Open questions for the senior product lead

1. Alpha seat or free alpha until gates pass? If sold, what does the buyer get, and what is the refund promise?
2. Is paid v1 “four postable stories from one source” or “one perfect packet”? Give me one sentence I can repeat.
3. Is 4:5 in paid v1? Client work dies without it.
4. Who judges “publishable” in the 20-source test, and can I see evidence before paying?
5. Where does repost live, and what happens to legacy 15/30/60 jobs and links?
6. What is the support promise, and who answers when a client deadline hits a defect?
7. If I stop renewing, can I still open and re-download old packets? Do I own the archive?
8. What is the client-footage deletion policy, and is automatic retention optional?
9. Will there be a public known-issues list and rollback build?

---

*Founder brief source for PRD 1.1. Product decisions are in [PRD.md](PRD.md); current state, open items, and contracts are in [ROADMAP.md](ROADMAP.md).*
