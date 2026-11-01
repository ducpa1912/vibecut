# Third-party notices

VibeCut is proprietary software. The components below remain under their own
licenses. This file is a release checklist entry point, not legal advice.
Resolve exact versions and full license texts from the release environment; see
[docs/licensing.md](docs/licensing.md).

## Runtime Python packages

| Component | License | Upstream |
|---|---|---|
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| NumPy | BSD-3-Clause and bundled permissive notices | https://numpy.org |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp |
| python-stretch (optional) | MIT | https://github.com/gregogiudici/python-stretch |
| Signalsmith Stretch (optional, via python-stretch) | MIT | https://github.com/Signalsmith-Audio/signalsmith-stretch |

yt-dlp is the default URL downloader and is used through its public Python API.
A copy of the Unlicense text must be included in release artifacts. No
attribution is required by the Unlicense, but the inventory should still list
the installed version.

## System dependencies

- **ffmpeg / ffprobe** — a user-installed system dependency by default. Its
  license depends on the build. A Homebrew build with `--enable-gpl` and
  `--enable-version3` is GPL-3.0-or-later; do not bundle it without the
  corresponding notices and source or written offer.
- **Apple Vision / Speech / AVFoundation** — used through macOS frameworks.
  Apple SDK binaries are not redistributed with VibeCut.
- **swiftc / Xcode Command Line Tools** — used on the user's machine to build
  the Vision helper. Do not redistribute the toolchain.

## Optional external sidecars

xhs_get is not part of the proprietary VibeCut source tree or default
artifact. If a distribution ships it alongside VibeCut, keep it in a separate
artifact and comply with its license:

- **xhs_get** — GPL-3.0. Provide corresponding source or a written offer and the
  license text. Keep its cookies and session inside its own process.

No xhs_get source, comments, tests, or assets are copied into the VibeCut
URL-ingest modules. The integration is HTTP-only.

## Voice extraction engines

Clean voice extraction (`voice_extract.py`) runs only on this Mac. Its engines
are optional, are never required for a clone, and weights with unresolved
terms are downloaded on first use rather than bundled with VibeCut.

| Component | License | Upstream |
|---|---|---|
| DeepFilterNet 3 (`deep-filter`) | Code MIT; model weights MIT / Apache-2.0 | https://github.com/rikorose/deepfilternet |
| Silero VAD v5 | MIT (code and weights) | https://github.com/snakers4/silero-vad |
| Mel-Band RoFormer (Kim vocal 2) weights | MIT since 2026-04-22 (previously GPL-3.0); MLX conversion MIT | https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx |
| `audio-separator` | MIT (wrapper only; model terms stay with each checkpoint) | https://github.com/streichgeorg/python-audio-separator |
| Demucs `htdemucs` / `htdemucs_ft` | Code MIT. The weights are **not** covered by the MIT grant; the author calls them research-oriented because of the MUSDB terms. | https://github.com/facebookresearch/demucs |
| pyannote.audio 3.1 / Community-1 | Code MIT; 3.1 pipeline MIT; Community-1 weights CC-BY-4.0. Gated Hugging Face download. | https://huggingface.co/pyannote/speaker-diarization-3.1 |
| ffmpeg `afftdn` | Part of the ffmpeg build; the binary's LGPL/GPL configuration applies, not VibeCut's source | https://ffmpeg.org |

pyannote attribution: speaker diarization uses pyannote.audio and the
`pyannote/speaker-diarization-3.1` pipeline by Hervé Bredin and contributors,
licensed MIT; the Community-1 weights are CC-BY-4.0. Keep this attribution in
About or Setup wherever the speaker filter is offered.

Demucs note: VibeCut calls the user's installed Demucs and caches the vocal
stem locally. Do not redistribute Demucs weights in an installer until the
weight terms are cleared; Mel-Band RoFormer is the permissive-weight
alternative. MDX-Net/UVR and BS-RoFormer checkpoints are experiments only and
must not ship until their model authors grant written permission.

Mel-Band RoFormer and Demucs weights are downloaded on first use or supplied by
an installed pack. No model weights are stored in the VibeCut repository.
