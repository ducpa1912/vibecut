#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'error: %s\n' "$*" >&2; exit 1; }
[[ $# == 1 ]] || fail 'usage: check-bundle-helpers.sh <app>'
# The dev bundle keeps helpers in Contents/Helpers; the Xcode app in Contents/Resources/Helpers.
helpers="$1/Contents/Helpers"
[[ -d "$helpers" ]] || helpers="$1/Contents/Resources/Helpers"
lib=libdav1d.7.dylib
names=(ffmpeg ffprobe "$lib" whisper-cli)
for name in "${names[@]}"; do
  if [[ "$name" == whisper-cli && ! -e "$helpers/$name" && "${DUCK_ALLOW_NO_WHISPER:-0}" == 1 ]]; then
    continue
  fi
  if [[ "$name" != whisper-cli && ! -e "$helpers/$name" && "${DUCK_ALLOW_NO_FFMPEG:-0}" == 1 ]]; then
    continue
  fi
  file="$helpers/$name"
  [[ -f "$file" ]] || fail "missing $name"
  listing=$(otool -L "$file") || fail "cannot inspect $name"
  # The heading contains the caller's build path. Inspect load commands only.
  deps=$(awk 'NR > 1 {sub(/^[[:space:]]*/, ""); sub(/ \(compatibility version.*/, ""); print}' <<< "$listing")
  [[ -n "$deps" ]] || fail "missing load commands for $name"
  while IFS= read -r dep; do
    case "$dep" in
      /usr/lib/*|/System/Library/*) ;;
      "@loader_path/$lib") [[ "$name" != whisper-cli ]] || fail "whisper-cli links outside system libraries" ;;
      *) fail "$name links outside the bundle: $dep" ;;
    esac
  done <<< "$deps"
  if [[ "$name" == whisper-cli ]]; then
    [[ -x "$file" ]] && "$file" --help >/dev/null 2>&1 || fail "whisper-cli failed to run"
  elif [[ "$name" != "$lib" ]]; then
    [[ -x "$file" ]] || fail "$name is not executable"
    version=$("$file" -version) || fail "$name -version failed"
    config=$(sed -n 's/^configuration: //p' <<< "$version")
    [[ -n "$config" ]] || fail "$name has no configure line"
    case " $config " in
      *" --enable-gpl "*|*" --enable-nonfree "*) fail "$name enables GPL or nonfree components" ;;
    esac
    [[ " $config " == *" --enable-libdav1d "* ]] || fail "$name lacks dav1d"
  fi
done
printf 'Bundle helper check passed\n'
