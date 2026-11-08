#!/usr/bin/env bash
# Build the FFmpeg 7.1.1 binaries DuckSuite ships.
#
# LGPL only: no --enable-gpl, no --enable-nonfree, no libx264/libx265, and no
# network protocols. H.264 encode uses Apple VideoToolbox, AAC uses the native
# encoder. The output is two static arm64 binaries that link only against
# macOS system frameworks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${FFMPEG_VERSION:-7.1.1}"
SRC="${FFMPEG_SRC:-$ROOT/build/ffmpeg-src}"
PREFIX="${FFMPEG_PREFIX:-$ROOT/build/ffmpeg-lgpl}"
TARBALL="$SRC/ffmpeg-$VERSION.tar.xz"

mkdir -p "$SRC" "$PREFIX"
if [ ! -f "$TARBALL" ]; then
  curl -L --fail --silent --show-error \
    -o "$TARBALL" "https://ffmpeg.org/releases/ffmpeg-$VERSION.tar.xz"
fi
if [ ! -d "$SRC/ffmpeg-$VERSION" ]; then
  tar xf "$TARBALL" -C "$SRC"
fi

cd "$SRC/ffmpeg-$VERSION"
PKG_CONFIG_PATH="/opt/homebrew/opt/dav1d/lib/pkgconfig:${PKG_CONFIG_PATH:-}" \
./configure \
  --prefix="$PREFIX" \
  --disable-gpl \
  --disable-nonfree \
  --disable-doc \
  --disable-debug \
  --disable-network \
  --disable-autodetect \
  --enable-zlib \
  --enable-libdav1d \
  --enable-videotoolbox \
  --enable-audiotoolbox \
  --enable-static \
  --disable-shared \
  --extra-ldflags="-Wl,-rpath,@executable_path"
make -j"$(sysctl -n hw.ncpu)"
make install

# Ship dav1d beside the binaries; @executable_path is the rpath.
DAV1D_SRC="/opt/homebrew/opt/dav1d/lib/libdav1d.7.dylib"
mkdir -p "$PREFIX/lib"
cp "$DAV1D_SRC" "$PREFIX/lib/libdav1d.7.dylib"
for tool in ffmpeg ffprobe; do
  install_name_tool -change "$DAV1D_SRC" "@rpath/libdav1d.7.dylib" "$PREFIX/bin/$tool"
  codesign --force --sign - "$PREFIX/bin/$tool" >/dev/null 2>&1 || true
done
codesign --force --sign - "$PREFIX/lib/libdav1d.7.dylib" >/dev/null 2>&1 || true

printf 'Built %s/bin/ffmpeg and ffprobe\n' "$PREFIX"
