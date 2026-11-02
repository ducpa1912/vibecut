# URL ingest · phase 6 QA matrix

Release gate for the URL bar: link detection, download, cleanup, and handoff
to analysis. Rendering quality and audio engines are covered elsewhere.

Priorities:

- **P0** — release blocker. Data loss, security, legal exposure, or the common
  path is broken.
- **P1** — must fix before sign-off unless explicitly waived.
- **P2** — polish or environment-specific; record and schedule.

Record every run in the result log at the end. Attach API responses, job
history, server logs, and artifact listings as evidence.

## Entry criteria

Do not start the matrix until all of these are true:

- [ ] Clean build from the release commit; no uncommitted changes in the
      artifact.
- [ ] Python 3.11+ virtual environment; `python -m pip show yt-dlp` meets the
      `requirements.txt` floor.
- [ ] `ffmpeg -version` and `ffprobe -version` work; record the build.
- [ ] `python scripts/check_proprietary_deps.py` passes.
- [ ] Unit tests pass, including provider detection tests that expect
      `ytdlp` for non-RedNote links.
- [ ] Setup exposes provider mode (`auto` / `yt-dlp` / `XHS`) and the yt-dlp
      quality, codec, container, audio and cookie fields.
- [ ] The playlist picker flow is reachable from the URL bar.
- [ ] Baseline machine has no xhs_get, Node.js or Docker installed, unless a
      case explicitly enables it.
- [ ] Test URLs and accounts are available and permitted for testing. Do not
      use content you are not allowed to access.

## Standard checks

Apply these after every successful ingest unless a case says otherwise.

| ID | Check |
|---|---|
| SC-01 | Source file exists under `data/sources/`, is non-zero, and probes with a duration greater than zero. |
| SC-02 | Job moves to `queued` / analysis starts; no stuck `downloading` state. |
| SC-03 | History has one `ingest` entry with status `ok`, provider id, title, duration, size and redacted source URL. |
| SC-04 | No xhs_get, Node or Docker process was spawned for a yt-dlp ingest. |
| SC-05 | No cookie value, access token, `xsec_token`, or authorization header appears in `job.json`, history, or server logs. |
| SC-06 | No `.ingest-*` file remains in `data/sources/`, including `.part` and per-format fragments. |
| SC-07 | Display filename is sanitized; no path separators, control characters, or `..`. |
| SC-08 | Cancel endpoint returns `cancelled: false` for an already completed job and does not alter it. |

## Fixtures

| ID | Fixture |
|---|---|
| F-YT | Public YouTube video, 2–10 min, single video, audio present. |
| F-YT-PL | Public YouTube playlist with at least 3 playable videos, one unavailable item, and more than 200 entries in the large variant. |
| F-TT | Public TikTok video. |
| F-IG | Public Instagram reel. |
| F-X | Public X post containing a video. |
| F-RD | Public Reddit post containing a video. |
| F-VM | Public Vimeo video. |
| F-DIRECT | Direct HTTPS MP4 or WebM file. |
| F-PRIV | Private YouTube video owned by the test account. |
| F-AGE | Age-gated YouTube video. |
| F-MEMBER | Members-only or paid video. |
| F-DRM | DRM-protected stream from a legal test source. |
| F-RN | RedNote note with `xsec_token` and one video. |
| F-RN-BARE | RedNote `/explore/<id>` without `xsec_token`. |
| F-RN-SHORT | `xhslink.com` / `xhslink.cn` short link to a tokenized note. |
| F-RN-IMG | RedNote image-only note. |
| C-FILE | Valid Netscape `cookies.txt` for the test account. |
| C-BAD | Malformed or truncated `cookies.txt`. |
| C-EXP | Expired cookies for the test account. |
| S-XHS | Local xhs_get instance with a signed-in session. |
| D-TINY | 200 MB APFS volume or disk image for the disk-full case. |

## A. Provider detection

