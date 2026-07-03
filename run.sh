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

# Run the scrapers, capturing the exit status without aborting the script so
# we can always send a notification and clean up afterwards.
STATUS=0
{
    echo "=== Run started: $(date) ==="
    source venv/bin/activate
    python main.py
    echo "=== Run finished: $(date) ==="
} >>"$LOG" 2>&1 || STATUS=$?

# ── Notification via ntfy.sh ──────────────────────────────────────────────
# Put your private topic in a gitignored file next to this script:
#   echo "my-secret-topic-xy93" > .ntfy_topic
# Install the ntfy app, subscribe to the same topic, done.
NTFY_TOPIC="$(cat "$DIR/.ntfy_topic" 2>/dev/null || true)"

if [ -n "$NTFY_TOPIC" ]; then
    # A run is healthy only if main.py exited 0, printed its final summary,
    # and the log has no hard failures.
    if [ "$STATUS" -eq 0 ] \
        && grep -q "Timing summary" "$LOG" \
        && ! grep -qiE "Traceback|too many index entries|Quota exceeded" "$LOG"; then
        TITLE="✅ Scraper OK"
        PRIORITY="default"
    else
        TITLE="❌ Scraper FAILED (exit $STATUS)"
        PRIORITY="high"
    fi

    # Build a short body: per-scraper product counts, upload total, timing, and
    # a count of any errors logged.
    SUMMARY="$(grep -E "Saved [0-9]+ products to" "$LOG" || true)"
    WRITES="$(grep -E "Writes *:" "$LOG" | tail -1 || true)"
    TIMING="$(grep -E "^ *Total " "$LOG" | tail -1 || true)"
    ERRCOUNT="$(grep -cEi "Traceback|Error scraping|pagination_stalled|too many index entries|Quota exceeded" "$LOG" || true)"

    BODY="$(printf '%s\n%s\n%s\nError lines: %s\nLog: %s' \
        "$SUMMARY" "$WRITES" "$TIMING" "$ERRCOUNT" "$LOG")"

    # Best-effort: never let a notification failure break the run.
    curl -s --max-time 20 \
        -H "Title: $TITLE" \
        -H "Priority: $PRIORITY" \
        -d "$BODY" \
        "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
fi

# Keep only the 14 most recent logs.
ls -1t logs/*.log | tail -n +15 | xargs -r rm --

exit "$STATUS"
