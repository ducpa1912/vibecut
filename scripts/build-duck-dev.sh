#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${DUCK_APP_OUT:-$ROOT/build/DuckSuite.app}"
CORE="$ROOT/build/duckcore-dist"

"$ROOT/scripts/build-duckcore.sh" "$CORE"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Helpers"
cp "$ROOT/mac/DuckSuite/DuckSuite/Info.plist" "$APP/Contents/Info.plist"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable DuckSuite" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.ducksuite.app" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName DuckSuite" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 0.1.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion 1" "$PLIST"

swiftc \
  -O \
  -target arm64-apple-macosx26.0 \
  -parse-as-library \
  -o "$APP/Contents/MacOS/DuckSuite" \
  "$ROOT"/mac/DuckSuite/DuckSuite/*.swift

mkdir -p "$APP/Contents/Resources/duckcore"
cp -R "$CORE/duckcore/." "$APP/Contents/Resources/duckcore/"
mkdir -p "$APP/Contents/Resources/static"
cp -R "$ROOT/static/duck" "$APP/Contents/Resources/static/duck"

for helper in vision_probe transcribe_apple translate_apple; do
  if [ -x "$ROOT/bin/$helper" ]; then
    cp "$ROOT/bin/$helper" "$APP/Contents/Helpers/$helper"
  fi
done

MODEL="${DUCK_LAMA_MODEL:-$HOME/vibecut-lanes/ducksuite/models/fill/lama_fp32.onnx}"
if [ -f "$MODEL" ]; then
  mkdir -p "$APP/Contents/Resources/base-models"
  cp "$MODEL" "$APP/Contents/Resources/base-models/lama_fp32.onnx"
else
  printf 'warning: LaMa model not found at %s\n' "$MODEL" >&2
fi

if [ -n "${DUCK_FFMPEG:-}" ] && [ -x "$DUCK_FFMPEG" ]; then
  cp "$DUCK_FFMPEG" "$APP/Contents/Helpers/ffmpeg"
else
  printf 'warning: LGPL ffmpeg not copied; set DUCK_FFMPEG=/path/to/lgpl/ffmpeg\n' >&2
fi

codesign --force --deep --sign - \
  --entitlements "$ROOT/mac/DuckSuite/DuckSuite/DuckSuite.entitlements" \
  "$APP" >/dev/null

printf 'Built %s\n' "$APP"
printf 'Run: open "%s"\n' "$APP"
