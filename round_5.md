# VibeCut — Round 5: R1 trim and app review

**Date:** 2026-10-28  
**Baseline:** `main` at `2459073`; R1 merged, tag `refactor-1-done`  
**Suite:** 1415 passed, 7 skipped  
**Method:** Old sub-agents re-used — senior dev/QC, senior product/QA, solo creator, client editor, and the founder. Read-only. No code changes during the review.  
**Scope:** Review the merged app; run QC/QA/testing/unit checks; examine the four trim limitations; recommend fixes and new features; give a final founder verdict.

---

## Executive verdict

**ALPHA ONLY / HOLD.**

The test suite is healthy. The trim product behavior is not paid-safe.

The core finding is not “trim handles are missing.” It is:

> A trim currently changes the story range but does not atomically change the Edit, captions, layer times, preview, and render identity. The user can approve a different film than the one the screen shows.

The four reported limitations are real. Two are P0 for paid work:

1. **Start trim does not move layers** — text, graphics, and captions can sit over different words.
2. **Captions are not rebuilt after trim** — burn, SRT, preview, and packet can carry stale cues.

The other two are P1:

3. **Trim only shortens** — the only widen path is Stories ±, which creates a fresh Edit and breaks the current binding.
4. **Edit screen shows the old length until reopen** — header, preview, and scrubber disagree with the timeline.

The founder’s verdict:

> “A trim that silently changes the film is not a trim; it is a re-edit.”

---

## Test and QC evidence

### Full suite

```text
/opt/homebrew/bin/python3.11 -m pytest -q -p no:cacheprovider
1415 passed, 7 skipped, 5 warnings
```

### Targeted

```text
tests/test_clipset_trim.py        5 passed
tests/test_studio_js.py          17 passed
trim + Studio + picks            31 passed
```

### Static

```text
compileall                          exit 0
node --check (25 JS files)          pass
git diff --check                    clean
```

### Gaps in evidence

- No mounted pointer-drag test. Pure helpers and TestClient paths are covered; the browser drag/focus path is not.
- No live browser run on the founder’s videos in this review.
- The founder manual tables exist in `docs/handoff/r1-t1.md` through `r1-t4.md` and are unrun.
- GitHub CI had not run on the merged main at the time of the R1 review.

---

## What works

- Sentence-bound snapping: no mid-sentence cuts.
- Pointer and keyboard trim handles; slider roles and Home/End.
- A new Edit version is created after trim.
- Layers are kept and flagged; they are not silently deleted.
- The trim state persists after reopening.
- Rights policy, performance, and the wider suite are healthy.
- A start/end trim covers the four limitation cases in the manual checklist.
- Performance: 26 s synthetic 1440p AV1 final render was 15.29 s wall, **0.59× story length**; Studio read cache budgeted **38 requests** for a five-minute every-step-twice session.

---

## The four limitations

### 1. Trim only shortens

**Severity:** P1 before paid release; acceptable alpha limitation.

**Root cause**

`trimStoryRange` slices only the current story’s sentence spans. The end handle’s maximum is `spans.length - 1`. Stories ± can widen a range, but it is a separate path and does not rebind the current Edit.

**User impact**

The user cannot restore a removed sentence from the timeline. They have to leave Edit, use Stories ±, and accept a new Edit. That breaks the obvious meaning of “trim” and triggers the stale-Edit problem below.

**Required behavior**

- Load the full source sentence pool, not only the selected story.
- Allow both directions at sentence bounds.
- Preview overlap/neighbour collisions before commit.
- Use the same trim transaction for timeline handles and Stories ±.

### 2. Start trim does not move layers

**Severity:** **P0 blocker for paid work.**

**Root cause**

Layer and caption times are stored in output time and preserved unchanged. The outside-layer check only tests `0..newDuration`. A layer removed from the start of the story is not negative in that check, so it is neither shifted nor flagged.

**User impact**

A hook, lower third, CTA, or caption that was over the old first sentence now plays over the new first sentence. That can be a different claim, name, or meaning. The screen may show no warning because only the removed tail is flagged.

**Required behavior**

