#!/usr/bin/env bash
# Build the FFmpeg 7.1.1 binaries DuckSuite ships.
#
# LGPL only: no --enable-gpl, no --enable-nonfree, no libx264/libx265, and no
# network protocols. H.264 encode uses Apple VideoToolbox, AAC uses the native
# encoder. FFmpeg libraries are static. The arm64 tools load dav1d from
# beside the executable and use macOS system libraries and frameworks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${FFMPEG_VERSION:-7.1.1}"
SRC="${FFMPEG_SRC:-$ROOT/build/ffmpeg-src}"
OUTPUT="${FFMPEG_PREFIX:-$ROOT/build/ffmpeg-lgpl}"
TARBALL="$SRC/ffmpeg-$VERSION.tar.xz"

mkdir -p "$SRC" "$OUTPUT"
if [ ! -f "$TARBALL" ]; then
  curl -L --fail --silent --show-error \
    -o "$TARBALL.part" "https://ffmpeg.org/releases/ffmpeg-$VERSION.tar.xz"
  mv "$TARBALL.part" "$TARBALL"
fi
if [ ! -d "$SRC/ffmpeg-$VERSION" ]; then
  tar xf "$TARBALL" -C "$SRC"
fi

cd "$SRC/ffmpeg-$VERSION"
# Use the published configure recipe without embedding the staging directory.
PREFIX=/usr/local
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
# Stage just the shipping artifacts. Keep the configure prefix independent of
# the checkout because both executables print it in their version banner.
mkdir -p "$OUTPUT/bin" "$OUTPUT/lib"
lib=libdav1d.7.dylib
install -m 755 "/opt/homebrew/opt/dav1d/lib/$lib" "$OUTPUT/lib/$lib"
install_name_tool -id "@loader_path/$lib" "$OUTPUT/lib/$lib"
codesign --force --sign - "$OUTPUT/lib/$lib"
ln -sf "../lib/$lib" "$OUTPUT/bin/$lib"

for tool in ffmpeg ffprobe; do
  install -m 755 "$tool" "$OUTPUT/bin/$tool"
  dep=$(otool -L "$OUTPUT/bin/$tool" | awk '$1 ~ /\/libdav1d\.7\.dylib$/ {print $1}')
  install_name_tool -change "$dep" "@loader_path/$lib" "$OUTPUT/bin/$tool"
  codesign --force --sign - "$OUTPUT/bin/$tool"
  if strings "$OUTPUT/bin/$tool" | grep -F '/Users/' >/dev/null; then
    echo "error: $tool contains a home directory path" >&2
    exit 1
  fi
done
"$OUTPUT/bin/ffmpeg" -version > "$OUTPUT/BUILD.txt"
printf 'Built %s/bin/ffmpeg and ffprobe\n' "$OUTPUT"
