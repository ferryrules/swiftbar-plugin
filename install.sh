#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"
PLUGIN_DIR="$SCRIPT_DIR/plugins"

echo "Alembic Dashboard — SwiftBar setup"
echo "==================================="
echo
echo "All config + state lives in $SCRIPT_DIR (config/ and .cache/)."
echo

# --- SwiftBar ---
if ! ls /Applications/SwiftBar.app &>/dev/null 2>&1; then
    echo "SwiftBar not found. Installing via Homebrew…"
    if ! command -v brew &>/dev/null; then
        echo "Homebrew not found. Install SwiftBar manually:"
        echo "  https://github.com/swiftbar/SwiftBar/releases"
        exit 1
    fi
    brew install --cask swiftbar
    echo
fi

# --- Config ---
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$CONFIG_DIR/.env"
    chmod 600 "$CONFIG_DIR/.env"
    echo "Created config: $CONFIG_DIR/.env"
    echo "Opening it now — fill in your API keys."
    echo
    open -a TextEdit "$CONFIG_DIR/.env"
else
    echo "Config already exists: $CONFIG_DIR/.env"
fi

# --- Plugin directory ---
chmod +x "$PLUGIN_DIR"/*.py
chmod +x "$SCRIPT_DIR/tools"/*.py

# Point SwiftBar at our plugin directory
defaults write com.ameba.SwiftBar PluginDirectory "$PLUGIN_DIR"

# --- Rewind indexer (launchd) ---
read -r -p "Install Rewind background indexer (launchd, every 30s)? [Y/n] " ans
ans=${ans:-Y}
if [[ "$ans" =~ ^[Yy]$ ]]; then
    if python3 "$SCRIPT_DIR/tools/rewind-indexer.py" --install-launchd; then
        echo "Indexer installed. First snapshot will appear in ~30s, or run:"
        echo "  python3 $SCRIPT_DIR/tools/rewind-indexer.py --once"
    fi
fi

# --- Ollama (optional) ---
if ! command -v ollama &>/dev/null; then
    echo
    echo "Ollama not detected. For local Rewind synth (no API key, ~1s per call):"
    echo "  brew install ollama && brew services start ollama && ollama pull llama3.2:3b"
    echo "Without Ollama, Rewind uses deterministic template synth."
fi

echo
echo "Done!"
echo "  Plugins     → $PLUGIN_DIR"
echo "  Config      → $CONFIG_DIR/"
echo "  Cache       → $SCRIPT_DIR/.cache/"
echo "  Indexer     → $SCRIPT_DIR/tools/rewind-indexer.py"
echo
echo "SwiftBar plugin directory set to:"
echo "  $PLUGIN_DIR"
echo

if ! pgrep -q SwiftBar; then
    echo "Starting SwiftBar…"
    open -a SwiftBar
fi
