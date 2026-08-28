#!/bin/sh
set -eu

CWD=$(dirname -- "$0")
REPO_ROOT=$(cd "$CWD/../.." && pwd)
CACHE_ROOT="${TMPDIR:-/tmp}/helomi-swift-build-cache"

CLANG_MODULE_CACHE_PATH="$CACHE_ROOT/clang"
SWIFTPM_MODULECACHE_OVERRIDE="$CACHE_ROOT/swiftpm"

mkdir -p \
  "$CLANG_MODULE_CACHE_PATH" \
  "$SWIFTPM_MODULECACHE_OVERRIDE"

# avfaudio

AUDIO_PKG_PATH="$CWD/avfaudio"
AUDIO_BUILD_PATH="$AUDIO_PKG_PATH/.build/release/avfaudio"
AUDIO_DST_PATH="$REPO_ROOT/src/helomi_core/audio/avfaudio/bin"

swift build --package-path "$AUDIO_PKG_PATH" -c release
mkdir -p "$AUDIO_DST_PATH"
cp "$AUDIO_BUILD_PATH" "$AUDIO_DST_PATH/avfaudio"
