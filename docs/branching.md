# Branches and shipping

Four branches share one codebase. The lanes differ in **what they work on**, not
in which files exist. Any lane can merge into any other because every lane
ships through `main`.

| Branch | Role | Worktree |
|---|---|---|
| `main` | Archive: the union of every lane. Nobody works on it directly. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut` |
| `classic` | Beta launch focus: the Classic view (`/?classic=1`). | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic` |
| `studio` | Work in progress: the Studio view (Import → Check → Stories → Edit → Finish). | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio` |
| `voice-room` | Hidden, independent voice features: Voice Room page, voice clone, voice library, voice extraction. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room` |

## The one rule

**Every change on a lane ships with `scripts/ship.sh` from that lane's worktree.**
The script:

1. fetches GitHub,
2. merges any newer copy of the lane and then `main` into the lane (conflicts stop here, on the lane),
3. runs the test suite,
4. pushes the lane,
5. fast-forwards `main` to the lane and pushes `main`.

Because each ship first takes in `main`, every lane keeps absorbing the others.
Merging lane A into lane B is then never bigger than the last few ships.

Never commit on `main` directly, never force-push, and never delete a feature on a lane
to hide it. Deleting code on one lane deletes it on every lane at the next
ship. Hide features with switches (below).

## Who owns what

Each lane edits its own files freely. Shared files take small, additive changes
only. Ship them soon, so the other lanes pick them up on their next ship.

| Area | Owner lane | Files |
|---|---|---|
| Classic view | `classic` | `static/app.js`, `static/creator.js`, `static/style.css`, `static/creator.css`, the Classic half of `static/index.html` |
| Studio view | `studio` | `static/studio/**` except the voice files; `edits.py`, `routes_edits.py`, `compose_render.py`, `story_queue.py`, `routes_check.py`, `routes_library.py` |
| Voice features | `voice-room` | `voice_clone.py`, `voice_extract.py`, `routes_voice_clone.py`, `static/voices.html`, `static/studio/voiceroom.js`, `static/studio/voiceclone.js` |
| Shared core | any lane, additive | `app.py`, `pipeline.py`, `audio.py`, `tts.py`, `stt.py`, `music.py`, `render.py`, `settings_store.py`, `workflow_config.py`, `admin/`, tests of shared code |

## Hiding features: switches, not branches

What a build shows is set by configuration, so one codebase serves every lane.
Planned switches (see the plan below):

- `VIBECUT_EDITION=classic|studio|all`: which view opens by default, and whether
  the other view's link shows. The beta build uses `classic`.
- `VIBECUT_FEATURES=voice_room,...`: turns on hidden features. If `voice_room` is
  off, `/voices` and the voice clone routes answer 404 and no link to them shows.

## Working with OpenCode or another session

Give each session one lane worktree. Tell it to commit on that lane and finish
with `scripts/ship.sh`. Two sessions on the same lane at once will conflict; use
one session per lane.

## Upcoming work plan (revised)

### Why the method changed

The first plan let the lanes start in parallel straight away. Four things made that risky:

1. **Studio work would reach the beta untested.** Every ship merges `main` into the lane, so Studio and Voice Room changes flow into `classic`. Only the test suite guards it, and there are no Classic UI tests (only `test_studio_js.py` and `test_studio_layout.py`).
2. **Hot files every lane edits.** `static/index.html` was changed by Studio, Voice Room and Classic work. `app.py` holds 105 routes in about 9,150 lines. The R3 merge conflicts came from files like these.
3. **The voice files live inside Studio.** `voiceclone.js` sits in `static/studio/`, and Studio's Edit and Setup import it. Voice Room work would edit Studio's folder.
4. **No release point.** Beta testers would get whatever the `classic` tip is that day.

The fix: one short foundation phase first, done by one session. Then the three lanes run in parallel, each shipping small. The beta gets tagged releases, not the branch tip.

### Phase A: foundation (one session, on `classic`, before parallel work)

Each step ships on its own.

- **A1. Switches.**
  - `VIBECUT_EDITION=classic|studio|all` and `VIBECUT_FEATURES=voice_room,...`, read in `settings_store.py` and exposed in `/api/settings`.
  - The `index.html` boot picks the default view and hides the links to features that are off.
  - Voice routes and `/voices` answer 404 when `voice_room` is off.
  - Tests for each combination.
- **A2. Give Voice Room its own folder.**
  - Move `voiceroom.js`, `voiceclone.js` and `voices.html` styling into `static/voice/`, with its own small `api.js`.
  - Studio's Edit and Setup import from there.
  - A move only, no behaviour change. It is done once now, so the lanes never edit each other's folders.
- **A3. Cool the hot files.**
  - New routes go into lane modules: `routes_classic.py`, `routes_studio.py`, and the existing `routes_voice_clone.py`.
  - `app.py` only registers them, and takes small shared changes.
  - `static/index.html` belongs to `classic`. Other lanes touch only the A1 boot block.
  - Existing routes are not moved, to avoid a big-bang diff.
- **A4. Classic guard tests.**
  - An API-level Classic flow test with fakes: import → plan → render → history → export.
  - A smoke test that the Classic page loads its scripts.
  - `scripts/ship.sh` also runs `node --check` on every JS file.
  - From then on, a Studio or Voice Room ship cannot break Classic without failing the ship.
- **A5. Release tags.**
  - Add `scripts/release.sh`. It tags the current `classic` as `beta-YYYYMMDD-N` and pushes the tag.
  - The beta build is made from a tag, with `VIBECUT_EDITION=classic` and no extra features.
  - Tags are made only after the founder test passes.

**Done when** all five have shipped and every lane has taken them in, by running a ship with nothing new to ship.

### Phase B: three lanes in parallel (one session each, own worktree)

The rules for every lane:

- One item = one ship. Ship at least once a day of work; unshipped work is what makes merges hard.
- Shared core changes stay additive and tested from both views.
- Every user-visible item ends with a click-by-click founder test script in `docs/testing/`. The founder runs it, and Claude records the result.

**`classic` (beta focus)**

1. A founder test script covering every Classic flow:
   - import, plan, render, render-all, variants, hooks, mixer, history, export, batches
   - the Creator workspace: clip set, captions, preflight, packet, artifacts, queue
2. Fix what that pass and `round_6.md` find, highest severity first. Each fix gets a Classic guard test.
3. Beta setup inside Classic: first-run keys and voice engines.
4. When the founder pass is clean, `scripts/release.sh` makes the first beta tag.

**`studio` (work in progress)**

1. R3 open items (`docs/handoff/r3-review.md`):
   - a speech-only retry route
   - Check cancel, and Import cancel and ETA
   - Library "load more"
   - Open in Finish carries the story and shape
2. Render warnings in Finish (for example "Music bed skipped").
3. The Edit clone picker is shown only when `voice_room` is on.

**`voice-room` (hidden, independent)**

1. One page in `static/voice/`: the voice library (stock and cloned voices, preview, rename, delete), cloning, and the clean-clip finder.
2. Reached from Classic, with the Classic look, when `voice_room` is on.
3. Open from the review:
   - a live OpenRouter check of a cloned voice (one 10 s request, with the founder's OK)
   - a Cancel button for voice tasks
   - a browser test of the clip picker

### Phase C: beta cadence

- Testers get tags only.
- `voice_room` can be switched on for chosen testers without a new branch.
- A fix for a beta problem goes on `classic`, ships, and gets a new tag. The other lanes pick it up on their next ship.