| ID | P | Steps | Expected |
|---|---|---|---|
| D-01 | P0 | Inspect F-YT with provider `auto`. | Response provider is `ytdlp`, label `yt-dlp`; no sidecar status required. |
| D-02 | P0 | Inspect F-TT with `auto`. | `ytdlp`. |
| D-03 | P0 | Inspect F-IG with `auto`. | `ytdlp`. |
| D-04 | P0 | Inspect F-X with `auto`. | `ytdlp`. |
| D-05 | P0 | Inspect F-RD with `auto`. | `ytdlp`. |
| D-06 | P0 | Inspect F-VM with `auto`. | `ytdlp`. |
| D-07 | P0 | Inspect F-RN with `auto`. | `xhs`, label `XHS / RedNote`. |
| D-08 | P1 | Inspect F-RN-SHORT with `auto`. | `xhs`. |
| D-09 | P0 | Inspect `https://xiaohongshu.com.evil.example/explore/x`. | `ytdlp`; not treated as RedNote. |
| D-10 | P0 | Inspect `https://rednote.com@evil.example/explore/x`. | `ytdlp`; host is `evil.example`, not RedNote. |
| D-12 | P2 | Set provider `ytdlp`, inspect F-RN. | `ytdlp`; unsupported or extractor error, no crash, no automatic XHS fallback. |
| D-13 | P0 | Submit `ftp://example.com/video.mp4`. | HTTP 400 before any provider call. |
| D-14 | P0 | Submit a URL with a space, backslash, or control character. | HTTP 400 before any provider call. |
| D-15 | P0 | Clear the XHS URL and inspect F-RN with `auto`. | Inline configuration error; no job created. |
| D-16 | P1 | Submit `provider: "youtube"`. | HTTP 400 unknown provider. |
| D-17 | P1 | Save provider `ytdlp`, inspect F-RN. | `ytdlp`; configured mode wins over auto detection. |
| D-18 | P2 | Inspect a URL with a 8 KB+ query string. | Clear "URL is too long" error, no crash. |

## C. Single-video ingest

Run SC-01 through SC-08 for every success case.

| ID | P | Steps | Expected |
|---|---|---|---|
| YT-01 | P0 | Inspect F-YT. | Title, duration, thumbnail and uploader present; provider `ytdlp`. |
| YT-02 | P0 | Create a job from F-YT at default quality. | One video downloaded; progress reaches 100%; probe and analysis start. |
| YT-03 | P1 | Repeat YT-02 with quality `720`. | Selected stream height is at most 720; job still probes. |
| YT-04 | P1 | Repeat YT-02 with codec `any` and container `mkv`. | Valid video produced; probe succeeds; no ffmpeg merge error. |
| TT-01 | P0 | Inspect and ingest F-TT. | Metadata and video import; watermark/no-watermark behavior is whatever the public page serves; no bypass. |
| TT-02 | P1 | Ingest F-TT with cookies `none`. | Success for a public video; no cookie store read. |
| IG-01 | P0 | Inspect and ingest F-IG with cookies `none`. | Public reel imports, or a clear sign-in error; no crash. |
| IG-02 | P1 | Repeat IG-01 with C-FILE. | If Instagram requires auth, the cookie path succeeds; otherwise the error is clear and actionable. |
| X-01 | P0 | Inspect and ingest F-X. | Video imports; post text is not treated as the filename. |
| X-02 | P1 | Ingest F-X with cookies `none`. | Public post succeeds or returns a clear auth error. |
| RD-01 | P0 | Inspect and ingest F-RD. | Video imports; Reddit host is not misrouted to XHS. |
| RD-02 | P1 | Ingest a Reddit post with an external YouTube link. | yt-dlp handles the resolved media or returns a clear unsupported error; no sidecar. |
| VM-01 | P0 | Inspect and ingest F-VM. | Metadata and video import. |
| VM-02 | P1 | Ingest a Vimeo password-protected video without a password. | Clear auth error; no bypass attempt. |
| DIRECT-01 | P1 | Ingest F-DIRECT. | Download succeeds; extension and probe are correct. |
| DIRECT-02 | P1 | Ingest an HTML page that is not a video. | Clear "not a video" or extractor error; no invalid source stored. |

## D. Playlist picker

| ID | P | Steps | Expected |
|---|---|---|---|
| PL-01 | P0 | Inspect F-YT-PL. | Response status `picker`, `needs_choice: true`, choices with title, duration, thumbnail, uploader, URL. |
| PL-02 | P0 | Choose one entry from PL-01 and create a job. | Exactly one video is downloaded; duration matches the chosen entry. |
| PL-03 | P0 | POST `/api/jobs/from-url` with the playlist URL directly. | HTTP 409; no job directory or source file is created. |
| PL-04 | P1 | Inspect a playlist with more than 200 entries. | At most 200 choices; no crash or unbounded response. |
| PL-05 | P1 | Inspect a playlist with one item. | Picker with one selectable item, or a single-video response; both must be usable. |
| PL-06 | P1 | Inspect an empty or fully unavailable playlist. | Clear "no selectable videos" error; no job. |
| PL-07 | P1 | Inspect a playlist where one entry has no URL. | Entry is filtered; remaining entries are selectable. |
| PL-08 | P2 | Open the picker, then cancel or navigate away. | No download starts and no job remains. |
| PL-09 | P0 | Verify the job request for a chosen entry carries that entry URL. | Download matches the selection, not the first item. |

