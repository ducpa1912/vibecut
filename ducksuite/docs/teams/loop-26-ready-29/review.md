# Loop 26 review — $29 readiness (PLAN loop 8, REQ-20261111-02; REQ-20261115-02 P4)

Built by the sub-leader on 2026-11-16 at the founder's word ("ok you fix it yourself") after the
OpenCode run stopped on a provider 503 (session `ses_e22b449f…`, last message `idle · failed ·
Service temporarily unavailable`). OpenCode's partial tree was read and kept only where it held; the
JS import heuristic and the unauthenticated licence link were replaced (reasons below).

**Result:** 326 tests pass, `node --check static/duck/app.js` clean.
`textfill.VERSION` stays 17; no fill pixels change; the next render is not cold.

## 1. Pack integrity — pass, with one stated gap

- The 98 % rule is gone. Every file must match its **exact** size, at download and for "installed".
- Every file is checked against the publisher's digest **where the publisher gives one**, once,
  after download (not on every Settings open). A mismatch or short file is deleted with its `.part`
  and the pack reads "The download was damaged. Try again." A network failure reads "The download
  stopped. Check the connection and try again."; the technical text stays in `detail`.
- Hugging Face URLs are pinned to the revision whose hashes were read, so the file behind a URL
  cannot change under the hash.

| File | Size (bytes) | Digest | Source read 2026-11-16 |
|---|---|---|---|
| `lama_fp32.onnx` | 208 044 816 | SHA-256 `1faef530…3eb68d6` | `huggingface.co/api/models/Carve/LaMa-ONNX/tree/main` (LFS oid), rev `c3c0c9e4` |
| `weights.safetensors` (Whisper) | 1 613 977 612 | SHA-256 `951ed3fc…3e7f8a6` | `huggingface.co/api/models/mlx-community/whisper-large-v3-turbo/tree/main` (LFS oid), rev `a4aaeec0` |
| `config.json` (Whisper) | 268 | git blob SHA-1 `6ac9a52a…3e` | same API; not an LFS file, so HF publishes only the git blob id. Checked as `sha1("blob 268\0"+bytes)` |
| `kokoro-v1.0.onnx` | 325 532 387 | **none published** | `api.github.com/repos/thewh1teagle/kokoro-onnx/releases/tags/model-files-v1.0`: asset `digest` is null, the release notes list no hash; upstream `taylorchu/kokoro-onnx` v0.2.0 also null |
| `voices-v1.0.bin` | 28 214 398 | **none published** | same release |

**Fail (stated, not hidden):** the two Kokoro files have exact-size checks only. No digest was made
from our own download. A publisher hash, or a mirror that publishes one, closes it.

Checks run: all five pinned URLs answer 200 with exactly these sizes (HEAD), and the real
268-byte `config.json` passes its git SHA-1. The large files were **not** downloaded and hashed.

## 2. FFmpeg source offer — pass; one founder action

- `duckcore/licenses.py` holds the offer; `Licenses/FFmpeg-SOURCE.txt` is the same text (a test keeps
  them equal) and is copied into the app by `build-duck-dev.sh` with the other licences.
- The configure line is compared with `scripts/build-ffmpeg-lgpl.sh` by a test, as is the version.
- ffmpeg.org publishes a GPG signature per release, not a SHA-256; the offer says so and points to
  the `.asc` file. No digest was invented.
