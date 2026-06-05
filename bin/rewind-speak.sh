#!/usr/bin/env bash
# Refresh Rewind and speak the three lines aloud. Run from anywhere.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN="$REPO_ROOT/plugins/rewind.1h.py"

open -g "swiftbar://refreshplugin?name=rewind.1h.py" 2>/dev/null || true

LINES=$(PYTHONDONTWRITEBYTECODE=1 python3 "$PLUGIN" speak 2>/dev/null || true)

if [ -n "$LINES" ]; then
  TEXT="Where you were. $(echo "$LINES" | sed -n '1p'). Next. $(echo "$LINES" | sed -n '2p'). Don't forget. $(echo "$LINES" | sed -n '3p')."
  say -r 220 "$TEXT" &
fi

osascript -e "display notification \"$LINES\" with title \"Rewind\"" 2>/dev/null || true
