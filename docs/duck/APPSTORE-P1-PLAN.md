# App Store P1 execution plan

Date: 2026-11-07  
Scope: the P1 items between “app builds” and “archive can be uploaded.”

## Order

```text
1. Xcode + project
2. LGPL ffmpeg
3. Nested-code signing
4. PrivacyInfo + privacy answers
5. StoreKit decision
6. Own-footage attestation
7. Third-party notices + licenses
8. Window minimum
9. Screenshots
10. Review notes
11. Archive + TestFlight
```

Do not start screenshots until Clean P1 is closed; do not upload until nested code and privacy pass.

## 1. Xcode and project

**Need:** full Xcode 26+ for `xcodebuild archive`, StoreKit testing, and App Store upload. Command Line Tools are enough for `swiftc` and local `.app` builds, not for submission.

**Options**

- Install Xcode from the Mac App Store or Apple Developer downloads.
- Or archive on a cloud Mac CI with Xcode 26 and App Store Connect API key.
- XcodeGen is a separate convenience: `brew install xcodegen`, then generate from `mac/DuckSuite/project.yml`.
- `xcodebuild -version` must report Xcode, not Command Line Tools.
- Select it: `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.

**Exit:** `xcodebuild -version` returns Xcode 26+; `xcodebuild -list` sees the DuckSuite scheme.

## 2. LGPL ffmpeg

**Need:** `Contents/Helpers/ffmpeg` and `ffprobe` built LGPL, with VideoToolbox. No `--enable-gpl`, no libx264, no libx265.

**Tasks**

- Build or obtain an LGPL-only ffmpeg for arm64.
- Verify: `ffmpeg -version` configuration has no `--enable-gpl`, no `libx264`, no `libx265`.
- Copy into `Contents/Helpers/`.
- Add the LGPL license text and source offer to the bundle.
- Update `scripts/build-duck-dev.sh` to copy the approved binary from `DUCK_FFMPEG`.

**Exit:** `ffmpeg -version` is LGPL; app renders 1080p H.264 through VideoToolbox; no GPL binary in the bundle.

## 3. Sign nested code

**Need:** every executable and dylib signed before the outer app. `codesign --deep` is not a submission strategy.

**Sign order**

1. ONNX Runtime dylibs / Python framework dylibs.
2. Python executable.
3. `duckcore` executable.
4. Swift helpers: `vision_probe`, `transcribe_apple`, `translate_apple`.
5. Models are data, not code; no signature required beyond SHA-256.
6. Outer `DuckSuite.app`.

**Tasks**

- Use `xcodebuild archive` with automatic signing, or an inside-out `codesign` script for CI.
- Verify: `codesign --verify --deep --strict --verbose=2 build/DuckSuite.app`.
- Check entitlements on nested code; only the app needs sandbox. Do not grant unnecessary JIT/unsigned-memory entitlements.
- Test Python + ONNX Runtime under hardened runtime. If ONNX needs JIT, document and justify the entitlement.

**Exit:** strict verification passes; no unsigned nested code; archive validates in Organizer.

## 4. PrivacyInfo and privacy answers

**Bundle:** `Contents/Resources/PrivacyInfo.xcprivacy`.

**Content**

- `NSPrivacyTracking`: false.
- `NSPrivacyTrackingDomains`: empty.
- `NSPrivacyCollectedDataTypes`: empty for local-only v1.
- `NSPrivacyAccessedAPITypes`: only APIs actually used.
  - File timestamp: app container reason `C617.1`; user-selected file reason `3B52.1` if reading imported file dates.
  - Disk space: app container `E174.1`; user-selected file `85F4.1` if inspecting imported files.
  - UserDefaults: `CA92.1` only if the app uses it. Audit first; do not add unused reasons.
- App Privacy label: Data Not Collected.
- Privacy policy URL and support URL in App Store Connect.

**Exit:** manifest validates; App Privacy answers match the manifest; no undeclared required-reason API.

## 5. StoreKit decision

**v1:** local-only. Remove the Render subscription scaffold.

- Delete `mac/DuckSuite/DuckSuite/StoreManager.swift` or move it behind a future cloud flag.
- No StoreKit product IDs in v1.
- $29 is the App Store app price, not an in-app purchase.
- If cloud render ships later, add StoreKit 2 auto-renewable products, restore, manage subscription, `appAccountToken`, and server validation.

**Exit:** no unused StoreKit code; App Store Connect has no missing IAP; review notes say local-only.

## 6. Own-footage policy — no runtime gate

**Product decision:** remove the runtime rights gate. Put the responsibility in the README, Terms & Conditions, and an always-on acknowledgment in Settings.

**Implementation**

- Check passes `attestation=True`; Clean layers are not blocked by `rights_not_attested`.
- Settings shows a read-only, always-checked “I own this footage or have permission to edit it” row with the watermark/logo warning.
- README and `TERMS.md` state the policy and the user’s responsibility.
- App Review notes explain that the app is for the user’s own footage or authorized footage, and that Clean is not a watermark-removal tool.
- Keep the rights policy code available for a future enterprise/client-review build, but do not gate the consumer v1 flow.

**Exit:** no `rights_not_attested` blocks in a fresh Check; Settings acknowledgment visible; README and T&C published.

## 7. Third-party notices + licenses

Rewrite `THIRD_PARTY_NOTICES.md` for DuckSuite only. Remove VibeCut, yt-dlp, xhs_get, voice engines, and cloud tenants.

**Bundle in `Contents/Resources/Licenses/`**

- Python (PSF license)
- FastAPI (MIT)
- Uvicorn (BSD-3-Clause)
- NumPy (BSD-3-Clause + bundled notices)
- Pillow (HPND)
- ONNX Runtime (MIT)
- LaMa model/code (verify exact license; Apache-2.0 expected)
- ffmpeg LGPL (LGPL text + source offer)
- Lucide icons (ISC) if still used
- Any Swift helper dependencies
- `THIRD_PARTY_NOTICES.md`

**Exit:** every shipped binary/model/data pack has a license entry and text; no VibeCut-era claims.

## 8. Window minimum

`DuckSuiteApp.swift` currently uses 1080×700. Design target is 1280×800.

- Set `.frame(minWidth: 1280, minHeight: 800)`.
- Verify at 1280×800: three-column layouts, queue table, preview stage, no clipped labels.
- Keep 200% zoom behavior.

**Exit:** app opens at 1280×800 or larger; no horizontal clipping.

## 9. Screenshot set

Capture after Clean P1 is closed.

- 1280×800
- 1440×900
- 2560×1600
- 2880×1800

Use a long 16:9 fixture, not the 46 s square test. Screens:

1. Welcome
2. Check scene-first handoff
3. Edit transcript
4. Clean Focus verified proof
5. Preview After proof
6. Render queue/output

No fake data. No black artifact. No 12/12 claim that the proof cannot support.

## 10. Review notes

Write `docs/duck/APP-REVIEW-NOTES.md`:

- Offline app; no account, no telemetry.
- Local Python sidecar bound to `127.0.0.1:0`; per-launch token; no LAN/remote access.
- Bundled Python, ONNX Runtime, LaMa, LGPL ffmpeg; no downloaded executable code.
- Optional model packs are data only, SHA-256 verified.
- Files selected with `NSOpenPanel`; copied into the sandbox.
- Own-footage attestation and watermark policy.
- No login needed for review.
- Cloud render: not in v1, or disclose if shipped.
- Clean is a local edit tool; users must own the footage.

## 11. Archive and TestFlight

- Select the team and “Automatically manage signing.”
- Set version and build.
- Product → Archive.
- Validate in Organizer.
- Upload to App Store Connect.
- Internal TestFlight on a clean Mac.
- Test: launch, import, Check, Edit, Clean, Preview, Render, Settings, no crash.
- Submit.

## Exit gate

- `xcodebuild archive` succeeds.
- Nested-code verification passes.
- LGPL ffmpeg verified.
- PrivacyInfo and App Privacy match.
- Own-footage attestation works.
- Clean P1 closed on the same test video.
- TestFlight clean-Mac pass.
- App Store review notes written.
