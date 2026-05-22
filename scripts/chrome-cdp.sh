#!/usr/bin/env bash
# Launch Google Chrome with the DevTools remote-debugging port open so
# jobscout scripts (bootstrap, future apply) can attach via CDP.
#
# Uses a dedicated profile under ~/.cache/jobscout/chrome-cdp so it doesn't
# fight with your normal Chrome windows. Log into LinkedIn once in this
# window; the profile persists across runs.
#
# Usage:
#   bash scripts/chrome-cdp.sh                                  # launch
#   make bootstrap-profile LINKEDIN_URL=https://...             # use it
#
# When you're done, just close the Chrome window.

set -euo pipefail

PORT="${PORT:-9222}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.cache/jobscout/chrome-cdp}"
JOBSCOUT_CHROME_BIN="${JOBSCOUT_CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [[ ! -x "$JOBSCOUT_CHROME_BIN" ]]; then
  echo "Chrome not found at $JOBSCOUT_CHROME_BIN — set JOBSCOUT_CHROME_BIN to your install path" >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"

echo "Launching Chrome on port $PORT with profile $PROFILE_DIR"
echo "After Chrome opens: sign into LinkedIn once, then leave the window open."
echo "Run bootstrap from another terminal with:"
echo "  make bootstrap-profile LINKEDIN_URL=https://www.linkedin.com/in/<the-user>/"
echo ""

exec "$JOBSCOUT_CHROME_BIN" \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "https://www.linkedin.com/feed/"
