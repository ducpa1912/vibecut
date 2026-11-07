# DuckSuite

Offline macOS app for turning one long video into the few clips you will post.

```text
Import → Analyze → Edit → Render → Export
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

Day 1 shell and Day 2 projects/import are implemented. The app is not App Store ready yet.

- `duckcore` local FastAPI core with token handshake.
- Sandboxed SwiftUI shell with `NSOpenPanel` import.
- SQLite project index.
- Static DuckSuite shell.
- Development `.app` builder.
- Engine extraction: Apple Vision, Apple Speech, smart story helpers, LaMa text fill.
- `/api/engine` and `/api/models` show what is ready on this Mac.
- Tests for core auth, projects and engine status.

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
