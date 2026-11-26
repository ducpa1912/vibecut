#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/build/pb-source"
out="$root/build/whisper-cpp"
tag=v1.8.2
commit=4979e04f5dcaccb36057e059bbaed8a2f5288315
mkdir -p "$out"
if [[ ! -d "$src" ]]; then
  git clone --depth 1 --branch "$tag" https://github.com/ggml-org/whisper.cpp.git "$src"
fi
[[ "$(git -C "$src" rev-parse HEAD)" == "$commit" ]]
[[ -z "$(git -C "$src" status --porcelain)" ]]
grep -qx 'MIT License' "$src/LICENSE"
prefix_map="-ffile-prefix-map=$root=."
flags=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64
       -DCMAKE_INSTALL_PREFIX=/usr/local -DBUILD_SHARED_LIBS=OFF
       -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON -DGGML_NATIVE=OFF
       -DWHISPER_CURL=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF
       "-DCMAKE_C_FLAGS=$prefix_map" "-DCMAKE_CXX_FLAGS=$prefix_map"
       "-DCMAKE_OBJC_FLAGS=$prefix_map" "-DCMAKE_OBJCXX_FLAGS=$prefix_map")
cmake -S "$src" -B "$out/obj" "${flags[@]}"
cmake --build "$out/obj" --config Release --target whisper-cli --parallel "$(sysctl -n hw.ncpu)"
candidate="$out/obj/bin/whisper-cli"
otool -L "$candidate" | awk 'NR > 1 && $1 !~ /^\/(usr\/lib|System\/Library)\// { print; bad=1 } END {exit bad}'
if strings "$candidate" | grep -F /Users/ >/dev/null; then
  echo "error: whisper-cli contains a home directory path" >&2
  exit 1
fi
nm "$candidate" | grep 'ggml_metallib_start' >/dev/null
install -m 755 "$candidate" "$out/whisper-cli"
cp "$src/LICENSE" "$out/LICENSE"
{
  printf 'whisper.cpp %s (%s)\n' "$tag" "$commit"
  printf '%q ' cmake -S "$src" -B "$out/obj" "${flags[@]}"
  printf '\n'
  otool -L "$out/whisper-cli"
  "$out/whisper-cli" --help
} > "$out/BUILD.txt" 2>&1
