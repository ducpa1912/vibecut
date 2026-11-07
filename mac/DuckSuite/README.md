# DuckSuite Mac shell

Day 1 feasibility shell for the Mac App Store build.

## Requirements

- Full Xcode 26+ (Command Line Tools alone cannot build StoreKit, entitlements or an App Store archive).
- Apple Silicon Mac running macOS 26+.
- Optional: `xcodegen` to generate the project from `project.yml`.

## Development bundle without Xcode

From the repo root:

```bash
scripts/build-duck-dev.sh
open "$PWD/build/DuckSuite.app"
```

This builds the Swift shell, the PyInstaller `duckcore` sidecar, the static DuckSuite page, the LaMa model and any compiled Apple helpers present in `bin/`.

FFmpeg is not included until an LGPL build is supplied:

```bash
DUCK_FFMPEG=/path/to/lgpl/ffmpeg scripts/build-duck-dev.sh
```

## Generate the Xcode project

Full Xcode 26+ is required for StoreKit, App Sandbox testing and App Store archives.

```bash
cd mac/DuckSuite
xcodegen generate
open DuckSuite.xcodeproj
```

Or create an Xcode project manually with the same bundle ID, deployment target, entitlements and Info.plist.

Testing steps: [docs/handoff/ducksuite-testing.md](../../docs/handoff/ducksuite-testing.md).

## What must be in the bundle

```text
DuckSuite.app/Contents/Helpers/duckcore
DuckSuite.app/Contents/Helpers/ffmpeg
DuckSuite.app/Contents/Helpers/ffprobe
DuckSuite.app/Contents/Helpers/vision_probe
DuckSuite.app/Contents/Helpers/transcribe_apple
DuckSuite.app/Contents/Helpers/translate_apple
DuckSuite.app/Contents/Resources/base-models/lama_fp32.onnx
DuckSuite.app/Contents/Resources/static/duck/
```

`duckcore` is the bundled Python sidecar. It reads one token line from stdin and prints one handshake line:

```json
{"port": 51234, "pid": 1234}
```

The Swift shell passes a 256-bit token on stdin, reads the handshake from stdout, and loads:

```text
http://127.0.0.1:<port>/#t=<token>
```

The page removes the fragment immediately and keeps the token in memory.

## Day 1 acceptance

- Clean Mac launch without Terminal, Homebrew or network.
- Local API rejects requests without the bearer token.
- StoreKit test purchase for the CPU Render product.
- One sample 1080p render with bundled ffmpeg and LaMa.

## Not here yet

- Helper build scripts.
- Xcode project checked in.
- StoreKit configuration file.
- App Store archive and privacy manifest.