- Rebase every timed layer and caption by the start delta.
- Clamp at zero.
- Clip or remove fully outside layers, with confirmation.
- Flag ambiguous or pinned layers.
- Distinguish story-pinned hooks/CTAs from source-anchored callouts.
- Never keep an out-of-range layer silently.

### 3. Captions are not rebuilt after trim

**Severity:** **P0 blocker for paid work.**

**Root cause**

The trim rebind copies the existing `captions` object. `default_story_caption_track` returns the cached track without checking the new clip hash. The render accepts the old track.

**User impact**

- Start trim: captions run late by the trimmed amount.
- End trim: cues beyond the new end disappear.
- Burn, SRT, preview, packet, and review output can disagree with the new story.
- Names and claims can appear at the wrong time.

This breaks the one-caption-lineage promise.

**Required behavior**

- On clip-hash change, reject the cached track.
- Rebuild or reflow cues from the new trimmed sentence spans.
- Preserve manual text/timing where anchored to the same content.
- Create a new caption-track version in the same transaction.
- If rebuild fails, fail the trim or mark captions stale and block render/export.
- Test burned cues, SRT, packet cues, and cue hashes, not only track IDs.

### 4. Edit screen shows the old length until reopen

**Severity:** P1 before paid; acceptable alpha limitation only with a visible warning.

**Root cause**

The timeline keeps a local `trimOverride` with the new duration. The parent Edit screen’s `state.duration`, header, preview, scrubber, and playhead are not updated. The timeline and the rest of the screen disagree.

**User impact**

The header says the old length while the timeline says the new one. The preview and scrubber still use the old cut. A later layer save can hit 409. The user may approve a cut they are not seeing.

**Required behavior**

- One duration source.
- Return `story`, `revision`, new duration, Edit, caption track, and hashes from the trim transaction.
- Parent Edit screen updates header, preview, scrubber, playhead, and toy timeline immediately.
- Reload the proxy by new Edit ID or show “rebuilding preview.”
- Disable Finish until preview and Edit hashes agree.

---

## Additional systemic defects

### P1 — Stories ± changes the clip set but not the Edit

`static/studio/stories.js` updates the story range through the clip-set PATCH. The current Edit pointer survives with a stale clip hash. Later PATCHes return 409.

**Fix:** Stories ± and timeline trim must use the same server trim transaction and return the new Edit.

### P1 — Trim is non-atomic

The clip-set PATCH commits before `createEdit`. If `createEdit` fails, the story is trimmed but the Edit is stale. Finish can silently fall back to the plan path and render a different film without graphics, captions, or audio layers.

**Fix:** one server transaction for range + Edit + captions + pointers. If it fails, nothing commits. Finish must fail closed on a stale/missing Edit.

### P1 — Undo is broken after trim

Generic Edit undo restores layers onto a story range that no longer exists. It does not restore bounds or captions. There is no trim-specific undo.

**Fix:** undo creates a new version restoring story range, layers, captions, duration, and hashes. Old artifacts and review links remain immutable.

### P1 — 9:16 trim leaves 4:5 stale

Trimming one aspect updates the story range but does not rebind the other aspect. The other Edit fails on open or silently uses the old story hash.

**Fix:** rebind every live aspect in the transaction or mark the other aspect stale with a clear badge and repair path.

### P2 — No revision/ETag

Two tabs can trim the same story and last writer wins. The clip-set PATCH has no expected revision.

**Fix:** accept `expected_revision`; return 409 with the current story/revision; no silent overwrite.

### QA gap — no mounted drag test

No browser-level test exercises the real drag handle, keyboard focus, drop, and subsequent caption/layer state.

**Fix:** Playwright pointer drag on start and end; assert duration, layer positions, caption cues, and 409 recovery after drop.

---

## Role reports

### Senior dev / QC

**Verdict:** ALPHA ONLY. No code P0; P1 trim-to-Edit lineage can silently produce a different film.

**Findings**

