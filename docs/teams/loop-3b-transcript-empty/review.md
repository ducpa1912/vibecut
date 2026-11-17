# Loop 3B review — the silent missing transcript box

**Verdict: pass.** Founder: "where is my script in the preview panel?" The box was not rendered at all when there were no cues, so nothing explained the absence.

## Why there is no transcript

The stored check result has `transcript: {language: null, provider: null, segments: 0, text: ""}` and `engine.stt_errors` with four failed routes. Read from the scratch copy of `prj_e95348a97316`:

- the local speech route returned no transcript;
- the optional Whisper route was not installed;
- the OpenRouter routes failed (no ffmpeg on the dev path / no transcript).

The transcript box used `overlayCuesForTime()`; with zero cues it rendered nothing. The full line-by-line list was removed in `1d48020` on 2026-11-09; the script now lives in the timeline's Script lane and Script Focus. `transcriptRow()` remains dead code. The old list is not brought back.

## Fix

- The Edit preview always shows a **Transcript** box for a video scene, even with zero cues.
- Empty state: **No transcript** and one plain sentence: “No speech was read. Run Check again, or add a speech engine in Settings.” No model name.
- **Hide / Show** stays in the head; after Hide the button reads **Show**, so the box can be brought back.
- At ≤1200 px the box moves under the picture; the picture shrinks to `calc(100% - 205 px)` and the box is capped at 200 px, so it no longer covers the picture or the timeline.

## Measured

Script: `NODE_PATH="$(npm root -g)" node /tmp/probe-3b-final.cjs` against `build/opencode-3a/root`.

| Viewport | Box | Picture | Overlap | Head / Hide / Show | Empty text clipped |
|---|---|---|---|---|---|
| 800×600 | y 355–554, w 198 | y 63–266, w 156 | **no** | present, Hide → Show | **no** |
| 1024×700 | y 365–511, w 422 | y 63–288 | **no** | present | no |
| 1280×800 | beside, y 67, w 240 | y 67, h 478 | **no** | present | no |
| 1440×900 | beside, y 67, w 240 | y 67, h 538 | **no** | present | no |
| 200 % (720×450) | y 355, capped 200, scrolls | y 63, h 278 | **no** | present | no horizontal clip |

At 800×600 the transcript ends at **479 px**, the timeline starts at **486 px**: no overlap. Before the fix the box did not exist.

## What got worse

- At 800×600 and 200 % the picture is smaller (156 px wide / 278 px tall at 800) to leave room for the transcript. The story is still readable in the picture; the box is the point.
- At 200 % the empty message scrolls inside a 200 px box.
- The old full transcript list is still absent by product decision; users use the timeline Script lane.

## Not tested

- VoiceOver and keyboard focus of Hide/Show.
- A project with real cues at 800×600 (the review project has none); the cue rows use the same container.
- The story media inspector, which intentionally has no transcript box.
