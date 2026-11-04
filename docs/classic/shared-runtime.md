# Classic's own runtime

Classic does not depend on another lane's checkout. Studio is moving its shared
code into `features/` and `core/` on the `studio` branch and may remove
`rights.py`. None of that changes Classic, because Classic keeps its own copy.

Three separate things, on purpose:

- **Code is pinned.** Classic's copy of the backend code protects it from Studio's code move.
- **The machine runtime is shared.** Python, packages, Whisper, Argos, AI fill models and
  Playwright stay shared across lanes. This is the founder's decision for development
  (2026-11-05): no per-lane copies.
- **Media is the lane's own.** Test videos, recordings, cloned voices and the music
  library live in this checkout's gitignored `data/` folder.

## The rule

- Classic's copy of the shared backend is pinned in `classic_runtime/manifest.json`:
  75 files with path, sha256, source and version. The baseline is `classic` `2f385a2`.
- `tests/test_classic_runtime_pin.py` fails when a pinned file changes without the
  manifest, when a new runtime file is not pinned, or when Classic imports
  `features.*` or `core.*` or names another lane's folder.
- A Studio change reaches Classic only as a deliberate port: change the file, add a
  Classic test, and run the command below in the same commit.

```bash
scripts/pin-classic-runtime.py --source "studio abc1234: why" render.py
```

`routes_classic.py` and `static/classic/**` are Classic's own and are not pinned.
`rights.py` and the Classic rights flow stay as they are.

## Scripts that stand on their own

| Script | How it stands alone |
|---|---|
| `scripts/release.sh` | Checks signatures from the fixed commit in `scripts/release-signature-base`, not a merge-base with `main`. An unknown base stops the release. |
| `scripts/lane-env.sh` | Classic: port 8796, jobs and settings in `~/vibecut-lanes/classic`, packs in `~/vibecut-lanes/classic/packs`, media, recordings, voices and music in `data/`, fill models in `~/.cache/vibecut/models/fill`. |
| `scripts/ship-lane.sh` | Takes in only `origin/classic`. Never moves `main`. |
| `scripts/serve-classic.sh` | Starts `app.py` from this checkout. It uses `.venv` here if there is one. |

## What Classic still reads outside this checkout

Audit of 2026-11-04, updated 2026-11-05. No Python file imports from, or names a path in, another checkout.

| Thing | Location | Size | Shared with | Status |
|---|---|---|---|---|
| Lane data, keys, jobs | `~/vibecut-lanes/classic` | — | nobody | Own |
| Compiled helpers | `bin/transcribe_apple`, `bin/vision_probe` in this checkout (not tracked; source in `tools/`) | small | nobody | Own |
| Optional packs | `~/vibecut-lanes/classic/packs` (was `~/Library/Application Support/VibeCut/packs`, which does not exist on this Mac) | none yet | nobody | Own |
| AI fill models | `~/.cache/vibecut/models/fill` (`VIBECUT_FILL_MODELS`, set by `lane-env.sh`) | 274 MB | every lane | Shared, founder's decision. Copied once from Studio's data on 2026-11-05 and checked against `SHA256SUMS` |
| Kokoro voices | `data/models/kokoro` in this checkout, or the Voice pack | not installed | nobody | Own folder, empty |
| Lane media | `data/media`, `data/recordings` in this checkout (gitignored) | founder's files | nobody | Own. Tests read real files here; see `docs/classic/testing/real-media.md` |
| Cloned voices | `data/voices` in this checkout (`VIBECUT_VOICES_DIR`) | founder's files | nobody | Own |
| Music library | `data/music` in this checkout (`VIBECUT_MUSIC_DIR`) | founder's files | nobody | Own |
| Python 3.11 and packages | `/opt/homebrew`, site-packages | 2.6 GB | every lane, founder app | Machine-level. No venv |
| ffmpeg, ffprobe, yt-dlp, mlx_whisper | `/opt/homebrew/bin` | — | every lane | Machine-level |
| Whisper model | `~/.cache/huggingface/hub` (`HF_HUB_CACHE` moves it) | 1.5 GB | every lane | Machine-level |
| Argos translation models | `~/.local/share/argos-translate` | 83 MB | every lane | Machine-level |
| OpenCode CLI and its login | `~/.opencode`, `~/.local/share/opencode` | 171 MB | every lane | Machine-level |

Machine-level things stay in place when Studio moves its code. They change only if
someone upgrades or deletes them. Sharing them is the founder's decision for
development, so Classic makes no per-lane copy of them.
