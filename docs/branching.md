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

## Upcoming work plan

### Step 0: switches (on `classic` first, because the beta needs them)

- Read `VIBECUT_EDITION` and `VIBECUT_FEATURES` in `settings_store.py`, and expose them in `/api/settings`.
- `static/index.html` boot script: default to the edition's view, and hide the "Open Studio" and "Voice Room" links when they are off.
- `app.py` and `routes_voice_clone.py`: the voice routes and `/voices` answer 404 when `voice_room` is off.
- Tests for both switches. After this ships, every lane builds the same code and only the configuration differs.

### `classic` (beta)

1. Step 0 above.
2. A founder test pass on every Classic flow, with a click-by-click script: import, plan, render, render-all, variants, hooks, mixer, history, export, batches, and the Creator workspace (clip set, captions, preflight, packet, artifacts, queue).
3. Fix the Classic findings from that pass and from `round_6.md`.
4. Beta setup: first-run keys and voice engines reachable from Classic, plus a beta build with `VIBECUT_EDITION=classic`.

### `studio` (work in progress)

1. R3 open items (`docs/handoff/r3-review.md`):
   - a speech-only retry route
   - Check cancel, and Import cancel and ETA
   - Library "load more"
   - Open in Finish carries the story and shape
2. Show render warnings in Finish (for example "Music bed skipped"). Classic History shows them already.
3. Keep the Edit clone picker, but show it only when `voice_room` is on.

### `voice-room` (hidden, independent)

1. Make the Voice Room page self-contained:
   - one place for the voice library (stock and cloned voices, preview, rename, delete), cloning, and the clean-clip finder
   - its own small API module, so Studio changes cannot break it
2. Reach it from Classic and match the Classic look. Today it borrows `studio.css` and `studio/api.js`.
3. Put it behind `VIBECUT_FEATURES=voice_room`.
4. Still open from the review: a live OpenRouter check of a cloned voice, a Cancel button for voice tasks, and a browser test of the clip picker.
