#!/usr/bin/env bash
# SCBrowser installer (macOS Apple Silicon, arm64).
# Usage: ./scripts/install.sh
# Steps: 1) ensure ungoogled-chromium (Brew cask), 2) build SCBrowser.app
#        (byte-identical copy, signature preserved), 3) put `scbrowser`
#        on PATH, 4) verify a cold start.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "==> SCBrowser install (macOS arm64)"

if [ ! -d "/Applications/Chromium.app" ]; then
  echo "Installing ungoogled-chromium via Homebrew..."
  /opt/homebrew/bin/brew install --cask ungoogled-chromium
else
  echo "Chromium.app found: $(/Applications/Chromium.app/Contents/MacOS/Chromium --version)"
fi

echo "==> Building SCBrowser.app (signature must stay valid - see build-app.sh)"
"$ROOT/scripts/build-app.sh"

chmod +x "$ROOT/bin/scbrowser"

# Put `scbrowser` on PATH: symlink into /usr/local/bin (already on PATH).
# Falls back to adding $ROOT/bin to ~/.zshrc if /usr/local/bin isn't writable.
if [ -w /usr/local/bin ]; then
  ln -sf "$ROOT/bin/scbrowser" /usr/local/bin/scbrowser
  echo "Linked: /usr/local/bin/scbrowser"
else
  mkdir -p "$HOME/bin"
  ln -sf "$ROOT/bin/scbrowser" "$HOME/bin/scbrowser"
  grep -q "SCBrowser/bin" "$HOME/.zshrc" 2>/dev/null || \
    echo 'export PATH="$HOME/SCBrowser/bin:$PATH"' >> "$HOME/.zshrc"
  echo "Linked: ~/bin/scbrowser (+ PATH line in ~/.zshrc)"
fi

echo "==> Verifying cold start"
scbrowser close >/dev/null 2>&1 || true
scbrowser open https://example.com
scbrowser status

echo "Done. Daily use (plain `scbrowser`, no full path needed):"
echo "  scbrowser open https://privacytests.org/"
echo "  scbrowser show        # bring window to front"
echo "  scbrowser hide        # minimize"
echo "  scbrowser close       # quit SCBrowser only"
echo "Note: launch via the CLI only - double-clicking SCBrowser.app"
echo "      in Finder/Dock opens stock Chromium, by design (see README)."
