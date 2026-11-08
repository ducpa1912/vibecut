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
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion 1" "$PLIST"

mkdir -p "$APP/Contents/Resources"
cp "$ROOT/mac/DuckSuite/DuckSuite/PrivacyInfo.xcprivacy" "$APP/Contents/Resources/PrivacyInfo.xcprivacy"
if [ -d "$ROOT/mac/DuckSuite/DuckSuite/Assets.xcassets" ]; then
  DEVELOPER="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
  ACTOOL="$DEVELOPER/usr/bin/actool"
  if [ -x "$ACTOOL" ]; then
    ICON_PLIST="$(mktemp -t duck-icon).plist"
    "$ACTOOL" "$ROOT/mac/DuckSuite/DuckSuite/Assets.xcassets" \
      --compile "$APP/Contents/Resources" \
      --platform macosx --minimum-deployment-target 26.0 \
      --app-icon AppIcon --output-partial-info-plist "$ICON_PLIST" >/dev/null 2>&1 || true
    if [ -f "$ICON_PLIST" ]; then
      /usr/libexec/PlistBuddy -c "Merge $ICON_PLIST :" "$PLIST" >/dev/null 2>&1 || true
      rm -f "$ICON_PLIST"
    fi
  elif [ -f "$ROOT/build/DuckSuite-Xcode.app/Contents/Resources/AppIcon.icns" ]; then
    cp "$ROOT/build/DuckSuite-Xcode.app/Contents/Resources/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon" "$PLIST" >/dev/null 2>&1 || \
      /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$PLIST"
  fi
fi

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
mkdir -p "$APP/Contents/Resources/Licenses"
cp -R "$ROOT/Licenses/." "$APP/Contents/Resources/Licenses/"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$APP/Contents/Resources/Licenses/README.md"

mkdir -p "$ROOT/bin"
for helper in vision_probe transcribe_apple translate_apple; do
  source="$ROOT/tools/$helper.swift"
  binary="$ROOT/bin/$helper"
  if [ -f "$source" ] && { [ ! -x "$binary" ] || [ "$source" -nt "$binary" ]; }; then
    if [ "$helper" = "vision_probe" ]; then
      swiftc -O -swift-version 5 "$source" -o "$binary"
    else
      swiftc -O -parse-as-library "$source" -o "$binary"
    fi
  fi
  if [ -x "$binary" ]; then
    cp "$binary" "$APP/Contents/Helpers/$helper"
  fi
done

MODEL="${DUCK_LAMA_MODEL:-$HOME/vibecut-lanes/ducksuite/models/fill/lama_fp32.onnx}"
if [ -f "$MODEL" ]; then
  mkdir -p "$APP/Contents/Resources/base-models"
  cp "$MODEL" "$APP/Contents/Resources/base-models/lama_fp32.onnx"
else
  printf 'warning: LaMa model not found at %s\n' "$MODEL" >&2
fi

FFMPEG_SRC="${DUCK_FFMPEG:-${DUCK_LGPL_FFMPEG:-$ROOT/build/ffmpeg-lgpl/bin/ffmpeg}}"
FFPROBE_SRC="${DUCK_FFPROBE:-$(dirname "$FFMPEG_SRC")/ffprobe}"
if [ -x "$FFMPEG_SRC" ]; then
  cp "$FFMPEG_SRC" "$APP/Contents/Helpers/ffmpeg"
  codesign --force --sign - "$APP/Contents/Helpers/ffmpeg" >/dev/null 2>&1 || true
else
  printf 'warning: LGPL ffmpeg not copied; set DUCK_FFMPEG=/path/to/lgpl/ffmpeg\n' >&2
fi
if [ -x "$FFPROBE_SRC" ]; then
  cp "$FFPROBE_SRC" "$APP/Contents/Helpers/ffprobe"
  codesign --force --sign - "$APP/Contents/Helpers/ffprobe" >/dev/null 2>&1 || true
else
  printf 'warning: LGPL ffprobe not copied; set DUCK_FFPROBE=/path/to/lgpl/ffprobe\n' >&2
fi

DAV1D="${DUCK_DAV1D:-$ROOT/build/ffmpeg-lgpl/lib/libdav1d.7.dylib}"
if [ -f "$DAV1D" ]; then
  cp "$DAV1D" "$APP/Contents/Helpers/libdav1d.7.dylib"
  codesign --force --sign - "$APP/Contents/Helpers/libdav1d.7.dylib" >/dev/null 2>&1 || true
else
  printf 'warning: libdav1d not copied; AV1 input will not decode\n' >&2
fi

# Sign nested code first without the app's sandbox entitlements, then seal the
# app itself. A deep sign with --entitlements gives every helper the app
# sandbox, which breaks standalone ffmpeg/ffprobe/vision_probe runs.
codesign --force --deep --sign - "$APP" >/dev/null
for nested in "$APP"/Contents/Helpers/*; do
  [ -f "$nested" ] && codesign --force --sign - "$nested" >/dev/null 2>&1 || true
done
for attempt in 1 2 3; do
  if codesign --force --sign - \
    --entitlements "$ROOT/mac/DuckSuite/DuckSuite/DuckSuite.entitlements" \
    "$APP" >/dev/null 2>&1; then
    break
  fi
  printf 'codesign attempt %s failed; retrying\n' "$attempt" >&2
  sleep 1
done

printf 'Built %s\n' "$APP"
printf 'Run: open "%s"\n' "$APP"
