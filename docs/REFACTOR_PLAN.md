# Refactor round 1 (R1)

**Base:** tag `refactor-1-base` on `main` (`2564ac8` plus this plan).

**Baseline tests:** 1331 passed, 7 skipped.

**Run as:** one OpenCode wave with 4 tracks. The rules are the same as in WORKPLAN §2–§5: own worktree, owned files only, no merge/push/delete, and a handoff in `docs/handoff/r1-tK.md` ending with "## Founder manual test". Claude Code reviews, fixes and merges T1→T4.

**Goals:**
- Make the rights lock a setting with one policy source.
- Finish the four partial QA round 1 items (#13, #14, #18, #21).

## 1. The rights lock (founder decision, 2026-10-28)

Rights checks are spread over many places today:
- `app.import_rights`
- `routes_edits._clean_rights_attested` / `_require_clean_rights`
- `detect.cleanup_block_reason`
- `cleanup.py:327`
- `routes_check.py`
- `preflight.py`
- `music.py`
- Studio's `import.js`, `check.js` and the Clean layer

R1 moves them into one module and adds a Setup switch.

### Setting

The setting lives in `settings.json` as `rights.lock` (bool) and defaults to `true`. It is shown in Studio at **Setup → Rights → Rights lock**.

| | Lock **on** (default) | Lock **off** |
|---|---|---|
| Import | Needs "I own this footage or have the rights to it" ticked (today's behaviour) | No box. Import starts straight away. |
| Check, Stories, Edit, captions, voice, dub, music, Finish | Open after Import (today) | Open |
| Clean on old subtitles, captions and plain burned-in text | Needs the rights tick | Open, no tick |
| Clean on a `handle_or_logo` | Needs the rights tick | Needs the per-video "this handle or logo is mine" tick |
| Clean on a `watermark` | Always refused | Always refused |
| Clean on `screen_text` (app UI) | Never cleaned | Never cleaned |

The last three rows stay fixed whatever the setting is:
- Watermarks and other creators' handles or logos are attribution marks, so VibeCut doesn't strip them.
- Screen text is a quality rule, not a rights rule.

### Contract (frozen for R1)

- **New module `rights.py`**, the only place policy is decided:
  - `lock_enabled(settings=None) -> bool`
  - `job_attested(job) -> bool`, which keeps today's legacy-job rule (a job with no `rights` record counts as attested)
  - `may_import(attested: bool|None) -> bool`
  - `clean_block_reason(kind, *, job, settings=None) -> str|None`, which returns `watermark`, `screen_text`, `attestation_required` or `rights_not_attested`, or None
  - `policy(job=None) -> {lock, attested, needs_import_tick, clean: {kind: reason|None}}`
- **`detect.cleanup_block_reason`** stays as a thin wrapper, for older callers and tests.
- **Server routes:**
  - `GET /api/rights/policy` returns `policy()` with no job.
  - `GET /api/jobs/{id}` adds `rights_policy`, which is `policy(job)`.
  - `POST /api/settings` accepts `rights: {lock: bool}`.
  - With the lock **on**, the import routes return **409** "Confirm you own this footage or have the rights to it." when `rights` is not true. This fixes the API/Studio mismatch: the API used to import without the tick.
  - With the lock **off**, `rights` is optional, and it is still stored when sent.
- **Every server gate reads `rights.py`:** Import, the Check prefill, the Clean save in `routes_edits`, `cleanup/layers`, the residual check and preflight. A request body or browser storage never decides policy.
- **Turning the lock back on doesn't affect saved Edits.** Old Edits are not rewritten. The next save of a Clean layer is gated again.

## 2. Tracks

| Track | Build | Owns |
|---|---|---|
| **T1 Rights policy** | `rights.py` + the contract above. Rewire `app.py` import routes (rights lines only), `routes_edits.py` (Clean gate), `detect.py` (`cleanup_block_reason`/`clean_prefill` delegate), `cleanup.py`, `routes_check.py`, `routes_cleanup.py`, `preflight.py`, `music.py` rights reads, `settings_store.py` (`rights.lock` default + normalise). Tests: a matrix of lock on/off × kind × attested. Import 409 with the lock on. Legacy jobs. Settings round-trip. | the files listed, `tests/test_rights_policy.py`, updates to `tests/test_import_rights.py`, `tests/test_detect.py`, `tests/test_cleanup.py` |
| **T2 Studio rights UI** | **Setup → Rights**: a "Rights lock" switch with this help text: "On: people must confirm they own the footage before importing or cleaning. Off: anyone can import, caption, voice and clean old captions. Watermarks are never removed, and handles or logos always need a 'this is mine' tick." Import, Check and the Clean layer read `GET /api/rights/policy` / `job.rights_policy` and show the tick only when it is needed. Drop the localStorage attestation as a policy source; it may remain only as a remembered checkbox state. Clean chips show the server reason. | `static/studio/setup.js`, `import.js`, `check.js`, `edit/layers/clean.js`, `studio.css` (rights styles only) |
| **T3 Story picks + trim** | **#13:** prefer ending on a closing sentence (terminal punctuation, falling to a pause ≥ 350 ms). Spread picks across the source: penalise picks whose centres fall within 15% of the source length of a pick already chosen, unless fewer candidates remain. **#14:** trim from the Edit timeline. Drag the story's start and end handles, snapping to sentence bounds, saved through the existing clip-set `stories` PATCH. The Edit follows the new bounds and layers outside them are flagged, not deleted. | `clipset.py`, `static/studio/edit/timeline.js`, `static/studio/stories.js` (shared trim helper only), `tests/test_clipset*.py` |
| **T4 Performance** | **#18:** profile a Final render of a 26 s story from a 1440p AV1 source (seen at 2 min 50 s). Check the decode path: software `libdav1d` vs VideoToolbox, seek-before-input, and scale before the filter graph. Target ≤ 2× story length on an M1. Write the profile to `docs/handoff/r1-t4.md`. **#21:** a shared per-job read cache in Studio for job, clip-set, Check report and edits list. It is invalidated on every write through `api.js` and on a job `updated_at` change from the shell watcher. Target ≤ 40 requests in a 5-minute session that opens every step twice. | `render.py`, `compose_render.py` (decode/scale only), `static/studio/api.js`, `static/studio/shell.js`, `tests/test_render*.py` |

**Shared-file rules:**
- T2 calls only `api.js` functions that already exist, plus `request()`. T4 owns `api.js` changes.
- T3 and T4 don't touch rights code.
- `app.py` is open only to T1 (rights lines and the new route).

## 3. Exit

- All tests pass. New tests cover every row of the §1 table.
- `node --check` passes. `compileall` passes.
- Each handoff has a founder manual test table, with videos A and B where relevant.
- Claude Code merges, re-runs the suite, and tags `refactor-1-done`.
