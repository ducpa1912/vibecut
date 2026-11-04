# Voice Room runtime (audit 2026-11-04, at `a3da0b1`)

Studio is moving its shared code into `features/` and `core/` on its own branch. Voice Room keeps its own copy of what it runs on, so that move cannot change this lane.

## Our copy of the shared backend

`voice_runtime_manifest.json` lists 63 files with their sha256 at `a3da0b1`: every module the server can reach, plus `requirements.txt`, `scripts/lane-env.sh` and `scripts/ship-lane.sh`. The seven modules written for this lane are listed as `owned` and are not pinned.

`tests/test_voice_runtime_pin.py` fails when:

- a pinned file changed without a mark, or went missing;
- a module runs here and is not pinned (imports inside functions and `__import__("name")` count);
- the running server loads a repo module the import walk did not see;
- anything imports `features.*` or `core.*`, or a runtime file names another worktree.

A Studio change reaches this lane only as a deliberate port, with Voice Room tests, and then a mark:

```bash
python3 scripts/voice_runtime_pin.py --mark audio.py --note "Port the X fix from Studio"
python3 scripts/voice_runtime_pin.py --add new_module.py --note "Needed by the Y route"
python3 scripts/voice_runtime_pin.py --check
```

## What stays shared

The founder decided on 2026-11-05 that Python, packages, Whisper, other models and Playwright stay shared on this machine for development. No lane makes its own copy. The code pin above is a separate matter: it protects this lane from Studio's code move.

## What the lane reaches outside its worktree

| Item | Where it is now | Size | Shared with other lanes? | State |
|---|---|---|---|---|
| Python 3.11.7 and all packages | `/opt/homebrew/bin/python3`, `/opt/homebrew/lib/python3.11/site-packages`. This worktree has no `.venv`. | 2.6 GB | Yes | Shared by the founder's decision. Versions recorded in `docs/voice/runtime-lock.txt`. |
| ffmpeg, ffprobe 9.0.2 | `/opt/homebrew/bin` | system tool | Yes | Reported, not copied |
| demucs 4.1.0 | `/opt/homebrew/bin/demucs` | in site-packages | Yes | Reported. Weights not on this Mac (`~/.cache/torch` absent), so first use downloads them. |
| mlx_whisper 0.4.3 | `/opt/homebrew/bin/mlx_whisper` | in site-packages | Yes | Reported |
| Whisper weights (`mlx-community/whisper-large-v3-turbo`) | `~/.cache/huggingface/hub` (`stt.py`, honours `HF_HOME` and `HF_HUB_CACHE`) | 1.5 GB | Yes | Shared by the founder's decision |
| yt-dlp 2026.10.21 | `/opt/homebrew/bin/yt-dlp` | system tool | Yes | Reported |
| `deep-filter`, `audio-separator`, RoFormer model | Not installed on this Mac | none | n/a | Optional. Search falls back. |
| Packs | `~/Library/Application Support/VibeCut` (`packs.py`, `VIBECUT_PACKS_DIR`): absent on this Mac | none | Would be | Nothing to copy. Set `VIBECUT_PACKS_DIR` if packs arrive. |
| Kokoro models | `<worktree>/data/models/kokoro` or a pack: absent | none | No | Kokoro shows as not installed |
| Playwright for recordings | `~/.npm/_npx/*/node_modules/playwright`, `~/Library/Caches/ms-playwright` | 668 MB + 206 MB | Yes | Shared by the founder's decision |
| OpenCode | `~/.opencode/bin/opencode` | 171 MB | Yes | Tool for the lane's builds. The voice Setup no longer offers it. |
| Apple `say`, `swiftc` | `/usr/bin` | system | Yes | Part of macOS |
| `OPENROUTER_API_KEY` | The shell environment | none | Yes | Used until a key is saved in this app's Setup |
| `bin/vision_probe` | `<worktree>/bin` (git-ignored, built locally) | 200 KB | No | Already the lane's own |
| Finder launchers | `scripts/*.command`, found relative to themselves | small | No | Own. There is no Desktop launcher for this lane. |

## Data, media and recordings

Each lane stores its own files, git-ignored. The old `~/vibecut-lanes/voice`, `~/vibecut-lanes/media/voiceroom` and `~/vibecut-lanes/recordings/voiceroom` folders were removed on purpose by the founder and are not restored.

| What | Where |
|---|---|
| Jobs, settings, keys, logs, `server.pid` | `data/` |
| Media and real test files | `data/media` |
| Recordings | `data/recordings` |
| Cloned voices | `data/voices` (`voice_clone.py`) |
| Music library | `data/music` (`audio.MUSIC_DIRS`) |