## E. Cancel

| ID | P | Steps | Expected |
|---|---|---|---|
| CN-01 | P0 | Start a large F-YT download and cancel while progress is moving. | Job status `failed`, error "Download cancelled."; worker stops; history records the failed attempt. |
| CN-02 | P0 | Cancel immediately after the job is created, before bytes arrive. | No provider request or a promptly aborted request; job failed; no analysis. |
| CN-03 | P1 | Cancel with the network throttled so the download stalls. | Cancel is observed at the next callback; no permanent stuck job. |
| CN-04 | P1 | Press cancel twice. | Second call is safe; one history entry; no exception. |
| CN-05 | P1 | Cancel a completed ingest. | `cancelled: false`; completed job and renders are untouched. |
| CN-06 | P0 | After CN-01/CN-02, inspect `data/sources/`. | No `.ingest-*`, `.part`, or format-fragment files remain. |
| CN-07 | P1 | Restart the app while a download is running. | Interrupted job is marked failed on restart; no zombie worker; temp files cleaned. |
| CN-08 | P1 | Cancel during XHS polling. | Polling stops; job failed; xhs_get is not polled again. |

## F. Auth, private, and age-gated

| ID | P | Steps | Expected |
|---|---|---|---|
| AU-01 | P0 | Ingest F-PRIV with cookies `none`. | "This video is private." No job source, no bypass. |
| AU-02 | P1 | Ingest F-PRIV with owner C-FILE. | Authorized download succeeds and is recorded. |
| AU-03 | P0 | Ingest F-AGE with cookies `none`. | Age-gate message with a cookie hint; no bypass. |
| AU-04 | P1 | Ingest F-AGE with an age-verified C-FILE. | Download succeeds when the account is allowed. |
| AU-05 | P0 | Ingest F-MEMBER with cookies `none`. | Clear membership/login error; no paywall bypass. |
| AU-06 | P0 | Ingest F-DRM. | No decryption or key fetching occurs. The result is a clear unsupported/DRM/probe error, never a playable bypass or a retry loop. |
| AU-07 | P2 | Ingest a region-locked video. | "Region-restricted" or extractor error; no geo bypass. |
| AU-08 | P1 | Ingest a deleted video. | "The video was not found." No job. |
| AU-09 | P0 | Inspect all error text and history for credential leakage. | URL tokens are `[redacted]`; no cookies or authorization values. |
| AU-10 | P1 | Submit a URL containing `user:pass@`. | Credentials are rejected or fully redacted; they never reach history or logs. |

## G. Cookies

| ID | P | Steps | Expected |
|---|---|---|---|
| CK-01 | P0 | Ingest F-YT with cookies `none` (default). | No cookie file or browser store is opened; public video succeeds. |
| CK-02 | P1 | Set `file` + C-FILE; ingest F-AGE. | Authorized download succeeds. |
| CK-03 | P0 | Set `file` with an empty path. | "Choose a cookies.txt file in Setup, or use browser cookies." No job. |
| CK-04 | P0 | Set `file` with a missing path. | "The configured yt-dlp cookies.txt file does not exist." No job. |
| CK-05 | P1 | Set `file` with C-BAD. | yt-dlp error is surfaced clearly; no crash; no partial source. |
| CK-06 | P1 | Set `file` with C-EXP. | Login/auth error with a clear hint. |
| CK-07 | P1 | Set `browser: safari`; ingest F-AGE. | Works, or a clear macOS permission error; close Safari if the store is locked. |
| CK-08 | P1 | Set `browser: chrome`; ingest F-AGE. | Works, or a clear Keychain/locked-profile error. |
| CK-09 | P2 | Set `browser: firefox`; ingest F-AGE with Firefox present. | Works or clear error. |
| CK-10 | P2 | Set an unsupported browser name. | Clear error naming the browser; no crash. |
| CK-11 | P0 | After CK-02, inspect `data/`, `job.json`, history and logs. | Cookie file is not copied; no cookie value is stored or logged. |
| CK-12 | P1 | Use the XHS cookie handoff. | Cookie reaches xhs_get; it is not saved to VibeCut settings or secrets. |

