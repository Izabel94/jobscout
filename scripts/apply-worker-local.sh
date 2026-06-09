#!/usr/bin/env bash
# Local apply-worker, designed for macOS launchd.
#
# Polls cloud Supabase for pending apply_requests; runs the matching
# per-source apply module against the user's CDP-attached Chrome.
# Notifies on failure so silent crashes are visible.
#
# Install:
#   cp scripts/com.jobscout.apply-worker.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.jobscout.apply-worker.plist
#
# Manual smoke test:
#   bash scripts/apply-worker-local.sh

set -uo pipefail

REPO_DIR="${JOBSCOUT_REPO:-$HOME/projects/jobscout}"
LOG_DIR="$HOME/.cache/jobscout/launchd"
LOG_FILE="$LOG_DIR/apply-worker.log"
# 9223, not 9222 — sidegig owns 9222. Distinct ports stop the two apps'
# workers from attaching to each other's CDP Chrome.
CDP_PORT="${CDP_PORT:-9223}"

# In-project venv; survives branch switches because .venv is gitignored.
PYTHON="$REPO_DIR/.venv/bin/python"
DOTENV="$REPO_DIR/.venv/bin/dotenv"

mkdir -p "$LOG_DIR"

notify() {
  local title="$1" body="$2"
  osascript -e "display notification \"$body\" with title \"$title\" sound name \"Funk\"" 2>/dev/null \
    || echo "[notify-fallback] $title — $body" >> "$LOG_FILE"
}

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }

echo "" >> "$LOG_FILE"
echo "==== $(ts) apply-worker starting ====" >> "$LOG_FILE"

# Single-instance lock. A run now keeps the filled tab open for review (up to
# ~10 min), so it can outlast the 5-min launchd tick — skip overlapping ticks
# rather than attach a second worker to the same Chrome. mkdir is atomic and
# portable (no flock on macOS). Reclaim a lock older than 30 min (prior run
# killed, e.g. machine slept).
LOCK_DIR="$LOG_DIR/apply-worker.lock"
if [[ -d "$LOCK_DIR" && -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +30 2>/dev/null)" ]]; then
  rmdir "$LOCK_DIR" 2>/dev/null || true
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$(ts) another worker holds the lock — skipping this tick" >> "$LOG_FILE"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# Cheap CDP probe — open a TCP connection to the debug port.
# Skip silently if Chrome isn't up AND there are no pending rows. If
# pending rows exist, surface a notification so the user knows.
if ! lsof -nP -iTCP:"$CDP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  pending=$(
    cd "$REPO_DIR" && \
    "$DOTENV" run -- "$PYTHON" -c "
from jobscout.db import list_apply_requests
n = sum(1 for r in list_apply_requests(limit=50) if r['status'] == 'pending')
print(n)
" 2>/dev/null || echo 0
  )
  if [[ "${pending:-0}" -gt 0 ]]; then
    notify "jobscout: $pending apply request(s) waiting" \
      "Start Chrome with: bash scripts/chrome-cdp.sh"
  fi
  echo "$(ts) CDP Chrome down; pending=$pending — exiting" >> "$LOG_FILE"
  # Intentional exit 0: don't pollute launchctl's last-exit-status with
  # "Chrome not running" — that's a normal state for a 5-min poll.
  # User already got a notification above if there were pending rows.
  exit 0
fi

cd "$REPO_DIR" || { notify "jobscout apply-worker" "cd $REPO_DIR failed"; exit 1; }

if [[ ! -x "$PYTHON" ]]; then
  notify "jobscout apply-worker" "venv missing: $PYTHON — run \`poetry install\`"
  exit 127
fi

# Hard backstop only. The worker bounds its own review wait (~10 min) and
# exits 0 normally; 900s sits above fill-time + that wait so a genuine hang
# (exit 124) still surfaces as a failure, but normal review never trips it.
JOBSCOUT_CDP_URL="http://localhost:$CDP_PORT" \
  gtimeout 900 "$DOTENV" run -- "$PYTHON" -m jobscout.apply.worker >> "$LOG_FILE" 2>&1
status=$?

if [[ $status -ne 0 ]]; then
  tail_lines="$(tail -5 "$LOG_FILE" | tr '\n' ' ' | cut -c1-240)"
  notify "jobscout apply-worker FAILED (exit $status)" "$tail_lines"
  echo "$(ts) FAILED exit=$status" >> "$LOG_FILE"
  exit "$status"
fi

echo "$(ts) OK" >> "$LOG_FILE"
