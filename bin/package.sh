#!/bin/bash
set -euo pipefail

# Build a shareable tarball of the repo with secrets and per-machine state stripped.
# See README.md "Sharing without GitHub" for the full flow.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"

OUT_DIR="${1:-$HOME/Desktop}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="$OUT_DIR/${REPO_NAME}-${STAMP}.tgz"

mkdir -p "$OUT_DIR"

if [ ! -f "$REPO_ROOT/.env.example" ]; then
    echo "ERROR: $REPO_ROOT/.env.example missing — install.sh would fail on the recipient." >&2
    exit 1
fi

if grep -qE '^(GITHUB_TOKEN|LINEAR_API_KEY|OUTLINE_API_KEY|SLACK_USER_TOKEN)=(ghp_|lin_api_|ol_api_|xoxp-)[A-Za-z0-9]' "$REPO_ROOT/.env.example"; then
    echo "ERROR: .env.example looks like it contains real secrets. Aborting." >&2
    exit 1
fi

PARENT="$(dirname "$REPO_ROOT")"

tar -czf "$OUT_FILE" \
    -C "$PARENT" \
    --exclude="$REPO_NAME/.git" \
    --exclude="$REPO_NAME/.cache" \
    --exclude="$REPO_NAME/config/.env" \
    --exclude="$REPO_NAME/config/auto-hidden.json" \
    --exclude="*/__pycache__" \
    --exclude="*.pyc" \
    --exclude=".DS_Store" \
    "$REPO_NAME"

SIZE="$(du -h "$OUT_FILE" | awk '{print $1}')"

echo "Wrote $OUT_FILE ($SIZE)"
echo
echo "Verify nothing sensitive slipped in:"
echo "  tar -tzf '$OUT_FILE' | grep -E 'config/\\.env$|\\.git/' || echo '  (clean)'"
echo
echo "Recipient runs:"
echo "  tar -xzf $(basename "$OUT_FILE") && cd $REPO_NAME && ./install.sh"
