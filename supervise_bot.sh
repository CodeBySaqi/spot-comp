#!/bin/bash
# 24/7 supervisor: keeps bot.py running, restarts it if it crashes.
# Handles SIGTERM (alwaysdata restart) cleanly: kills the child bot so no
# orphaned bot.py keeps polling the Telegram token (that caused 409 conflicts).
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
BASE="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE" || exit 1

# 1) kill any orphaned bot.py left behind by a previous service instance
pkill -9 -f "$BASE/venv/bin/python.*bot.py" 2>/dev/null
sleep 1

echo "[supervise] started $(date)" >> "$BASE/supervise.log"

BOT_PID=""
cleanup() {
  echo "[supervise] stop signal received — killing bot (pid $BOT_PID)" >> "$BASE/supervise.log"
  if [ -n "$BOT_PID" ]; then
    kill -9 "$BOT_PID" 2>/dev/null
    sleep 1
  fi
  exit 0
}
trap cleanup SIGTERM SIGINT

while true; do
  "$BASE/venv/bin/python" -u "$BASE/bot.py" >> "$BASE/bot.log" 2>&1 &
  BOT_PID=$!
  wait "$BOT_PID"
  echo "[supervise] bot exited at $(date) — restarting in 5s" >> "$BASE/supervise.log"
  sleep 5
done
