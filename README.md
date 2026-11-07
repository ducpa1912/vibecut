# DuckSuite

Offline macOS app for turning one long video into the few clips you will post.

```text
Welcome → Check → Edit ⇄ Clean Focus → Preview → Render → Welcome
```

DuckSuite does the local work on this Mac:

- dissect a long video into smart story candidates
- detect text, faces, speech, music and quality
- clean old text with LaMa AI fill or explicit blur
- add captions, local voice-over or dub
- trim, reframe, edit, render 1080p at 24/30 fps
- export MP4, SRT and a cover

No account. No telemetry. No upload unless the user chooses optional cloud render.

## Status

Six-screen Daylight Story Desk UI is implemented. The app is not App Store ready yet.

- `duckcore` local FastAPI core with token handshake.
- Sandboxed SwiftUI shell with `NSOpenPanel` import.
- SQLite project index.
- Static DuckSuite shell.
- Development `.app` builder.
- Engine extraction: Apple Vision, Apple Speech, smart story helpers, LaMa text fill.
- `/api/engine` and `/api/models` show what is ready on this Mac.
- Six screens: Welcome, Check, Edit, Clean Focus, Preview, Render.
- Welcome: upload, recent projects, active queue, finished output, engine and disk.
- Check: scene cuts publish first; Editor opens while transcript, text detection, and stories continue.
- Editor: Proof Rows, transcript, captions, voice, fine trim, Clean focus entry.
- Clean Focus: same Editor frame, only clean tools; scene list, proof pair, Fill/Blur/Off, detect status.
- Preview: Before / Compare / After player; clean runs scene by scene; blurred placeholder is never rendered; readiness counts proofs.
- Render: source-aspect 1080p, queue, state-appropriate pause/resume, output returns to Welcome.
- Clean preview frames are cached per edit version; frame and source endpoints support media-token reads.
- Captions: generate from transcript, edit cue text, download SRT, choose Clean/Bold/Minimal style and bottom/middle/top position, or burn into the render.
- Voice-over: local macOS voices, script from captions, voice-over or voice-only, preview and render mix.
- Language is auto-detect only; no picker.
- UI reviews and screenshots: [docs/teams/README.md](docs/teams/README.md).
- Tests for core auth, projects, upload, engine status, edits, clean layers, media auth, and reveal guards.

See [ROADMAP.md](ROADMAP.md) and [docs/duck/DISTRIBUTION.md](docs/duck/DISTRIBUTION.md).

## Run the development shell

```bash
scripts/serve-duck.sh
```

Open the printed URL. Development data lives in `~/vibecut-lanes/ducksuite`.

## Build the development app

```bash
scripts/build-duck-dev.sh
open "$PWD/build/DuckSuite.app"
```

Requires full Xcode for StoreKit, sandbox and App Store archives. Command Line Tools are enough for `swiftc -typecheck`.

Testing: [docs/handoff/ducksuite-testing.md](docs/handoff/ducksuite-testing.md).

## Docs

- [PRODUCT.md](PRODUCT.md) — product record.
- [ROADMAP.md](ROADMAP.md) — phases and gates.
- [docs/duck/DISTRIBUTION.md](docs/duck/DISTRIBUTION.md) — Mac App Store distribution.
- [docs/duck/COMMERCIAL.md](docs/duck/COMMERCIAL.md) — pricing and margins.
- [docs/duck/ENGINE-REUSE.md](docs/duck/ENGINE-REUSE.md) — what to copy from Studio.
- [docs/handoff/ducksuite-phase1-plan.md](docs/handoff/ducksuite-phase1-plan.md) — detailed build plan.
- [docs/branching.md](docs/branching.md) — branch policy.

## Branch rule

`ducksuite` is the active branch. `studio`, `main` and `classic` are frozen reference points. DuckSuite is a new app; it copies selected Studio engine code, not Studio history.
