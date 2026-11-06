#!/usr/bin/env bash
# Measure SCBrowser RAM while a page (default YouTube) is open.
# Usage: scripts/measure.sh [url] [seconds]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-https://www.youtube.com/}"
"$ROOT/bin/scbrowser" open "$URL" >/dev/null
echo "Waiting 8s for page/video to load..."
sleep 8
echo "== scbrowser status =="
"$ROOT/bin/scbrowser" status
echo "== SCBrowser process tree (RSS KB) =="
ps -axo pid=,ppid=,rss=,command= | grep SCBrowser.app | grep -v grep | awk '{print $3, $1}' | sort -nr | head -15 || true
echo "== Total SCBrowser RSS (MB, from CLI tree walk) =="
"$ROOT/bin/scbrowser" memory
echo "Goal: <400MB total is very aggressive for Chromium+YouTube (YouTube alone creates multiple renderers/GPU). If over, try: fewer tabs, --renderer-process-limit=1 via config, or 360p video. See README."
