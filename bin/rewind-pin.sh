#!/usr/bin/env bash
# Pin the current Rewind context as a labelled snapshot. Run from anywhere.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN="$REPO_ROOT/plugins/rewind.1h.py"

LABEL="${1:-}"

if [ -z "$LABEL" ]; then
  LABEL=$(osascript <<'OSA' || true
tell application "System Events"
  activate
  try
    set theLabel to text returned of (display dialog "Pin this moment as:" default answer "" buttons {"Cancel","Pin"} default button "Pin" with title "Rewind")
    return theLabel
  on error
    return ""
  end try
end tell
OSA
)
fi

LABEL="$(echo -n "$LABEL" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
[ -z "$LABEL" ] && exit 0

PYTHONDONTWRITEBYTECODE=1 python3 "$PLUGIN" pin "$LABEL"

open -g "swiftbar://refreshplugin?name=rewind.1h.py" 2>/dev/null || true

osascript -e "display notification \"$LABEL\" with title \"Pinned moment\" sound name \"Tink\"" 2>/dev/null || true
