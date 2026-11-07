# DuckSuite testing

Date: 2026-11-07
Scope: Day 1 shell + Day 2 projects/import.

## 1. Browser shell

```bash
scripts/serve-duck.sh
```

Open the printed URL. The token is in the URL fragment and is removed by the page after load.

What works:

- local core health
- project list
- development import by absolute path (browser fallback)
- project delete

The browser fallback is development only. The Mac app uses `NSOpenPanel` and copies the file into the sandbox container.

Stop the server with `Ctrl+C`.

## 2. Python tests

```bash
python3 -m pytest -q tests/test_duckcore.py
```

Expected: `5 passed`.

## 3. Swift typecheck

Command Line Tools are enough for a syntax/type check:

```bash
swiftc -typecheck -target arm64-apple-macosx26.0 mac/DuckSuite/DuckSuite/*.swift
```

Expected: no output.

## 3. Engine status

With the dev server running:

```bash
TOKEN=<printed token>
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8797/api/engine
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8797/api/models
```

Expected:

- `vision.available: true`
- `speech.apple: true`
- `fill.method: "lama"`, `fill.ready: true`
- `models[0].id: "lama"`

## 4. Development app bundle

```bash
scripts/build-duck-dev.sh
open "$PWD/build/DuckSuite.app"
```

This builds:

```text
build/DuckSuite.app/Contents/MacOS/DuckSuite
build/DuckSuite.app/Contents/Resources/duckcore/duckcore
build/DuckSuite.app/Contents/Resources/static/duck/
build/DuckSuite.app/Contents/Resources/base-models/lama_fp32.onnx
build/DuckSuite.app/Contents/Helpers/vision_probe
build/DuckSuite.app/Contents/Helpers/transcribe_apple
```

The app launches, starts `duckcore` on `127.0.0.1:0`, and loads the shell in WKWebView.

Current dev bundle does **not** include ffmpeg. The shell and projects work; video rendering does not yet. Set an LGPL ffmpeg path when it exists:

```bash
DUCK_FFMPEG=/path/to/lgpl/ffmpeg scripts/build-duck-dev.sh
```

Do not put Homebrew GPL ffmpeg in a release bundle.

## 5. App data reset

The app uses the sandbox container:

```text
~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite/
```

The development server uses:

```text
~/vibecut-lanes/ducksuite/
```

Delete a test data folder only when the app is closed. Keep `models/` if you want to avoid re-copying LaMa.

## 6. StoreKit / full Xcode

This machine has Command Line Tools only. Full Xcode is required for:

- App Sandbox build
- StoreKit configuration and purchase test
- TestFlight / App Store archive
- nested-code signing

With Xcode installed:

1. `cd mac/DuckSuite && xcodegen generate`
2. Open `DuckSuite.xcodeproj`.
3. Add a StoreKit configuration with product IDs:
   - `com.ducksuite.app.render.cpu.10h`
   - `com.ducksuite.app.render.gpu.10h`
4. Edit Scheme → Run → Options → StoreKit Configuration → select the config.
5. Run on a clean Mac user. Test purchase, cancel, restore and manage subscription.
6. Archive and validate before upload.

## 7. Day 1 acceptance

- Clean Mac launch without Terminal, Homebrew or network.
- Local API rejects requests without the bearer token.
- StoreKit test purchase for the CPU Render product.
- One sample 1080p render with bundled ffmpeg and LaMa.

Current status: shell + local core + projects pass. ffmpeg/render and StoreKit still need full Xcode and the LGPL ffmpeg build.

## 8. Day 2 acceptance

- Import 3 real clips from the Mac app.
- Source copied into the container.
- Project card appears after import.
- Delete removes the project row and copied source.
- No path import, no URL import.