- Stories ± creates a stale Edit and later 409.
- Trim is non-atomic; a failed rebind can make Finish render the plan without layers.
- Captions keep old cues because the cached track is reused without a clip-hash check.
- Start trim leaves layers at old output times; outside detection misses removed prefixes.
- Header/preview keep old duration.
- Trim is shrink-only.
- No revision/ETag; two writers can overwrite.
- Missing tests: start trim + captions, undo-after-trim, multi-aspect, Stories ± rebind, 409 recovery, mounted drag.

**Technical requests**

1. Atomic story-range transaction.
2. `reflowRange` mapping layers/captions by start delta.
3. Clip-set revision tokens and explicit stale-Edit state.
4. `rangeChanged` callback and caption clip-hash validation at render.
5. Browser-level trim tests.
6. Trim receipt and stale badges.

### Senior product / QA

**Verdict:** HOLD. Trim is a core editor primitive, not a secondary feature.

**P0**

- Start trim does not move layers.
- Captions are not rebuilt.

**P1**

- Old duration until reopen.
- Shrink-only.
- No true trim undo.
- No live drag evidence.

**Desired behavior**

1. Both directions at sentence bounds.
2. Ripple layers by start delta.
3. Rebuild captions in the same transaction.
4. Optimistic duration and preview.
5. Trim undo.
6. New Edit/render version; old artifacts and links immutable.

**What not to promise**

“Captions and layers follow automatically,” “trim is undoable,” “lengthen from timeline,” “trim is non-destructive,” “frame-accurate,” “no re-render,” “multi-range/split/merge/word-level/auto-filler now,” or “Classic parity.”

### Solo creator

**Verdict:** no client or published work.

**Ranking**

1. Captions not rebuilt.
2. Start trim does not move layers.
3. Old length until reopen.
4. Shrink-only.

**Quote:** “A stale caption is worse than no trim.”

**Requests**

- Atomic trim transaction.
- Content-anchored layers.
- Caption reflow preserving manual name fixes.
- One duration source.
- Trim undo.
- Duration delta and stale badges.
- Sentence-anchored hooks/CTAs.
- Ripple-delete a middle sentence.
- Caption drift check.
- Approved-version lock.

### Client editor

**Verdict:** reject for paid jobs with burned captions or timed overlays.

**Safe path:** end-only trim on a clean, uncaptioned master, after reopening and checking duration/picture. A start trim on a captioned/layered cut is a no.

**Risks**

1. Captions wrong.
2. Hook/lower third over wrong sentence.
3. Stale preview.
4. Broken undo.
5. 9:16 trim invalidates 4:5.

**Wants**

- Layer ripple with per-layer “pin to source.”
- Caption rebuild with same style and new track ID.
- One duration source.
- Versioned story range.
- A/B compare.
- Approved-version lock.
- Trim receipt.
- Client-shareable proof of what moved/removed.

**Willingness:** $30/month or $99 one-time for safe trim; abandon if wrong captions/undo persist.

### Founder

**Verdict:** HOLD; alpha only.

**Minimum paid contract:** one transaction for story + Edit + captions + render identity. No half state. Finish fails closed on stale Edit.

**Fix order**

P0: atomic commit, start ripple, caption rebuild, revisioned range + undo.  
P1: one duration source, both-direction trim, 4:5 rebind, mounted drag.  
P2: trim receipt, A/B, approved lock.

**Greenlight now:** both-direction, ripple, caption rebuild, optimistic preview, undo, revision/ETag, trim receipt.  
**Defer:** A/B, approved lock, transcript-range.  
**Reject now:** split/merge, multi-range, word-level, silence/beat, auto-filler, auto-delete, cloud/multi-user.

---

## Minimum atomic trim contract

```text
POST /api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/trim
  expected_revision
  start_sentence
  end_sentence
```

Under one job lock:

1. Validate revision and current story/Edit/caption hashes.
2. Return 409 with current state on mismatch; zero writes.
3. Commit story range + new Edit for every live aspect + rebuilt caption track + pointers atomically.
4. Rebase layer/caption times by the start delta; clip/remove outside layers; flag ambiguous.
5. Rebuild captions from trimmed sentence spans; preserve manual fixes by content anchor.
6. Return one duration, new hashes, invalidated artifacts, and an undo token.
7. Finish fails closed if Edit is stale/missing; never plan fallback.
8. Undo is a new version; old artifacts/review links remain immutable.
9. Write a trim receipt: old/new range, moved/removed layers, caption changes.

