# Branches and shipping

Four branches share one codebase. Each lane is independent: it owns its UI,
routes and docs, and it does not merge another lane into itself automatically.

| Branch | Role | Worktree | Port | Data |
|---|---|---|---|---|
| `main` | Integration and release union. Only an explicit release merge moves it. | release checkout | — | — |
| `classic` | Classic view and beta launch focus. | `~/code/vibecut-classic` | 8796 | `~/vibecut-lanes/classic` |
| `studio` | Studio view (Import → Moments → Edit → Finish). | `~/code/vibecut-studio` | 8795 | `~/vibecut-lanes/studio` |
| `voice-room` | Voice Room, voice clone, voice library, voice extraction. | `~/code/vibecut-voice` | 8797 | `~/vibecut-lanes/voice` |

Port 8787 is the founder's server. No lane uses it.

## Lane isolation

Each lane has its own page, port, data folder and media folder. Nothing is
shared at runtime:

```bash
eval "$(scripts/lane-env.sh classic)"   # or studio / voice
python3 app.py
```

Media for a lane lives in `~/vibecut-lanes/media/<lane>`. Tests get their own
settings and secrets files per test, so a saved key or rights lock cannot leak
into the next test.

Classic and Voice Room ship with `scripts/ship-lane.sh`: it takes in their own
branch from GitHub, runs the suite and pushes the branch. **It never moves
`main` and never merges another lane.** Studio may use `scripts/ship.sh` only
for an explicit `main` release. When the founder asks for a release, the
release engineer merges the selected lane into `main` and runs the Classic,
Studio and Voice Room guards before pushing.

## The one rule

**A lane ships itself with `scripts/ship-lane.sh` from its own worktree.**
The script:

1. fetches GitHub,
2. takes in a newer copy of the same lane (conflicts stop here),
3. runs JavaScript syntax checks,
4. runs the test suite,
5. pushes the lane.

It does not move `main` and it does not merge another lane. A lane-to-lane or
lane-to-`main` merge is a separate, explicit release decision.

Never commit on `main` directly, never force-push, and never delete a feature on
a lane to hide it. Hide features with switches (below).

## Who owns what

Each lane edits its own files freely. Shared files take small, additive changes
only. Ship them soon, so the other lanes pick them up on their next ship.

New HTTP routes go into the lane's module (`routes_classic.py`, `routes_studio.py`,
`routes_voice_clone.py`), never into `app.py`. `tests/test_lane_routes.py` fails if
`app.py` gains a route.

| Area | Owner lane | Files |
|---|---|---|
| Classic view | `classic` | `static/classic/**` (own page, JS and CSS), `routes_classic.py` |
| Studio view | `studio` | `static/index.html` (Studio page), `static/studio/**`; `edits.py`, `routes_edits.py`, `compose_render.py`, `story_queue.py`, `routes_check.py`, `routes_library.py`, `routes_studio.py` |
| Voice features | `voice-room` | `static/voice/**` (own `api.js`, `ui.js`, `voice.css`), `static/voices.html`, `voice_clone.py`, `voice_extract.py`, `routes_voice_clone.py` |
| Shared core | any lane, additive | `app.py`, `pipeline.py`, `audio.py`, `tts.py`, `stt.py`, `music.py`, `render.py`, `settings_store.py`, `workflow_config.py`, `admin/`, tests of shared code |

## Hiding features: switches, not branches

What a build shows is set by configuration, so one codebase serves every lane.
Planned switches (see the plan below):

- `VIBECUT_EDITION=classic|studio|all`: which view opens by default, and whether
  the other view's link shows. The beta build uses `classic`.
- `VIBECUT_FEATURES=voice_room,...`: turns on hidden features. If `voice_room` is
  off, `/voices` and the voice clone routes answer 404 and no link to them shows.

## Beta releases

When the founder test pass on `classic` is clean, run this from the classic worktree:

```bash
scripts/release.sh --founder-passed
```

It tags the shipped `classic` as `beta-YYYYMMDD-N` and pushes the tag. It refuses
when:

- you are on another lane,
- there are uncommitted changes,
- the lane does not match GitHub,
- the release commit is not signed.

Testers build from the tag, with `VIBECUT_EDITION=classic` and no
`VIBECUT_FEATURES`.

## Working with OpenCode or another session

Give each session one lane worktree. Tell it to commit on that lane and finish
with `scripts/ship-lane.sh`. Two sessions on the same lane at once will conflict; use
one session per lane.
