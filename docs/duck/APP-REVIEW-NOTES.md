# App Store review notes

## App

- **Name:** DuckSuite
- **Bundle ID:** `com.ducksuite.app`
- **Version:** 1.0 (build 1)
- **Minimum OS:** macOS 26.0
- **Architectures:** arm64
- **Category:** Photo & Video
- **Price:** $29.00, one-time
- **In-app purchases:** none
- **Account:** none
- **Network:** none beyond the loopback interface

## What the app does

DuckSuite turns one long talking-head video into short vertical clips. It finds
scene cuts, transcribes speech, finds burned-in text, proposes story segments,
and removes old text from the picture. Everything runs on the Mac. There is no
upload, no account, no telemetry, and no cloud service.

The six screens are Welcome, Check, Edit, Clean Focus, Preview, and Render.
Check publishes scene cuts first and opens Edit while transcript, text
detection, and stories continue in the background.

## How to review

1. Launch DuckSuite. No login or license key is required.
2. Click **Choose Video** or drag an MP4, MOV, or M4V file onto Welcome. Use any
   1080p video with burned-in text and speech if possible.
3. Wait for Check. Scene cuts appear first; the Editor opens automatically.
4. In Edit, review the proof rows, transcript, and clean layers.
5. Open **Clean Focus**. Choose Fill, Blur, or Off for a scene. Fill is the
   default when the local LaMa model is confident.
6. Open **Preview**. Clean proofs are generated scene by scene. The blur is a
   temporary processing placeholder and is never used in a final render.
7. Open **Render**. Choose 24 or 30 fps and start a render. The MP4 is written
   to the app's local `exports` folder and revealed in Finder.

A full 46-second 1080 × 1080 test video produces twelve scenes in roughly one
minute on an M-series Mac. First launch takes a few seconds while the local
Python core starts.

## Local core

The Swift app starts a bundled Python executable (`Contents/Resources/duckcore`)
on `127.0.0.1` with a random per-launch bearer token. The token is passed to the
web view and is required for every API call. The server binds to loopback only,
and the bundle contains no remote endpoints. The `network.client` and
`network.server` entitlements exist only for this loopback connection.

Projects, frames, caches, and exports live in the app container:

```text
~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite
```

Deleting the app removes the container and all user media.

## Sandbox and file access

The app is sandboxed. A video is imported through `NSOpenPanel` and copied into
the container. Exports are revealed with `NSWorkspace` after the user asks.

## Privacy

- No data is collected.
- No tracking, advertising, or analytics SDK is present.
- No account, email, phone number, or device identifier is requested.
- `PrivacyInfo.xcprivacy` declares no collected data and no tracking.
- The only required-reason APIs declared are file timestamps and disk space,
  used by the bundled media engine to read and write local files.

## Encryption

`ITSAppUsesNonExemptEncryption` is `false`. The app uses only local loopback
HTTP with a random token; it does not provide encrypted communications to a
remote service.

## Rights and content

DuckSuite does not download media and does not include a URL importer. The user
supplies the video and confirms they have the rights to edit it. The
acknowledgment is always visible in Settings, and the full policy is in the
repository `README.md` and `TERMS.md`.

## Known limitations for v1

- 1080p output only.
- 24 or 30 fps output.
- No colour grading, LUTs, or publish kit.
- Apple silicon and macOS 26 or later only.
- The clean model fills detected text lines. A low-confidence line is shown for
  review rather than rendered silently.

## Contact

Support and privacy contact: **TODO before submission**.

## Build artifacts

- Signed archive: `build/DuckSuite.xcarchive` (needs the team identity).
- Local app: `build/DuckSuite-Xcode.app`.
- Screenshots: `docs/appstore/screenshots/`.
