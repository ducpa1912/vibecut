# Refactor round 2 (R2): atomic trim

**Base:** tag `refactor-2-base` on `main`.

**Baseline tests:** 1415 passed, 7 skipped.

**Input:** `round_5.md` (the panel review of R1 trim).

**Verdict being fixed:** HOLD. A trim changes the story range without atomically changing the Edit, captions, layer times, preview and render identity.

**Run as:** one OpenCode wave with 4 tracks. Same rules as WORKPLAN §2–§5: own worktree, owned files only, no merge/push/delete, and a handoff in `docs/handoff/r2-tK.md` ending with "## Founder manual test". Claude Code reviews, fixes and merges T1→T4.

**Scope:**
- **In:** every panel item marked P0, P1, or Greenlight in `round_5.md`.
- **Deferred:** A/B compare, approved-version lock, transcript-range trim, word-boundary trim.
- **Rejected (not built):** split/merge, multi-range, frame-level freeform trim, silence/beat trim, auto filler removal, auto-deleting outside layers, cloud/multi-user.

## 1. Facts the plan relies on

- **Clip sets live inside `job.json`** (`job["clip_sets"]`). Edit pointers (`job["story_edits"]`) and caption pointers (`job["story_captions"]`) also live there. So one `app.update_job(job_id, mutate)` under `app.LOCK` is the single commit point.
- **Edit versions and caption tracks are immutable sidecars.** They are written before the commit. If the commit fails, the sidecars are orphans that nothing points to; they are never deleted and never visible.
- **An Edit's `story_ref.clip_hash` must equal `edits.clip_snapshot_hash(story.clips)`.** `routes_edits.patch_edit` already refuses a mismatch with 409.
- **The current gap:** `_story_edit_for_render` falls back to the plan path on a mismatch, so a stale Edit renders a different film. That fallback ends in R2.

## 2. Frozen contract

### 2.1 Story revision

- Every clip-set story carries `revision` (int). A missing value reads as `0`.
- Any change to a story's range bumps it by 1:
  - the trim, undo or rebind routes below;
  - `PATCH /clip-sets/{set_id}` story patches;
  - a re-pick that keeps the story id.
- `PATCH /clip-sets/{set_id}` story patches accept an optional `expected_revision`. On a mismatch it returns 409 with `code: "revision_mismatch"`.

### 2.2 Time mapping (the ripple rule)

**Mapping through the clips.** Layer and caption times are output time over the story's clips. A trim maps them through the clips, not by a guessed offset:
1. Output time maps to source time through the **old** clips.
2. Source time maps back to output time through the **new** clips.

**Results.** Moving the start earlier or later shifts every layer by the start delta, and the layer stays over the same words.

| Layer after mapping | Result | Receipt list |
|---|---|---|
| Inside the new range | Moved | `moved` |
| Partly outside | Clipped to the range | `clipped` |
| Fully outside | Kept, with `hidden: true` and its old times. The renderer skips hidden layers. Never deleted. | `outside` |

**Story-pinned layers.** A text or graphic layer may carry optional `anchor`:
- `"source"` is the default when the field is absent;
- `"story_start"` keeps the layer at its offset from time 0;
- `"story_end"` keeps it at its offset from the new end.

Pinned layers are listed in the receipt under `pinned`. A new Hook card is created with `anchor: "story_start"`.

**Schema rule.** `anchor` and `hidden` are optional in the Edit schema. An Edit without them hashes exactly as before.

### 2.3 Routes (T1 builds them; T3 and T4 code against them)

The routes share a prefix, written `<prefix>` below: `/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}`.

```text
GET  <prefix>/trim
  -> {revision, story:{id,start,end,dur,sentence_ids}, clip_hash,
      pool:[{id,start,end,text}],
      neighbours:{before:{id,end}|null, after:{id,start}|null},
      aspects:{"9:16":{edit_id,stale:bool}, "4:5":{...}},
      limits:{min_s:15, max_s:90}}

POST <prefix>/trim
  body {expected_revision:int, start_sentence:int, end_sentence:int, dry_run?:bool}
  -> 200 TrimResult
  -> 409 {detail:{code:"revision_mismatch"|"edit_changed"|"caption_rebuild_failed",
                  message, current:<GET payload>}}
  -> 422 {detail:{code:"range_invalid"|"overlaps_neighbour"|"too_short"|"too_long", message}}

POST <prefix>/trim/undo
  body {undo_token, expected_revision}
  -> 200 TrimResult  (or the 409/422 shapes above)

POST <prefix>/rebind
  body {expected_revision}
  -> 200 TrimResult  (current range; repairs every stale aspect Edit)
```

