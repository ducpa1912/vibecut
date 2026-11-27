# DuckSuite UI revamp — build report

**Date:** 2026-11-07  
**Branch:** `ducksuite`  
**Scope:** six-screen Daylight Story Desk UI, local core integration, review records.

## Shipped

- Welcome: upload, recent projects, active queue, recent renders, engine/disk.
- Check: scene-first handoff; Editor opens while transcript, text detection, and stories continue.
- Edit: Proof Rows, transcript, captions, voice, fine trim, Clean focus entry.
- Clean Focus: same Edit frame, clean tools only, proof pair, Fill/Blur/Off, layer list, detection status.
- Preview: Before / Compare / After player; After default; clean proof per scene; blurred placeholder; proof readiness.
- Render: source-aspect 1080p, queue, one state-appropriate queue control, cancelled rows without false progress, output.
- Settings remains a native sheet.

## Backend changes

- Check publishes partial scenes after the scene scan and reuses them in the analysis pass.
- `analyze_source` accepts precomputed scenes and scan info.
- Added media reads: project frame, source, transcript, raw upload, reveal guard.
- Media reads accept the launch token as a query value or session cookie.
- Clean preview frames are cached per edit version; repeated previews are instant.
- Render queue list includes edit duration, fps, width, and height.
- Asset serving uses explicit media types; fixes the sandboxed app bundle where `StaticFiles` returned 500 for JS/CSS.
- CSP allows inline styles; scripts stay same-origin.

## Tests

```text
15 passed
node --check static/duck/app.js
swiftc -typecheck -target arm64-apple-macosx26.0 mac/DuckSuite/DuckSuite/*.swift
dev .app builds and launches
```

## Review evidence

- [Team — Welcome & Check](team-1-welcome-check/review-02.md)
- [Team — Edit & Clean Focus](team-2-edit-clean/review-02.md)
- [Team — Preview & Render](team-3-preview-render/review-02.md)

## Known launch risks

1. **LaMa proof quality.** Very large stylized text on scene 01 leaves a dark artifact. Scene 07 is the verified clean example. The UI exposes Fill/Blur/Off and does not hide the result.
2. **Fixture.** The primary test is 46 s and 1080×1080. App Store screenshots need a longer 16:9 source.
3. **App Store hardening.** LGPL ffmpeg, privacy manifest, StoreKit, review notes, and notarization are not done.
4. **Swift tests.** Full Xcode is unavailable; verification is typecheck, dev app build, and launch.
5. **Render proof gate.** Readiness counts layers/proofs, not human-verified clean quality. A quality check is needed before claiming “clean” in marketing.

## Next

1. Fix the large-text mask/fill path or add an explicit “review this proof” gate.
2. Replace the 46 s square fixture with a long 16:9 App Store fixture.
3. Local dub.
4. App Store hardening.