## H. Disk, network, and failure handling

| ID | P | Steps | Expected |
|---|---|---|---|
| FL-01 | P0 | Point `VIBECUT_DATA` at D-TINY and ingest a video larger than the volume. | Job fails with a disk-space error; app stays responsive; no corrupt source is analyzed. |
| FL-02 | P0 | After FL-01, inspect `data/sources/`. | Partial `.part` and fragment files are removed, not left to fill the disk. |
| FL-03 | P0 | Make `data/` read-only and ingest. | Clear permission error; no job stuck in `downloading`. |
| FL-04 | P1 | Disconnect the network mid-download. | Retries are bounded; job fails with a network error; temp files cleaned. |
| FL-05 | P1 | Use a URL that returns HTTP 403 or 429. | Clear rate-limit/auth error; no infinite retry. |
| FL-06 | P1 | Truncate the downloaded file, then let probe run. | Probe failure is reported; job failed; no analysis on the broken file. |
| FL-07 | P1 | Remove `ffmpeg` from `PATH` and ingest. | Clear ffmpeg/probe error; no crash; no job queued. |
| FL-08 | P1 | Start three ingests at once. | Separate job ids and progress; no cross-talk; all complete or fail independently. |
| FL-09 | P1 | Restart the app with a queued analysis after a completed ingest. | Completed source stays; interrupted work is marked failed; no duplicate job. |
| FL-10 | P2 | Ingest a file with a very long title or Unicode filename. | Sanitized display name; source remains valid; no path traversal. |
| FL-11 | P0 | Check server logs after every failure case. | No stack trace with tokens, cookies, or full local paths exposed to the UI. |

## I. No Docker / Node, fresh Mac

| ID | P | Steps | Expected |
|---|---|---|---|
| EN-01 | P0 | On a clean user account, install only Python 3.11, ffmpeg and `requirements.txt`. | App starts; YouTube/TikTok ingest works. |
| EN-02 | P0 | Confirm `node`, `docker`, `xhs_get` are absent. | No install prompt appears for common URLs; no failure caused by their absence. |
| EN-04 | P1 | Open Setup with no xhs_get instance. | XHS shows not configured; non-RedNote ingest still works. |
| EN-05 | P1 | Press every Setup test button with the xhs_get sidecar absent. | Inline unavailable messages; no 500, no crash, no stuck spinner. |
| EN-06 | P1 | Build and run the Docker image; ingest F-YT. | yt-dlp works in the container; no Node required. Apple-only analysis features may fall back. |
| EN-07 | P0 | Remove ffmpeg from `PATH` on a fresh account. | Clear install error; app does not crash. |
| EN-08 | P1 | Run under Python 3.12 and 3.13 venvs. | Import, inspect and ingest work; no syntax or dependency break. |
| EN-09 | P1 | Run on macOS 14, 15 and 26. | URL ingest works; Apple framework differences do not affect download. |
| EN-10 | P1 | Launch a quarantined/downloaded app bundle on a fresh Mac. | Gatekeeper flow is documented; no hidden dependency on the build machine. |
| EN-11 | P2 | Run with no network. | Clear network error; no endless retry. |
| EN-12 | P2 | Run from a standard (non-admin) macOS user. | `data/`, caches and temp paths are writable; no permission prompt loop. |
| EN-13 | P2 | Run on Apple Silicon and Intel if supported. | Both architectures ingest and probe. Record any unsupported combination. |

## J. RedNote / xhs_get

