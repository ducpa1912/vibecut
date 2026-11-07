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

## 3b. Run a real check

```bash
TOKEN=<printed token>
PROJECT=<project id>
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/check"
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/check"
```

The check runs in the background. Expected progression:

```text
queued → Scanning → Reading → Stories → Check → done
```

When done, the response contains:

- `result.meta` — duration, size, fps
- `result.transcript` — provider, language, segment count
- `result.stories.stories` — smart story candidates
- `result.report.tracklets` — detected text regions with fill plans

A 46-second 1080p clip on this Mac took about 50 seconds and produced one story and 80 text tracklets.

### Full edit, story, and clean

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/full"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/stories/$STORY/smart-cut"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/clean/from-check"
```

Expected:

- full edit clips match the Check scenes
- smart cut uses the story clips
- clean layers are one per Check tracklet
- layer actions are `fill`, `blur` or `exclude`

### Preview and render

```bash
curl -s -o preview.jpg -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/clean/preview?time=2.0"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/render"

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/render"

curl -s -o out.mp4 -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/render/file"
```

Expected render: H.264/AAC MP4, 1080p short side, 24 or 30 fps, original audio. A 5-second smoke render took about 100 seconds on this Mac with LaMa fill.

### Queue

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/queue"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/queue/pause"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/queue/resume"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/render/cancel"
```

The queue is one local worker, first queued first. A completed or cancelled job stays in the list.

### Settings

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/settings"

curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"online_enabled":true,"online_endpoint":"https://render.example.com"}' \
  "http://127.0.0.1:8797/api/settings"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/models/lama/verify"
```

Expected: language `auto`, model hash matches `1faef...`, invalid endpoint rejected.

### Captions

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/captions/generate"

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/captions.srt"
```

Expected: one cue per transcript segment piece, editable text, valid SRT. A 46-second full edit produced 35 cues in this test.

Burn-in:

```bash
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"burn":true}' \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/captions"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/render"
```

Expected: the MP4 contains readable captions with a dark rounded background and keeps the audio. A 2-second smoke render passed in this test.

Caption style:

```bash
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"style":"bold","position":"top"}' \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/captions"
```

Styles: `clean`, `bold`, `minimal`. Positions: `bottom`, `middle`, `top`.

### Voice-over

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/voices"

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"voice":"Samantha","mode":"voice_over"}' \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/voice"

curl -s -o voice.wav -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8797/api/projects/$PROJECT/edits/$EDIT/voice/audio"
```

Expected: 2-second edit produced a 2.000s mono 22.05kHz WAV; render mixed it over the original audio.

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

## UI revamp smoke — six screens

Start the dev shell:

```bash
DUCK_TOKEN=review-token DUCK_PORT=8797 scripts/serve-duck.sh
```

Open `http://127.0.0.1:8797/#t=review-token`.

Expected:

1. **Welcome** opens on projects, upload, active queue, recent renders, engine.
2. **Check** cuts scenes first, publishes the scene strip, and auto-opens Editor while transcript/text detection continue.
3. **Edit** shows Proof Rows, transcript, Clean/Captions/Voice, fine trim.
4. **Clean Focus** is the Edit step in focus mode; only clean tools; proof pair; Fill/Blur/Off.
5. **Preview** defaults to the full After proof; Before/Compare/After toggle; scene strip; proof readiness.
6. **Render** shows source-aspect 1080p, one queue control, cancelled rows without a false progress bar, output returning to Welcome.

Review evidence:

- `docs/teams/team-1-welcome-check/review-02.md`
- `docs/teams/team-2-edit-clean/review-02.md`
- `docs/teams/team-3-preview-render/review-02.md`

Known launch risk: LaMa proof quality on very large stylized text. Scene 01 shows an artifact; scene 07 is the verified clean example.
