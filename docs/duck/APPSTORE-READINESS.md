# DuckSuite — App Store readiness

Date: 2026-11-07  
Status: not ready to submit

## Short answer: where is the DMG?

There is **no DMG**. That is intentional.

- Phase 1 is **Mac App Store only**; direct DMG distribution is explicitly out of scope in [DISTRIBUTION.md](DISTRIBUTION.md).
- The build output is `build/DuckSuite.app`, a **development app** signed ad hoc.
- App Store delivery is an `.xcarchive` upload through Xcode / Transporter, not a DMG.
- A DMG only returns if App Review rejects the bundled sidecar and a direct-distribution decision is made. That path needs Developer ID signing, notarization, and stapling.

## Current artifact

```text
build/DuckSuite.app
  ad-hoc signed
  TeamIdentifier: not set
  no distribution provisioning profile
  no PrivacyInfo.xcprivacy
  no app icon
  no bundled ffmpeg/ffprobe
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
| ffmpeg | LGPL ffmpeg/ffprobe bundled in `Contents/Helpers` | Homebrew build is GPL with libx264/x265; App Store and license blocker |
| Privacy | `PrivacyInfo.xcprivacy`, privacy policy URL, App Privacy answers | Required for submission |
| Icon | `Assets.xcassets` with 1024 px AppIcon; `CFBundleIconName` | App Store requires an icon |
| StoreKit | Decide: no cloud in v1, or configure Render subscription products and restore | Current `StoreManager` is unused scaffold |
| Metadata | Description, keywords, category, age rating, support URL, screenshots | Required listing |
| Review notes | Local server, bundled Python, no downloaded code, own-footage clean | High review-risk area |
| Media auth | Frontend uses `?t=` for images/video; distribution doc says no query-string tokens | Security policy mismatch; move media reads to the HttpOnly cookie |
| Own-footage | Runtime gate removed by product decision; always-on acknowledgment in Settings; policy in README and T&C | Legal/review copy must ship; no runtime gate |
| Clean quality | Scene 01 large-title artifact; some proofs still contain text | “Clean” is the key selling point; do not submit with a P1 proof |
| TestFlight | No archive, upload, or clean-Mac test | Release gate |

## P1 execution plan

See [APPSTORE-P1-PLAN.md](APPSTORE-P1-PLAN.md) for owners, order, commands, and exit criteria.

## Missing — P1

- Third-party notices are still VibeCut-era and mention yt-dlp, xhs_get, voice engines, and VibeCut. Rewrite for DuckSuite: FastAPI, Uvicorn, NumPy, Pillow, ONNX Runtime, LaMa, Python, ffmpeg LGPL, Swift helpers.
- Bundle exact license texts for every shipped component.
- `PrivacyInfo.xcprivacy` required-reason APIs: file timestamp, disk space, UserDefaults if used.
- Nested code signing: Python binary, `duckcore`, Swift helpers, ONNX runtime dylibs; archive signing must cover all.
- `CFBundleVersion` increment and release version scheme.
- App Store screenshots at 1280×800, 1440×900, 2560×1600, 2880×1800; long 16:9 fixture.
- Menu commands and window minimum: Swift window is 1080×700; design target is 1280×800.
- App Store review notes explaining that the local server binds `127.0.0.1:0` and uses a per-launch token.

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
