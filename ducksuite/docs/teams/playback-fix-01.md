# Editor playback fix

Date: 2026-11-08
Symptom: after Check, the video in Check and Edit showed a poster but would not play.

## Cause

The source endpoint served the imported file unchanged. The test fixture and
common modern imports are AV1 MP4. WKWebView on macOS does not reliably decode
AV1, so the `<video>` element loaded the poster and then failed silently. The
render pipeline was unaffected because it decodes through bundled ffmpeg +
libdav1d.

## Fix

- `/api/projects/{id}/source` now serves a cached H.264/AAC editor proxy.
- Proxy is generated once at 1280×720 maximum with VideoToolbox:
  - `h264_videotoolbox`
  - AAC 160 kbps
  - `+faststart`
  - source aspect preserved
- Generation starts in the background after import.
- If playback arrives first, the source endpoint generates it synchronously
  and then serves it.
- The original file remains the render master. Proofs and renders are unchanged.
- FileResponse range support verified: `Range: bytes=0-1023` returns `206`.

## Verified

```text
preview.mp4     2.5 MB for a 12 s clip
video           h264, 720 × 720
audio           aac
generation      0.9 s
range request   206 Partial Content
```

## Scope

- No change to render quality or codec.
- Editor playback now works for AV1, HEVC, and H.264 sources.
- The proxy is local, cached, and never uploaded.