| ID | P | Steps | Expected |
|---|---|---|---|
| RN-01 | P0 | Inspect F-RN with S-XHS configured. | Provider `xhs`; title and session state; no token in the response. |
| RN-02 | P0 | Create a job from F-RN. | Video deliverable imported; SC-01..SC-08 pass. |
| RN-03 | P0 | Inspect F-RN-BARE. | Warning about missing `xsec_token`; no job created. |
| RN-04 | P1 | Ingest F-RN-SHORT. | Short link resolves to a tokenized note and imports. |
| RN-05 | P1 | Ingest F-RN-IMG. | "Image only" or no-video error; no empty source; no job stuck. |
| RN-06 | P1 | Start with no xhs_get cookie. | Setup shows needs-cookie; **Open sign-in** and handoff work. |
| RN-07 | P1 | Expire the xhs_get session, then ingest. | Error surfaced in Setup, progress and history; re-sign-in fixes it. |
| RN-08 | P1 | Enable friends mode with no token, then with a valid token. | "Needs token" first; token unlocks the job. Invalid token gives a token error. |
| RN-09 | P1 | Stop xhs_get and inspect F-RN. | Inline service-down error; no job; app stays responsive. |
| RN-10 | P1 | Configure an invalid XHS URL. | Setup validation error; no request sent. |
| RN-11 | P2 | Toggle `no_record` and ingest the same note twice. | Fresh-download behavior matches the flag. |
| RN-12 | P2 | Set `xhs_interval` to a higher value. | Polling respects the interval; server load drops; no premature timeout. |
| RN-13 | P1 | Cancel while polling. | Polling stops immediately; job failed; history recorded once. |
| RN-14 | P1 | Ingest a note with multiple deliverables. | First video deliverable is imported; images are skipped; no partial merge. |
| RN-15 | P0 | After cookie handoff, inspect settings, secrets, history and logs. | Cookie is not persisted in VibeCut; no value appears in logs. |
| RN-16 | P0 | Inspect job/history source URL. | `xsec_token` and related share tokens are `[redacted]`. |
| RN-17 | P1 | Call the settings API while a token is saved. | Token is masked or absent; never returned in clear text. |
| RN-18 | P2 | Use a very long RedNote title. | Display filename is sanitized and bounded; source remains valid. |

## K. Security and legal boundary

| ID | P | Steps | Expected |
|---|---|---|---|
| LG-02 | P0 | List the release artifact. | No xhs_get, Node, `node_modules`, or copied sidecar source. |
| LG-03 | P0 | Run `python scripts/check_proprietary_deps.py` in the clean release venv. | Exit 0; no GPL/AGPL direct dependency or sidecar import. |
| LG-04 | P0 | Try a private, paid, or DRM-protected link with cookies. | Still refused where the account is not authorized; no decryption or bypass is attempted. |
| LG-05 | P1 | Submit an unsupported site. | Clear unsupported error; no hidden sidecar call. |
| LG-07 | P1 | Grep the artifact for license files. | `THIRD_PARTY_NOTICES.md`, yt-dlp Unlicense, and the proprietary EULA are present. |

## Result log

| Run | Commit | Date | macOS | Python | ffmpeg | yt-dlp | Sidecars | Tester |
|---|---|---|---|---|---|---|---|---|
| 1 | working tree | 2026-10-25 | local dev | 3.11.7 | 9.0.2 | 2026.10.21 | xhs_get only | agent + unit tests |

Per-case result:

| Case | Result | Evidence / defect |
|---|---|---|
| D-01 | ✅ pass | live YouTube inspect returned provider `ytdlp`, title and duration |
| YT-02 | ✅ pass | live 19s YouTube download → probe → analysis ready; source name `Me at the zoo.mp4` |
| YT-03 | ✅ pass | live provider at 360p produced H.264 MP4 |
| PL-01 | ✅ pass | live playlist returned 182 choices with thumbnails |
| PL-02 | ✅ pass (mocked) | selected-entry URL is passed to yt-dlp download |
| PL-03 | ✅ pass | playlist POST returns 409 before job creation |
| CN-01 | ✅ pass (mocked) | cancel marks failed, cleans partial, records one history entry |
| AU-01 | ✅ pass | Settings save/validation and yt-dlp status verified |
| CK-01 | ✅ pass | browser cookies / cookies.txt option mapping tested |
| FL-01 | ✅ pass (mocked) | fallback both-fail and cancellation paths |
| RN-16 | ✅ pass | success job/history/meta token redaction test |
| LG-03 | ✅ pass | `scripts/check_proprietary_deps.py` exits 0 |
| D-02..D-06 | ⏳ pending | TikTok/Instagram/X/Reddit/Vimeo live fixtures not available locally |
| RN-01..RN-15 | ⏳ pending | RedNote live one-note matrix needs a signed-in sidecar |
| EN-01..EN-13 | ⏳ pending | fresh Mac / Docker / ffmpeg-missing matrix not run in this session |

Copy rows as needed; every executed case needs an entry.

## Exit criteria

- All P0 cases pass.
- No open P1 defect involving data loss, disk leaks, credential exposure,
  wrong-provider routing, or license boundary.
- The dependency audit passes in the clean release environment.
- `docs/shared/licensing.md` notices and the release checklist are complete.
- The release artifact contains no sidecar source or binaries.
- Evidence is attached to the release ticket.
