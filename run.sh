#!/usr/bin/env bash
#
# Wrapper for the daily cron run on the Raspberry Pi.
# Activates the venv, runs all scrapers + Firestore upload, and logs the output.
#
set -euo pipefail

# Directory this script lives in (= project root), regardless of where cron calls it from.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

mkdir -p logs
LOG="logs/$(date +%Y-%m-%d_%H%M%S).log"

# Use system Chromium on the Pi (Playwright's bundled build has no armhf binaries).
export PLAYWRIGHT_BROWSERS_PATH=0

{
    echo "=== Run started: $(date) ==="
    source venv/bin/activate
    python main.py
    echo "=== Run finished: $(date) ==="
} >>"$LOG" 2>&1

# Keep only the 14 most recent logs.
ls -1t logs/*.log | tail -n +15 | xargs -r rm --
