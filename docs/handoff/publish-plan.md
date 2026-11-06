# Publish: current state and feature plan

Date: 2026-11-05
Status: wording fixed and full-video path made visible; features planned
Related: `ROADMAP.md` §2, `docs/handoff/lane-split-decisions.md`

## 1. What ships now

Finish has three stages: Review, Render, Publish.

Publish currently offers:

- **Publish kit** for one ready artifact: three titles, description, hashtags,
  pinned comment, cover times, captions and covers.
- **Review link** for one exact artifact and a shape.
- **Versions** hidden under the advanced section: older renders and edits.
- **Download all** for the current shape when two or more stories are ready.

The server routes:

```text
POST /api/jobs/{job_id}/artifacts/{artifact_id}/packet
GET  /api/jobs/{job_id}/packets
POST /api/shares
GET  /api/shares?job_id=
```

## 2. Fixed in this pass

- "Cut" is gone from Publish copy. The unit is a **story**.
- The publish-kit picker and the review-link picker label every artifact by its
  story. A full-video render reads **Full video**, not "Cut".
- Every ready artifact is listed, including a full-video render. Previously a
  full-video row could fall back to the generic "Cut" label.
- Publish is two columns: the kit and review link on the left, the finished
  list on the right. Each finished row has **Open file** and **Download**.
- The Review stage now plays a draft preview of the current Edit, with a
  Quick blur check and a compact leftover-text list; the separate
  "Review notes" card is gone.

## 3. Full video and stories

A job can hold:

- one **full video** story, `st_full_video`, or
- a set of moment stories, or
- both.

Publish must treat the full video as a first-class story:

- it appears in the publish-kit picker and the review-link picker;
- its packet carries the full duration and the same copy fields;
- its cover times are measured on the full video;
- its review link pins the exact full-video artifact.

Open issue: the packet builder currently derives titles and covers from the
selected story's clips. For a full-video artifact, use the full-video story and
its duration, not the first moment.

## 4. Planned features

### Phase 1 — Publish list

- A single "Ready to publish" list across the job.
- One row per ready artifact: story or Full video, shape, quality, version,
  size, date, duration.
- Status: draft render, final render, stale Edit, missing captions.
- Actions: build kit, make link, download, open in Finish.
- Empty state explains what to render.

### Phase 2 — Packet builder

- One packet per artifact, including full video.
- Copy fields: three titles, description, hashtags, pinned comment.
- Covers: three times, each with a frame thumbnail and "use current frame".
- Captions: include SRT and VTT when present; show missing captions as a hint.
- Packet manifest carries `edit.json`, `audio.json`, `music.json`, layer assets,
  `story_ref`, `artifact_id`, `edit_hash`.
- Full-video packet carries `full_video: true` and the full duration.

### Phase 3 — Review link

- One exact artifact, never "latest".
- Expiry and label.
- Show the pinned artifact, shape, version and `Edit vN`.
- Copyable URL.
- A local list of open links with created date, expiry and artifact.
- Approval state is manual: "Shared", "Approved", "Needs changes". No accounts.

### Phase 4 — Delivery

- Download all ready stories for one shape.
- Download one packet as ZIP; download the MP4 alone.
- Download captions separately.
- Copy title, description and hashtags to the clipboard.
- A local delivery log: built, downloaded, link created. No network calls.

### Phase 5 — Platform presets

- Labels only: TikTok, Reels, Shorts, feed.
- Each preset states shape, duration guidance and caption safe area.
- No OAuth, no direct posting, no scheduling, no analytics.

## 5. Data and APIs

Proposed additions:

```text
GET  /api/jobs/{job_id}/publish                 ready artifacts + packets + links
POST /api/jobs/{job_id}/artifacts/{id}/packet   exists; add full_video flag
POST /api/shares                                exists; pin artifact id
GET  /api/jobs/{job_id}/publish/log             local delivery log
```

Local log record:

```json
{
  "at": 1793875529.0,
  "kind": "packet | link | download",
  "artifact_id": "art_...",
  "story_id": "st_full_video",
  "shape": "9:16",
  "version": 2,
  "label": "Client review"
}
```

No accounts, no remote delivery, no analytics.

## 6. Risks

- A packet built from a stale Edit must fail closed, as render does.
- A full-video packet can be large; keep the same ZIP rules and size hints.
- Cover times on a full video can exceed the story; clamp to duration.
- Two artifacts can share a title. Always show shape and version.
- Review links must pin the artifact id, not the story pointer.

## 7. Acceptance

- Render a full video and one moment. Both appear in Publish by name.
- Build a packet for each. Both carry the correct duration, covers and captions.
- Make a review link for the full video. It opens the exact full-video render.
- No user-facing copy says "cut" in Publish.
- Empty, stale and missing-caption states each say what to do next.
