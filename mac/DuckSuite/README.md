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

FFmpeg is an LGPL 7.1.1 build made from source:

```bash
scripts/build-ffmpeg-lgpl.sh
```

That writes `build/ffmpeg-lgpl/bin/ffmpeg` and `ffprobe`. `build-duck-dev.sh`
copies them, `libdav1d.7.dylib` for AV1 decode, and `Licenses/` into the app.
Override with `DUCK_FFMPEG` / `DUCK_FFPROBE` only when testing another LGPL
build. Never ship a Homebrew GPL build.

## Build with Xcode

Full Xcode is required for App Sandbox signing, StoreKit testing and App Store archives.

```bash
# One-time
brew install xcodegen

# Build the sidecar, helpers, model and static page, then the Xcode app
scripts/build-xcode-dev.sh
open "$PWD/build/DuckSuite-Xcode.app"
```

Output: `build/DuckSuite-Xcode.app`, ad-hoc signed for local testing.

Manual equivalent:

```bash
scripts/build-duck-dev.sh
cd mac/DuckSuite
xcodegen generate
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project DuckSuite.xcodeproj -scheme DuckSuite -configuration Release \
  -derivedDataPath ../../build/xcode-derived BUILD CODE_SIGNING_ALLOWED=NO build
open DuckSuite.xcodeproj
```

The Xcode project embeds:

```text
Contents/Resources/duckcore/
Contents/Resources/static/duck/
Contents/Resources/Helpers/
Contents/Resources/base-models/lama_fp32.onnx
```

`project.yml` is the source of truth. `Info.plist` and `DuckSuite.entitlements` are generated from its `info.properties` and `entitlements.properties`. The generated `.xcodeproj` is not checked in.

App Store archive needs a real Apple Development / App Store signing identity and `DEVELOPMENT_TEAM`. Current local archive is unsigned.

Testing steps: [docs/handoff/ducksuite-testing.md](../../docs/handoff/ducksuite-testing.md).

## What must be in the bundle

```text
DuckSuite.app/Contents/Helpers/duckcore            # dev bundle
DuckSuite.app/Contents/Helpers/ffmpeg
DuckSuite.app/Contents/Helpers/ffprobe
DuckSuite.app/Contents/Helpers/vision_probe
DuckSuite.app/Contents/Helpers/transcribe_apple
DuckSuite.app/Contents/Helpers/translate_apple
DuckSuite.app/Contents/Resources/Helpers/duckcore  # Xcode bundle
DuckSuite.app/Contents/Resources/duckcore/          # Xcode PyInstaller folder
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

## Shipped in the bundle

- `PrivacyInfo.xcprivacy` with no tracking and no collected data.
- `AppIcon` asset catalog and `AppIcon.icns`.
- LGPL FFmpeg 7.1.1, ffprobe, and `libdav1d.7.dylib`.
- License texts under `Contents/Resources/Licenses/`.

## Not here yet

- Signing identity and `DEVELOPMENT_TEAM`.
- App Store signed archive and upload.
- Published support and privacy URLs.
- A licensed demo video for App Store screenshots.