**Pool.** `pool` is the source sentences between the neighbouring stories' bounds, capped at 90 s each side of the current range. The range must be contiguous within it, so it can grow and shrink in both directions.

**`dry_run`.** The full TrimResult with zero writes. Studio uses it for the live preview: duration, collisions and the receipt before the drop.

**TrimResult:**

```text
{story, revision, duration, clip_hash,
 edits:{aspect: public_edit},
 captions:{track_id, clip_hash, cue_hash, rebuilt:bool},
 receipt:{id, at,
   old:{start_sentence,end_sentence,start,end,dur},
   new:{start_sentence,end_sentence,start,end,dur},
   layers:{moved:[id], clipped:[id], outside:[id], pinned:[id]},
   captions:{kept:int, moved:int, dropped:int, added:int, manual_kept:int}},
 undo_token,
 invalidated_artifacts:[artifact_id],
 stale_aspects:[]}
```

### 2.4 Transaction (all under `app.LOCK`, in this order)

1. Load the job. Check `expected_revision` against the story's revision. Check that every live-aspect Edit head is the pointer the caller saw (the `aspects` map). On any mismatch return 409 with the current GET payload and write nothing.
2. Build the new story range from the pool. Validate the length (15–90 s) and that it doesn't overlap a neighbour.
3. Rebuild the caption track for the new clips (T2's function in §2.5). If that fails, return 409 `caption_rebuild_failed` and write nothing.
4. For every aspect with a current Edit (live aspects):
   - build the next Edit version, with layers rippled per §2.2;
   - set the new `story_ref` (with the new `clip_hash`);
   - point captions at the new `track_id`.
5. Write the sidecars: the Edit versions, the caption track, and the receipt at `jobs/<id>/trims/<receipt_id>.json` (holding the full before state).
6. **The single commit:** one `update_job` that does all of these, or raises and changes nothing:
   - replaces the story in `clip_sets`;
   - bumps `revision`;
   - sets every Edit pointer and `story_captions[key]`.
7. Append the Edit history.
8. Return TrimResult. `invalidated_artifacts` lists the story's artifacts whose `edit_hash` is no longer current. Artifacts and review links are never modified.

### 2.5 Undo

- **What it restores:** the receipt's old range, each aspect's pre-trim Edit (via `edits.restored_edit`, as a new version) and the pre-trim caption track id. All of these are under the old `clip_hash`, so they are exact.
- **How it runs:** it uses the same §2.4 transaction, writes its own receipt, and returns a new `undo_token`, so redo is the undo of the undo.
- **Undo after a later trim:** it is allowed only while `expected_revision` matches the revision the receipt produced. Otherwise it returns 409.

### 2.6 Captions (T2 builds; T1 calls)

```python
caption_reflow.rebuild_for_story(job_id: str, job: dict, set_id: str,
                                 old_story: dict, new_story: dict,
                                 old_track_id: str | None) -> ReflowResult
# ReflowResult: track (caption_engine.CaptionTrack, NOT yet saved), counts
#   {kept, moved, dropped, added, manual_kept}, and save(job_dir) -> track_id
# raises caption_reflow.ReflowError on failure (T1 maps it to 409)
```

**Reflow rule.**
- Each old cue maps to source time through the old clips (§2.2), then:
  - inside the new range: kept with its own text. Hand-edited text (manual fixes) is never re-transcribed.
  - fully outside: dropped.
  - partly outside: clipped at the edge.
- Newly added source spans get cues from the transcript, using the old track's style and chunking.
- The new track's `clip_hash` equals the new story's clip hash.

## 3. Tracks

| Track | Build | Owns |
|---|---|---|
| **T1 Trim transaction** | §2.1–§2.5: `trim.py` (pure: pool, range validation, time mapping, ripple, receipt), `routes_trim.py` (GET, trim, undo and rebind, with the transaction). `revision` and `expected_revision` in `patch_clip_set`. Optional `anchor`/`hidden` in `edits.py` `normalize_graphics` (hash unchanged when absent). Hidden layers are skipped in `compose_render.compile_edit`. T1 codes against §2.6. Until T2 merges, `routes_trim` imports `caption_reflow` lazily, and tests monkeypatch it. | `trim.py`, `routes_trim.py`, `app.py` (`patch_clip_set` and the router include line only), `edits.py` (`anchor`/`hidden` only), `compose_render.py` (skip `hidden` only), `tests/test_trim*.py` |
| **T2 Captions + fail-closed render** | `caption_reflow.py` per §2.6. `default_story_caption_track` and `_edit_caption_track` reject a track whose `clip_hash` doesn't match the story (no silent reuse). `_story_edit_for_render`: when a pointer exists but the Edit is stale or unreadable, the story render, Finish queue and publish packet return **409** `{code:"edit_stale", message:"This story changed after its Edit was made. Open it in Edit and press Repair."}`. **No plan fallback.** The legacy plan path stays only where no pointer exists. `routes_edits._payload` adds `stale: bool`. Burned cues, SRT and packet cues all come from the one track. | `caption_reflow.py`, `app.py` (`default_story_caption_track`, `_edit_caption_track`, `_story_edit_for_render` and their call sites' error mapping only), `routes_edits.py` (`_payload` only), `packet.py` (stale check only), `tests/test_caption_reflow.py`, `tests/test_render_fail_closed.py` |
| **T3 Studio** | One duration source. The trim result updates the Edit screen state: header, preview, scrubber, playhead, timeline, and a proxy reload by the new edit id (show "Rebuilding preview…"). Finish is disabled until the preview and Edit hashes agree. Timeline handles: both directions over `pool`, a `dry_run` on drag for a live duration/collision readout, commit on drop, and a 409 that reloads and explains. Stories ± calls the same trim route and never PATCHes ranges directly. **Undo trim** button with the receipt panel ("Moved 3 layers · 1 hidden outside · captions: 12 kept, 2 added"). A stale-aspect badge with **Repair** (calls `rebind`). Finish shows `edit_stale` with a Repair link. A new Hook card gets `anchor:"story_start"`. Remove the `trimOverride`/localStorage job-id hacks: get the job id from ctx. | `static/studio/edit/index.js`, `edit/timeline.js`, `edit/preview.js`, `edit/layers/text.js` (Hook anchor only), `stories.js`, `finish.js`, `api.js` (trim helpers + cache invalidation), `studio.css` (trim styles only) |
| **T4 Acceptance + browser tests** | The round_5 "Tests required" list, as tests against §2. `tests/test_trim_acceptance.py`: start earlier and later with layer shift and hidden outside layers; captions (burn cues = SRT = packet, cached track rejected, manual fix survives); atomic failure (forced caption/Edit failure leaves no story, pointer or artifact change); 409 races (stale revision, Stories ± then Edit save, two trims); multi-aspect rebind; undo restores range, layers and captions; Finish fails closed on a stale Edit. A synthetic job fixture with transcript, clip set and two aspects. Browser: `tests/browser/trim_drag.spec.mjs` (Node Playwright 1.64, already on this Mac, chromium cached) plus `tests/test_browser_trim.py`, which starts uvicorn on a free port with a scratch `VIBECUT_DATA` dir and the fixture, runs the spec, then **always** stops the server. Drag the start and end handles; assert the header duration, layer bar positions, caption cue times and focus. Skip cleanly when node or Playwright is missing. Every test skips with `pytest.importorskip("routes_trim")` / `("caption_reflow")` on this branch, so the T4 suite stays green; they must pass after the merge. | `tests/test_trim_acceptance.py`, `tests/test_browser_trim.py`, `tests/browser/**`, `tests/fixtures/trim_job/**` |

**Shared-file rules:**
- `app.py`: T1 owns only `patch_clip_set` and the include line; T2 owns only the functions listed for it. Nobody else edits it.
- Studio JS: only T3 edits it.

## 4. Exit (Claude Code checks at merge)

- Every round_5 required test exists and passes on merged `main`, including the browser drag. The full suite is green.
- **The founder line holds.** After any trim or undo, these all agree:
  - the Studio header duration;
  - the preview;
  - the Edit hash;
  - the caption `clip_hash`;
  - the rendered artifact's `edit_hash`.

  A stale Edit never renders.
- Each handoff has a founder manual test table with videos A and B.
- Tag `refactor-2-done`.
