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

# Use system Chromium on the Pi (Playwright ships no ARM/Raspberry Pi build).
# Adjust the path if `which chromium` differs (e.g. /usr/bin/chromium-browser).
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium

# Unbuffered output so progress shows up in the log in real time (Python
# otherwise buffers stdout when it's redirected to a file instead of a tty).
export PYTHONUNBUFFERED=1

# Scrape SPAR one category at a time on the Pi — two concurrent Chromium
# contexts peg the CPU and make pagination clicks flaky. Slower but reliable.
export SPAR_MAX_CONCURRENT=1

{
    echo "=== Run started: $(date) ==="
    source venv/bin/activate
    python main.py
    echo "=== Run finished: $(date) ==="
} >>"$LOG" 2>&1

# Keep only the 14 most recent logs.
ls -1t logs/*.log | tail -n +15 | xargs -r rm --
