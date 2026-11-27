# Third-party notices

DuckSuite is proprietary software. The components below remain under their own
licenses. This file is a release checklist entry point, not legal advice.

The shipped app carries the exact license texts under
`Contents/Resources/Licenses/`. The same files live in [`Licenses/`](Licenses/)
in this repository.

## DuckSuite itself

- Swift shell, web interface, `duckcore`, scene detection, clean pipeline,
  caption renderer, and packaging scripts: proprietary, Copyright © 2026
  DuckSuite.
- No account, telemetry, advertising SDK, or remote service is part of v1.

## Bundled runtime

| Component | License | Upstream |
|---|---|---|
| Python 3.11 | PSF License | https://www.python.org |
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Starlette | BSD-3-Clause | https://github.com/encode/starlette |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| Pydantic | MIT | https://github.com/pydantic/pydantic |
| AnyIO | MIT | https://github.com/agronholm/anyio |
| h11 | MIT | https://github.com/python-hyper/h11 |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| NumPy | BSD-3-Clause and bundled permissive notices | https://numpy.org |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| Click | BSD-3-Clause | https://github.com/pallets/click |
| websockets | BSD-3-Clause | https://github.com/python-websockets/websockets |
| httptools | MIT | https://github.com/MagicStack/httptools |
| OpenTelemetry API | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python |

PyInstaller packs these into a single `duckcore` folder. Their license texts
are in `Licenses/python/` and `Licenses/ONNX-Runtime-ThirdPartyNotices.txt`.
ONNX Runtime's notice covers its own bundled third-party code.

## Clean fill model

- **LaMa** ONNX checkpoint `lama_fp32.onnx` from
  [Carve/LaMa-ONNX](https://github.com/Carve/LaMa-ONNX), a port of
  [big-lama](https://github.com/advimman/lama). Apache-2.0. The full text is
  `Licenses/LaMa-Apache-2.0.txt`; the model file ships in
  `Contents/Resources/base-models/`.
- No model weights are downloaded at runtime.

## FFmpeg

DuckSuite ships two self-contained arm64 binaries:

```text
Contents/Helpers/ffmpeg
Contents/Helpers/ffprobe
```

| Item | Value |
|---|---|
| Version | FFmpeg 7.1.1 |
| License | LGPL-2.1-or-later |
| Configuration | `--disable-gpl --disable-nonfree --disable-network --disable-autodetect --enable-zlib --enable-videotoolbox --enable-audiotoolbox --enable-static --disable-shared` |
| Source | https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz |
| License text | `Licenses/FFmpeg-LGPL-2.1.txt` |
| Build | [`scripts/build-ffmpeg-lgpl.sh`](scripts/build-ffmpeg-lgpl.sh) |

The binaries link against macOS system frameworks and one bundled decoding
library. They contain no GPL code, no libx264, no libx265, and no network
protocol support. H.264 encoding uses Apple VideoToolbox; decoding uses the
native FFmpeg decoders. The build script is part of the complete corresponding
source. Object files for relinking are available on request from the support
address published with the App Store listing.

## dav1d

| Item | Value |
|---|---|
| Version | 1.5.4 |
| License | BSD-2-Clause |
| Purpose | Software AV1 decoding, so AV1 files work without hardware AV1 support |
| Shipped file | `Contents/Helpers/libdav1d.7.dylib` |
| License text | `Licenses/dav1d-BSD-2-Clause.txt` |

The dylib is loaded from the app's own `Helpers` folder through an
`@executable_path` rpath. No Homebrew path is used at runtime.

No Homebrew ffmpeg build is shipped.

## Apple frameworks

DuckSuite calls Apple Vision, Speech, AVFoundation, VideoToolbox, StoreKit (not
used in v1), and AppKit through the macOS SDK. Apple framework binaries are not
redistributed with DuckSuite. The Swift helper binaries are built from
`tools/*.swift` in this repository.

## Icons

- **Lucide** icon paths: ISC License. Text in `Licenses/Lucide-ISC.txt`.
- The DuckSuite app icon is original artwork made for this project.

## Development-only tools

Xcode, XcodeGen, PyInstaller, pytest, and the compilers used to build DuckSuite
are build tools. They are not shipped inside the app.
