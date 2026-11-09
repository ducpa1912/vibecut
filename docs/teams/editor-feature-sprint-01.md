# Editor feature sprint 01

Date: 2026-11-09
Scope: timeline, script, voice, dub, music, brush, optional packs.

## Shipped in this pass

### Timeline

- Four tracks under the video: Video, Script, Voice, Music.
- Video blocks select scenes; script blocks seek.
- Main tool per track:
  - Video: Trim
  - Script: Edit
  - Voice: Preview / Record
  - Music: Add / Remove
- Playhead follows the video; trim In/Out lives in the timeline header.

### Script

- Script tab + full-width drawer under the workspace.
- Original and editable script columns.
- Target language selector (English / Vietnamese / Chinese) auto-translates.
- Rewrite modes: Clean up, Shorten, Punchier.
- Reset returns to source text.
- Editing a script line uses the caption cue save path.
- Captions are generated automatically after Check when speech exists.
- Edit is editable and feeds captions, voice-over and dub.

### Voice and dub

- Inline audio preview in the Voice panel; no popup.
- Per-line Preview button for the first four cues, expandable.
- Generated voice-over over the original sound or voice-only.
- Native microphone recording:
  - microphone entitlement
  - `NSMicrophoneUsageDescription`
  - AVAudioRecorder to the app container
  - saved as `edit.voice`
- Dub builds a voice-only track from the current script.
- Background music upload, stored on the edit.
- Render mix:
  - Dub: original audio muted; dub + music, or dub only.
  - Voice-over: original bed + voice + music.
  - Music only: original + music.
- No separation tool required; separation remains optional.

### Optional packs

Settings lists four downloadable packs:

| Pack | Size | Purpose |
|---|---:|---|
| Kokoro voice pack | 325 MB | local voices |
| Whisper large-v3-turbo | 1.6 GB | speech |
| Qwen3 4B rewrite | 2.26 GB | local rewrite |
| Demucs separation | 84 MB | dub bed |

- Download manager writes to `models/packs`, streams to `.part`, reports progress, removes packs.
- System packs are listed with a link to macOS Translation settings.
- No executable code is downloaded.

### Clean brush

- `Paint a mask` in Edit opens Clean Focus with a brush stage.
- Canvas strokes are normalized and stored as a manual clean layer.
- Fill or Blur, brush size, undo, clear, apply.
- Manual layer uses the existing mask/raster path, so proof and render agree.

## Honest limits

- Apple Translation needs its language packs installed in macOS.
- Apple Intelligence is unavailable on this Mac; Rewrite falls back to a basic filler cleanup, not the 4B model.
- Downloaded Qwen/Whisper/Kokoro/Demucs files are data packs; their alternate engines are not wired in this build.
- Dub keeps music only if the user adds a BGM file or a separation engine exists. Without either, original audio is muted and dub is alone.
- Timeline supports select, trim and the four track tools; split/reorder are next.
- No brush eraser; use Clear and repaint.

## Verification

- 41 Python tests pass.
- Xcode build and unsigned arm64 archive pass.
- Browser checks: 4 timeline tracks, Script drawer, Voice actions, brush canvas, 4 pack rows.
- Proxy playback and inline preview retained.
