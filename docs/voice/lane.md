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
```

The browser opens on `http://127.0.0.1:8797/voices`. Click the real flow; close
the browser when done. The Playwright trace lands in
`~/vibecut-lanes/recordings/voiceroom/<date-time>/trace.zip`.

The founder tests, by hand, with real files. No test video, sound or generated
test file stands in for real media.

## Media library

The lane keeps no media by default. `~/vibecut-lanes/media/voiceroom` is empty
after the input copies were removed to save space. Copy a source video there
only when a test needs it. Keep media out of the repo.

## Voice extraction

Voice extraction is already part of this lane through commit `92200c0`
(`fix(voice): import language, clone engine, scripted keep, silent search,
voice queue`). The separate `vibecut-voice-extract` worktree has no newer code.
