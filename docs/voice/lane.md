# Voice Room lane

The Voice Room is its own lane, with its own port, data folder, media library
and recordings. It shares no runtime file with Classic or Studio.

| Item | Value |
|---|---|
| Branch | `voice-room` |
| Port | `8797` |
| Data | `~/vibecut-lanes/voice` |
| Media | `~/vibecut-lanes/media/voiceroom` |
| Recordings | `~/vibecut-lanes/recordings/voiceroom` |

Port `8787` and the founder's data are never used.

## Start and stop

```bash
scripts/voice-serve.sh
```

It refuses a busy port and writes the server PID to
`~/vibecut-lanes/voice/server.pid`. Stop only that PID. Do not `pkill` by
pattern.

Stay on port `8797`. Do not start this lane, a smoke check or a test run on an
ad-hoc or ephemeral port; the lane script writes `server.pid`, and only that PID
is stopped.

In Finder, double-click **scripts/Voice Room Server.command**. It opens
Terminal and starts the same server. Close that Terminal window or press
Ctrl-C to stop it.

## Setup

Top bar → **Setup** in `/voices`.

- OpenRouter key, **Test key**, and the OpenRouter text-model picker.
- OpenCode key, **Test key**, and the local OpenCode login when no key is set.
- **On this Mac**: Apple say, Kokoro, cloud voices and every voice-extraction
  engine, with the install or key hint for each.
- **This app's config** shows `~/vibecut-lanes/voice/settings.json` and
  `~/vibecut-lanes/voice/secrets.json`.

Saving a key here overrides the environment key for this app only. It does not
change Studio or Classic. Saving a new OpenRouter key clears the auth
quarantine; **Test key** checks the key with one request and shows the exact
OpenRouter error if it fails.

Cloned voices are read from this app's `voices/` folder even when OpenRouter is
unavailable. The list does not depend on a cloud call.

## Record a real flow

```bash
scripts/voice-record.sh
VOICE_PATH='/voices?ui=new' scripts/voice-record.sh
```

The browser opens on `http://127.0.0.1:8797/voices` by default, or on
`VOICE_PATH` when set. Click the real flow; press the floating **Finish
recording** button, close the browser, or press Ctrl-C. Wait for `Saved …`.
The Playwright trace lands in
`~/vibecut-lanes/recordings/voiceroom/<date-time>/trace.zip`.

In Finder, double-click **scripts/Record Voice Room.command** after the server
is running. It records the new UI at `/voices?ui=new`.

The founder tests, by hand, with real files. No test video, sound or generated
test file stands in for real media.

## New UI

The new shell is at `/voices?ui=new`. The old page stays at `/voices` and is
still the default. Each page links to the other: **New UI** on the old page,
**Old UI** on the new one.

The new shell uses a left rail on desktop, bottom tabs on mobile, and five
views: Library, Create, Compare, Recent and Settings. It loads
`static/voice/next.css` and `static/voice/next.js`; the old modules are reused
inside the new views.

## Media library

The lane keeps no media by default. `~/vibecut-lanes/media/voiceroom` is empty
after the input copies were removed to save space. Copy a source video there
only when a test needs it. Keep media out of the repo.

## Voice extraction

Voice extraction is already part of this lane through commit `92200c0`
(`fix(voice): import language, clone engine, scripted keep, silent search,
voice queue`). The separate `vibecut-voice-extract` worktree has no newer code.
