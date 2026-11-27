"""Written source offer for the bundled LGPL FFmpeg.

The text is built here so the core can serve it without finding a file inside
the app bundle. `Licenses/FFmpeg-SOURCE.txt` is the same text (a test keeps
them equal), and the configure line must match `scripts/build-ffmpeg-lgpl.sh`.
"""

from __future__ import annotations

FFMPEG_VERSION = "7.1.1"

FFMPEG_CONFIGURE = """PKG_CONFIG_PATH="/opt/homebrew/opt/dav1d/lib/pkgconfig:${PKG_CONFIG_PATH:-}" \\
./configure \\
  --prefix="$PREFIX" \\
  --disable-gpl \\
  --disable-nonfree \\
  --disable-doc \\
  --disable-debug \\
  --disable-network \\
  --disable-autodetect \\
  --enable-zlib \\
  --enable-libdav1d \\
  --enable-videotoolbox \\
  --enable-audiotoolbox \\
  --enable-static \\
  --disable-shared \\
  --extra-ldflags="-Wl,-rpath,@executable_path\""""

FFMPEG_SOURCE_OFFER = f"""FFmpeg {FFMPEG_VERSION} · LGPL 2.1 · written source offer

DuckSuite includes the ffmpeg and ffprobe programs from FFmpeg {FFMPEG_VERSION}, built
as LGPL only (no GPL or non-free parts) and unmodified. They link only against
macOS system frameworks and dav1d (BSD-2-Clause). The licence is in
FFmpeg-LGPL-2.1.txt beside this file.

Source
  Tarball:   https://ffmpeg.org/releases/ffmpeg-{FFMPEG_VERSION}.tar.xz
  Signature: https://ffmpeg.org/releases/ffmpeg-{FFMPEG_VERSION}.tar.xz.asc
  FFmpeg publishes a GPG signature for each release, not a SHA-256 digest
  (https://ffmpeg.org/download.html#releases). Check the tarball with the
  signature and the FFmpeg release key.

Build
  Script: scripts/build-ffmpeg-lgpl.sh in the DuckSuite source. Configure line:

{FFMPEG_CONFIGURE}

  PREFIX is the install folder (build/ffmpeg-lgpl by default).

Written offer
  For at least three years from the day we distribute this build of DuckSuite,
  anyone may ask us for the complete corresponding source code of the FFmpeg
  programs above, including the build script, on a medium customarily used for
  software interchange, for no more than the cost of performing that
  distribution. Write to: <contact address>
"""
