#!/bin/bash
# Stop the supervised bot + any stray bot.py processes.
BASE="$(cd "$(dirname "$0")" && pwd)"
pkill -9 -f "$BASE/venv/bin/python.*bot.py" 2>/dev/null
pkill -9 -f "supervise_bot.sh" 2>/dev/null
echo "stopped"
