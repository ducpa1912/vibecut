# Voice Room lane

The Voice Room is its own lane, with its own port and its own files in this
worktree's git-ignored `data/` folder. It runs on its own pinned copy of the
shared backend. See `docs/voice/runtime.md` for the pin rule and for what the
founder keeps shared for development: Python, models and Playwright.

| Item | Value |
|---|---|
| Branch | `voice-room` |
| Port | `8797` |
| Data (jobs, settings, keys, logs) | `data/` |
| Media, including real test files | `data/media` |
| Recordings | `data/recordings` |
| Cloned voices | `data/voices` |
| Music library | `data/music` |

`data/` is never committed. It is also the only copy: `git clean -X` or removing
this worktree deletes the jobs, keys, clones and media with it.

Port `8787` and the founder's data are never used.

## Start and stop

```bash
scripts/voice-serve.sh
```

It refuses a busy port and writes the server PID to
`data/server.pid`. Stop only that PID. Do not `pkill` by
pattern.

Stay on port `8797`. Do not start this lane, a smoke check or a test run on an
ad-hoc or ephemeral port; the lane script writes `server.pid`, and only that PID
is stopped.

In Finder, double-click **scripts/Voice Room Server.command**. It opens
Terminal and starts the same server. Close that Terminal window or press
Ctrl-C to stop it.

## Setup

Rail → **Settings** in `/voices`, one Setup for the app.

- **Keys**: OpenRouter, MiniMax and ElevenLabs. Save one key per provider;
  Setup never reads a saved key back.
- **Voices**: Apple voices, Kokoro, MiniMax Speech, ElevenLabs, and one
  **OpenRouter voices** row. HeyGen, Fish and Gemini share the OpenRouter key;
  they are not separate setups.
- **Local Whisper**, with its install hint and **Check again**.
- **Library** backup and restore, and a portable `.vcutvoice` import.

Saving a key here overrides the environment key for this app only. It does not
change Studio or Classic. Cloned voices are read from `data/voices` even when OpenRouter is unavailable.

## Record a real flow

```bash
scripts/voice-record.sh
```

The browser opens on `http://127.0.0.1:8797/voices`. Click the real flow; press
the floating **Finish recording** button, close the browser, or press Ctrl-C.
Wait for `Saved …`. The Playwright trace lands in
`data/recordings/<date-time>/trace.zip`.

In Finder, double-click **scripts/Record Voice Room.command** after the server
is running.

The founder tests, by hand, with real files. No test video, sound or generated
test file stands in for real media.

## The app

`/voices` is the standalone **VibeCut Voice** app. In the voice lane (`edition
voice`) `/` also opens it, and there is no Classic or Studio page behind it.
The old page and the `?ui=new` switch are retired.

The app uses a left rail on desktop, bottom tabs on mobile, and five views:
Library, Create, Compare, Recent and Settings. It loads `static/voice/next.css`
and `static/voice/next.js`.

## Media library

`data/media` holds the founder's real files, including the ones the tests read
(`docs/testing/real-media.md`). Music tracks go in `data/music`. Keep media out of
the repo.

## Voice extraction

Voice extraction is already part of this lane through commit `92200c0`
(`fix(voice): import language, clone engine, scripted keep, silent search,
voice queue`). The separate `vibecut-voice-extract` worktree has no newer code.