- Settings → Storage column: "FFmpeg 7.1.1 · LGPL 2.1 · **Source offer**" opens the text in a modal
  with **Back to Settings**. Served through `/api/licenses/ffmpeg-source` with the bearer token
  (OpenCode's plain `<a href>` would have answered 401 in the app, since a link carries no token).
- Seen live on the scratch root (port 8811): the row is 45 px; the modal shows the full text and the
  configure line.
- **Founder:** replace `<contact address>` in `duckcore/licenses.py` (and re-run the file write) before
  any distribution. No personal address was put in the repo.

## 3. Whisper options — research only, no code change

| MLX model (mlx-community) | Weights | vs today | FLEURS vi WER | CV9 vi WER |
|---|---|---|---|---|
| whisper-large-v3-turbo (today) | 1.61 GB | — | not published | not published |
| whisper-large-v3-turbo-8bit | 0.86 GB | 54 % | not published | not published |
| whisper-large-v3-turbo-4bit | 0.46 GB | 29 % | not published | not published |
| whisper-medium-mlx | 1.52 GB | 94 % | 12.7 | 24.4 |
| whisper-medium-mlx-q4 | 0.51 GB | 32 % | (medium, before quantising) | |
| whisper-small-mlx | 0.48 GB | 30 % | 21.2 | 33.3 |
| whisper-small-mlx-q4 | 0.20 GB | 12 % | (small, before quantising) | |
| (reference) large-v2 | — | — | 10.3 | 18.2 |

Sizes: Hugging Face tree API for each repo (sum of `.npz`/`.safetensors`), 2026-11-16. WER: Radford
et al., "Robust Speech Recognition via Large-Scale Weak Supervision", arXiv 2212.04356, appendix
Table 13 (FLEURS) and the Common Voice 9 table; read through a text extract of the PDF, so spot-check
the numbers before quoting them outside the team. Apple-silicon speed: **not published** by the model
publishers; not measured here (no audio may be generated or downloaded).

**Recommendation:** keep the pack as it is for now. The only option that is much smaller and plausibly
as accurate is `large-v3-turbo-4bit` (0.46 GB, 29 %), but no Vietnamese figure is published for any
turbo or quantised model, and `small` doubles the error (21.2 vs 10.3). Next step needs the founder: a
short Vietnamese clip they own, transcribed by today's pack and by turbo-4bit, word error and time
compared. Note: the 4/8-bit turbo repos name their file `model.safetensors`; confirm `mlx_whisper`
loads that name before any switch.

## 4. Fill repair line — pass

`fillRepairText(kind)` gives the next step, naming no model:
- built-in engine: "Next step: reinstall DuckSuite to restore the built-in fill files." (Edit status
  line and the Settings note);
- CPU pack: "Next step: press Remove on the CPU fill engine, then Download it again." (beside its
  pack error);
- your fill model: "Next step: press Clear on Your fill model, then Choose the folder again." (under
  a Not usable row; the row itself keeps its height).
Node test per case.

## 5. Import error copy — pass

`duckcore/import_errors.py` maps technical text to one creator sentence with a next step; the
technical text goes to the `duckcore.import` log and, for jobs, a `detail` field. Applied in the core
(so the browser import, the append jobs and the native Swift import all show it): `stage_upload`,
`/api/projects`, `/api/projects/upload`, all four append routes, the append job, the append read,
and the Check failure `message` (`error` keeps the technical text).

| Technical | Creator sentence (start) |
|---|---|
| no space left / Errno 28 / disk full | There is not enough free disk space… |
| `… is not installed or bundled` | DuckSuite is missing its video tools. Reinstall… |
| `ffmpeg frame read failed`, `Could not read a frame…` | DuckSuite could not read the frames of this video. Export it again as H.264 or HEVC MP4… |
| moov atom not found / Invalid data found / end of file / truncated | This video file is incomplete or damaged… |
| Decoder … not found / unknown or unsupported codec | This video uses a format DuckSuite cannot read… |
| does not contain any stream / no video stream | This file has no video picture… |
| does not match the master streams | This clip's picture size, frame rate or audio differs… |
| ffmpeg could not join the videos | This clip could not be joined to the project… |
| could not read the video durations / has no duration | DuckSuite could not read how long this video is… |
| Scene detection failed | DuckSuite could not find the scenes in this video… |
| The Check result is unreadable | This project's Check result is damaged. Run Check again… |
| The upload failed | The video could not be copied into DuckSuite. Check the free disk space… |
| The read could not start | DuckSuite could not start reading the new video… |
| anything else technical (ffmpeg, Errno, Traceback, paths, `[x @ 0x…]`, several lines) | This video could not be imported. Export it again as H.264 or HEVC MP4 and try again. |

Plain messages already written for a creator ("Use MP4, MOV or M4V.", "Wait for Check to finish
first.") pass through unchanged. OpenCode's JS keyword match was removed: it turned those plain
messages into the vague fallback. Tests: 17 mapped messages, 4 pass-throughs, 4 fallbacks, the
upload route, the append job.

## Follow-up review fixes

Installed files now run the same publisher-digest check as downloads. Technical
permission and missing-file errors map to creator copy. Browser and native bridge
import errors log technical text while showing creator copy. The sparse-file pack
test now correctly expects rejection.

Final suite: 326 passed, 5 existing TorchScript warnings.

## What got worse

- A pack download is ≤ 2 % stricter: a file that is a few bytes off now fails where it passed.
- The Whisper and LaMa packs are pinned to today's revisions; a publisher update needs a new hash
  and URL in `packs.py`.
- A Check failure now shows the plain sentence; the exact ffmpeg text is only in the log and the
  `error` field.

## Not tested

- A full real download of any pack (1.6 GB / 325 MB / 208 MB) through the app.
- The native Swift import path end to end (it shows the core's message; not clicked).
- The source-offer text inside a built `.app` (served from Python; the file copy is unchanged).
- Whisper speed or accuracy on any audio.
- The microphone step stays a founder hand test (`founder-test-all.md`, loop 23).