---

## Fix order

### P0 before any paid job

1. Atomic trim transaction.
2. Start-trim layer ripple.
3. Caption rebuild/reflow.
4. Revisioned ranges + true trim undo.

### P1 before paid, acceptable alpha only

- One duration source in header/preview/player.
- Both-direction sentence trim.
- 4:5 rebind or explicit stale badge.
- Stories ± rebind.
- Mounted drag test.
- Finish fail-closed on stale Edit.
- Trim receipt.

### P2

- A/B compare.
- Approved-version lock.
- Transcript-range trim.
- Word-boundary trim.

---

## New features requested by the panel

### Greenlight now — correctness, not extras

- Both-direction sentence trim.
- Layer ripple.
- Caption rebuild.
- Optimistic preview/duration.
- Trim undo.
- Range revision/ETag.
- Trim receipt.

### Defer

- A/B compare.
- Approved-version lock.
- Transcript-range trim.
- Word-boundary trim.

### Reject now

- Split/merge stories.
- Multi-range trim.
- Frame-level freeform trim.
- Silence/beat trim.
- Automatic filler removal.
- Auto-deleting outside layers.
- Cloud/multi-user trim.

Creators would value split/merge, multi-range, word-level, and silence/beat trim later — after the atomic contract is proven.

---

## What to promise today

**Can say**

- Alpha users can adjust a story at sentence boundaries.
- An end-only trim on a clean, uncaptioned story is the safe path.
- Old artifacts and review links remain immutable.
- Layers outside the end are flagged, not deleted.

**Cannot say**

- Start trim with layers is safe.
- Captions follow automatically.
- Trim is undoable.
- Trim works both directions.
- Multi-aspect trim is safe.
- A trimmed story is ready for a paid client.
- Trim is frame-accurate or word-accurate.
- No re-render is needed.

---

## Tests required before the next paid release

1. Start trim earlier and later: layers shift, outside layers flagged, duration/preview correct.
2. Caption rebuild: burn, SRT, packet cues match; cached track rejected on clip-hash change; manual fixes survive.
3. Atomic failure: force createEdit/caption failure; no story, pointer, or artifact changes.
4. 409/concurrency: stale revision, Stories ± then Edit save, two trims; no silent plan render.
5. Multi-aspect: 9:16 rebind/4:5 stale badge; old artifact immutable.
6. Undo after trim: range, layers, captions restore as a new version.
7. Finish with stale/missing Edit: fail closed with repair path.
8. Playwright mounted drag: pointer start/end, focus, caption/layer result after drop.

---

## Founder line

> “A trim that silently changes the film is not a trim; it is a re-edit.”

**Decision:** do not ship trim as complete. Fix the atomic contract first. New trim features wait.

---

## Appendix — evidence map

| Area | Files / evidence |
|---|---|
| Trim range | `static/studio/stories.js:123-143`; `static/studio/edit/timeline.js:330-355` |
| Layer timing | `static/studio/edit/timeline.js:400-416,521-526`; `static/studio/stories.js:146-155` |
| Caption reuse | `routes_edits.py:427-430`; `app.py:6286-6296,7151-7155` |
| Duration propagation | `static/studio/edit/timeline.js:400-413,597-635`; `static/studio/edit/index.js:216-221,739-745` |
| Stories ± stale Edit | `static/studio/stories.js:344-361`; `static/studio/edit/index.js:632-661`; `routes_edits.py:465-468` |
| Non-atomic trim | `static/studio/edit/timeline.js:382-398`; `app.py:6262-6282` |
| Revision gap | `app.py:6170-6196` |
| Tests | `tests/test_clipset_trim.py`; `tests/test_studio_js.py`; `tests/test_clipset_picks.py` |
| Handoffs | `docs/handoff/r1-review.md`; `r1-t1.md`; `r1-t2.md`; `r1-t3.md`; `r1-t4.md` |

**No code changes were made during this review.**
