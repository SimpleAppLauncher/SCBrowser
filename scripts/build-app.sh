#!/usr/bin/env bash
# Build a standalone SCBrowser.app from the installed ungoogled-chromium.
#
# CRITICAL (2026-11-06): the bundle must stay BYTE-IDENTICAL to the signed
# original. Do NOT rebrand Info.plist, do NOT add a wrapper script as
# CFBundleExecutable, do NOT put files inside the bundle, do NOT re-sign.
# Any of those invalidates the Developer ID signature -> macOS AMFI
# SIGKILLs every exec (-9, empty log) because of the `kill` flag, and the
# Keychain "Chromium Safe Storage" ACL stops matching -> "Relaunch to keep
# things encrypted" banner forever. Self-signed identities are NOT_TRUSTED
# and codesign can't use them, so re-signing is not a fix either.
#
# SCBrowser identity comes from launch-time flags instead (bin/scbrowser):
# own profile (~/Library/Application Support/SCBrowser), own port (9222),
# extension from $ROOT/extension, flags from $ROOT/config/privacy-flags.txt.
# It does NOT use /Applications/Chromium.app at runtime (own copy of the
# bundle, own profile + port) and does NOT touch a running Chromium.
#
# Launch ONLY via `bin/scbrowser open` (or close/open). Double-clicking the
# .app in Finder/Dock now opens stock Chromium with the default profile,
# because the bundle keeps its original identity on purpose.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="/Applications/Chromium.app"
APP="$ROOT/SCBrowser.app"
PROFILE_DIR="$HOME/Library/Application Support/SCBrowser"

if [ ! -d "$SRC" ]; then echo "Missing $SRC - install: brew install --cask ungoogled-chromium" >&2; exit 1; fi

echo "==> Building $APP from $SRC (byte-identical copy, no modifications)"
rm -rf "$APP"
cp -a "$SRC" "$APP"
xattr -cr "$APP" 2>/dev/null || true

mkdir -p "$PROFILE_DIR"

echo "==> Verifying signature (must say valid / accepted)"
codesign --verify --verbose=2 "$APP/Contents/MacOS/Chromium"
codesign --verify --verbose=2 "$APP"
spctl -a -vv "$APP" | head -5

echo "==> Warm-up: direct exec must succeed on first try (no 137 retries needed)"
if "$APP/Contents/MacOS/Chromium" --version >/dev/null 2>&1; then
  echo "Warm-up OK: $("$APP/Contents/MacOS/Chromium" --version)"
else
  echo "WARNING: --version failed (SIGKILL). Do NOT re-sign or edit the bundle." >&2
  echo "Check: codesign --verify --verbose=4 \"$APP/Contents/MacOS/Chromium\"" >&2
  exit 1
fi

echo "Built: $APP"
echo "Profile (separate from Chromium): $PROFILE_DIR"
echo "Launch (CLI only, not Finder/Dock): $ROOT/bin/scbrowser open https://privacytests.org/"
echo "Expected cold start: ~2-5s"
