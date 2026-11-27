# App Store metadata

Use this file when filling the App Store Connect record.

## App information

| Field | Value |
|---|---|
| Name | DuckSuite |
| Subtitle | Clean and cut video locally |
| Bundle ID | `com.ducksuite.app` |
| SKU | `ducksuite-mac-1` |
| Primary category | Photo & Video |
| Secondary category | Productivity |
| Age rating | 4+ |
| Price | $29.00 |
| In-app purchases | None |
| Minimum OS | macOS 26.0 |
| Architecture | Apple silicon (arm64) |
| Copyright | Copyright © 2026 DuckSuite |

## Promotional text

> Find the useful moments in a long video, remove the burned-in text, and
> export clean vertical clips. Everything stays on your Mac.

## Description

Turn one long video into short clips you can actually use.

DuckSuite reads a talking-head recording and finds the parts worth keeping. It
cuts scenes, transcribes speech, finds burned-in captions and titles, and
removes old text from the picture. You review each scene, then export clean
1080p MP4 clips at 24 or 30 fps.

**Made for local work**

No account. No upload. No telemetry. Your video, transcript, frames, and
exports stay in the app's local container on this Mac.

**Six steps, one desk**

- **Welcome** shows recent renders and one clear way in.
- **Check** cuts scenes first and opens the Editor while transcript, text
  detection, and story ideas continue.
- **Edit** shows proofs, transcript lines, and every clean layer.
- **Clean Focus** is the same frame without the noise: Fill, Blur, or Off.
- **Preview** generates a before/after proof for each scene. Blur is only a
  temporary processing placeholder.
- **Render** writes a 1080p H.264 MP4 and reveals it in Finder.

**Clean that you can check**

Every scene gets a proof made by the same pipeline as the final render. Review
the before and after, turn a layer off, or mark a scene as not clean. Rendering
stays blocked until each scene has a decision.

**Built for Apple silicon**

The app runs a local Python core, a bundled LaMa fill model, and LGPL FFmpeg.
H.264 encoding uses Apple VideoToolbox. Nothing is downloaded after install.

**Good to know**

- 1080p output, 24 or 30 fps.
- MP4, MOV, and M4V input.
- No colour grading, LUTs, or publish kit.
- No URL or social-platform import.
- macOS 26 or later on Apple silicon.
- One-time purchase. No subscription.

## Keywords

```text
video editor,remove text,clean video,burned-in text,captions,transcript,local,offline,creator,talking head
```

## Support and privacy URLs

| Field | Value |
|---|---|
| Support URL | TODO |
| Privacy policy URL | TODO |
| Marketing URL | Optional |

## App privacy answers

| Question | Answer |
|---|---|
| Does the app collect data? | No |
| Does the app track users? | No |
| Third-party advertising | No |
| Third-party analytics | No |
| Account creation | No |
| User content leaves the device | No |

The bundled `PrivacyInfo.xcprivacy` must match these answers.

## Screenshots

Upload these from `docs/appstore/screenshots/`:

| Order | 1280 × 800 | 1440 × 900 | Caption |
|---|---|---|---|
| 1 | `01-welcome-1280x800@2x.png` | `01-welcome-1440x900@2x.png` | One long video in. |
| 2 | `02-check-1280x800@2x.png` | `02-check-1440x900@2x.png` | Scenes first, the rest continues. |
| 3 | `03-edit-1280x800@2x.png` | `03-edit-1440x900@2x.png` | Every scene, transcript, and layer. |
| 4 | `04-clean-focus-1280x800@2x.png` | `04-clean-focus-1440x900@2x.png` | Clean the frame. Keep the choice. |
| 5 | `05-preview-1280x800@2x.png` | `05-preview-1440x900@2x.png` | Before and after, scene by scene. |
| 6 | `06-render-1280x800@2x.png` | `06-render-1440x900@2x.png` | 1080p locally. Nothing uploaded. |

Files ending `@2x` are 2560 × 1600 and 2880 × 1800, both accepted Mac sizes.
The screenshots use the internal `check-smoke` fixture. Clear its footage or recapture with a licensed demo before submission.

## Review information

- Demo account: not required.
- Review notes: `docs/duck/APP-REVIEW-NOTES.md`.
- Contact: TODO before submission.

## Export compliance

`ITSAppUsesNonExemptEncryption` is `false`. The app only uses loopback HTTP
with a random per-launch token.

## Pricing

| Field | Value |
|---|---|
| Price tier | $29.00 |
| Subscription | None |
| Introductory offer | None |
| Promo codes | Optional |
| Education discount | Optional |
