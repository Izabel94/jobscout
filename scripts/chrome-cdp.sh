#!/usr/bin/env bash
# Launch Google Chrome with the DevTools remote-debugging port open so
# `sidegig.discover --only upwork` can attach via CDP.
#
# Uses a dedicated profile under ~/.cache/sidegig/chrome-cdp so it doesn't
# fight with your normal Chrome windows. Log into Upwork once in this
# window; the profile persists.
#
# Usage:
#   bash scripts/chrome-cdp.sh         # launch
#   UPWORK_CDP_URL=http://localhost:9222 make discover   # use it
#
# When you're done with discover, just close the Chrome window.

set -euo pipefail

PORT="${PORT:-9222}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.cache/sidegig/chrome-cdp}"
CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "Chrome not found at $CHROME_BIN — set CHROME_BIN to your install path" >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"

echo "Launching Chrome on port $PORT with profile $PROFILE_DIR"
echo "After Chrome opens: sign into Upwork once, then leave the window open."
echo "Run discover from another terminal with:"
echo "  UPWORK_CDP_URL=http://localhost:$PORT poetry run dotenv run -- python -m sidegig.discover --only upwork"
echo ""

exec "$CHROME_BIN" \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "https://www.upwork.com/nx/find-work/"
