# DuckSuite — App Store readiness

Date: 2026-11-08  
Status: user-test-02 pass; signing and store URLs still blocked

## Short answer: where is the DMG?

There is **no DMG**. That is intentional.

- Phase 1 is **Mac App Store only**; direct DMG distribution is explicitly out of scope in [DISTRIBUTION.md](DISTRIBUTION.md).
- The build output is `build/DuckSuite.app`, a **development app** signed ad hoc.
- App Store delivery is an `.xcarchive` upload through Xcode / Transporter, not a DMG.
- A DMG only returns if App Review rejects the bundled sidecar and a direct-distribution decision is made. That path needs Developer ID signing, notarization, and stapling.

## Current artifact

```text
build/DuckSuite-Xcode.app
  ad-hoc signed
  TeamIdentifier: not set
  no distribution provisioning profile
  PrivacyInfo.xcprivacy present
  AppIcon present (CFBundleIconName = AppIcon)
  LGPL ffmpeg + ffprobe bundled
  licenses bundled at Contents/Resources/Licenses
```

Verified: the bundled app launches, its local core serves the UI, and JS/CSS return 200 in the sandbox.

## How to apply

1. **Apple Developer Program.** Enroll the legal entity or individual; pay the annual fee.
2. **Register the App ID.** Bundle ID `com.ducksuite.app` in Certificates, Identifiers & Profiles.
3. **Create the App Store Connect record.**
   - Platform: macOS
   - Name: DuckSuite
   - Primary language
   - Bundle ID
   - SKU
   - User access
4. **Set pricing and availability.**
   - $29 one-time app price.
   - Optional Render subscription: either configure StoreKit 2 products or remove the unused scaffold for v1.
5. **Complete App Privacy.**
   - Privacy policy URL and support URL.
   - App Privacy label: local app collects nothing, unless optional cloud render ships.
   - `PrivacyInfo.xcprivacy` inside the bundle.
6. **Use full Xcode.**
   - Xcode 27.2 is installed at `/Applications/Xcode.app`.
   - XcodeGen 2.46 is installed.
   - `xcodebuild -version` works with `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.
   - A full local build and an unsigned archive now succeed.
   - App Store signing still needs an Apple Development / App Store identity and a `DEVELOPMENT_TEAM`.
7. **Fix the distribution blockers below.**
   - LGPL ffmpeg, app icon, privacy manifest, signed nested code, StoreKit decision, review notes.
8. **Archive and upload.**
   - Product → Archive in Xcode.
   - Organizer → Distribute App → App Store Connect → Upload.
   - Or `xcodebuild archive` + `-exportArchive` with App Store Connect export options.
9. **TestFlight.**
   - Internal testers first.
   - Clean-Mac install, import, Check, Edit, Clean, Preview, Render, purchase/restore if subscriptions ship.
10. **Submit for review.**
    - Screenshots, description, keywords, age rating, content rights.
    - Review notes: local loopback server, bundled Python, no downloaded executable code, own-footage attestation.
11. **Respond to review.** Expect questions about the local server and bundled interpreter.

Notarization is **not** part of the Mac App Store path. It is required only for a direct-download DMG.

## Missing — P0 release blockers

| Area | Missing | Why it blocks |
|---|---|---|
| Toolchain | Xcode project generation | Ready: Xcode 27.2 + XcodeGen 2.46; unsigned build/archive pass |
| Signing | Distribution certificate, App Store provisioning profile, team ID | Current build is ad-hoc; unsigned archive has empty Team |
| ffmpeg | Ready: FFmpeg 7.1.1 LGPL arm64, `--disable-gpl`, VideoToolbox H.264, zlib, no network | Rebuild with `scripts/build-ffmpeg-lgpl.sh` |
| Privacy | Ready: `PrivacyInfo.xcprivacy` in bundle; policy URL and App Privacy answers still to publish | Required for submission |
| Icon | Ready: `CFBundleIconName = AppIcon`, `AppIcon.icns` in Resources | App Store requires an icon |
| StoreKit | Ready: no IAP scaffold in v1; price comes from App Store Connect | No subscription in v1 |
| Metadata | Description, keywords, category, age rating, support URL, screenshots | Required listing |
| Review notes | Local server, bundled Python, no downloaded code, own-footage clean | High review-risk area |
| Media auth | Frontend uses `?t=` for images/video; distribution doc says no query-string tokens | Security policy mismatch; move media reads to the HttpOnly cookie |
| Own-footage | Runtime gate removed by product decision; always-on acknowledgment in Settings; policy in README and T&C | Legal/review copy must ship; no runtime gate |
| Clean quality | Pass on the fixed fixture: scene 01 3.5 s, scene 03, scene 07 clean; proof/render MAD 2.30 | Re-run on a licensed 16:9 demo before submission |
| TestFlight | No archive, upload, or clean-Mac test | Release gate |

## P1 execution plan

See [APPSTORE-P1-PLAN.md](APPSTORE-P1-PLAN.md) for owners, order, commands, and exit criteria.

## Missing — P1

- Third-party notices rewritten for DuckSuite; license texts are in `licenses/` and `Contents/Resources/Licenses/`.
- `PrivacyInfo.xcprivacy` declares no tracking and no collected data; file timestamp and disk space reasons are declared.
- Nested code signing: still needs a real identity. The archive is unsigned.
- `CFBundleVersion` is 1; bump before each upload.
- Screenshots captured at 1280×800 and 1440×900, saved at 2× (2560×1600 and 2880×1800). Source footage needs a rights check before submission.
- Menu commands and window minimum: window minimum is 1280×800.
- Review notes written in `APP-REVIEW-NOTES.md`; metadata in `APPSTORE-METADATA.md`.
- Clean P1 passes on the fixed fixture. See `docs/teams/clean-quality/loop-05.md` and `docs/teams/user-test-02.md`.

## Missing — P2

- Queue archive/clear.
- App icon polish.
- Performance budget on M1 8 GB.
- Cloud render product IDs and `appAccountToken` if subscriptions ship.
- Privacy policy content for model packs and offline processing.
- Clean proof review gate in marketing.

## Current Xcode artifacts

```text
build/DuckSuite-Xcode.app      ad-hoc signed, local run
build/DuckSuite.xcarchive      unsigned archive, arm64
```

The archive contains the full app: Swift binary, `duckcore`, static UI, helpers, and LaMa model.

Unsigned archive command:

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild   -project mac/DuckSuite/DuckSuite.xcodeproj -scheme DuckSuite   -configuration Release -archivePath build/DuckSuite.xcarchive   CODE_SIGNING_ALLOWED=NO archive
```

## What can be done before signing

- Add `PrivacyInfo.xcprivacy` and copy it into the bundle.
- Add the app icon asset catalog.
- Replace query-string media tokens with the cookie.
- Rewrite third-party notices for DuckSuite.
- Build an LGPL ffmpeg binary.
- Fix the clean P1 and capture verified proof.
- Prepare App Store screenshots and review notes.
- Add own-footage attestation to the UI.

## Gate

Do not submit until:

- `xcodebuild archive` succeeds.
- Archive validates in Organizer.
- TestFlight installs on a clean Mac.
- Sandbox, local server, import, Check, Edit, Clean, Preview, Render pass.
- Clean P1 is closed on the test video.
- Privacy manifest and App Privacy match.
- LGPL ffmpeg is bundled with notices.
- Review notes are written.
