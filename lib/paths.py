"""Single source of truth for swiftbar-dashboard paths.

Everything (config + state + cache) lives next to the plugins so it's easy
to find and edit. Don't hard-code any of these paths elsewhere — import
from this module.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
CACHE_DIR = REPO_ROOT / ".cache"
PLUGINS_DIR = REPO_ROOT / "plugins"
PRESENTATION_INDEX = REPO_ROOT / "presentation" / "index.html"

ENV_FILE = CONFIG_DIR / ".env"
PLUGINS_CONFIG_FILE = CONFIG_DIR / "plugins.json"
AUTO_HIDDEN_FILE = CONFIG_DIR / "auto-hidden.json"

SLACK_AUTH_CACHE = CACHE_DIR / "slack-auth.json"
SLACK_USERS_CACHE = CACHE_DIR / "slack-users.json"
FOCUS_STATE = CACHE_DIR / "focus.json"
SEARCH_RECENT = CACHE_DIR / "search-recent.json"
SEARCH_RESULT_HTML = CACHE_DIR / "search-results.html"
REWIND_WINDOW = CACHE_DIR / "rewind-window.txt"
REWIND_IGNORE = CACHE_DIR / "rewind-ignore.txt"
REWIND_PINS_DIR = CACHE_DIR / "rewind-pins"
REWIND_ACTIVE_PIN = CACHE_DIR / "rewind-active-pin.txt"
REWIND_SNAPSHOT = CACHE_DIR / "rewind-snapshot.json"
REWIND_SOURCE_CACHE = CACHE_DIR / "rewind-sources.json"
REWIND_INDEXER_LOCK = CACHE_DIR / "rewind-indexer.lock"
REWIND_INDEXER_LOG = CACHE_DIR / "rewind-indexer.log"
REWIND_DEMO_FLAG = CACHE_DIR / "rewind-demo.flag"
REWIND_FORGET_LEDGER = CACHE_DIR / "rewind-forget-ledger.json"


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def display_path(path):
    """Render a path relative to the repo root for user-facing messages."""
    try:
        return f"config/{Path(path).relative_to(CONFIG_DIR)}"
    except ValueError:
        try:
            return f".cache/{Path(path).relative_to(CACHE_DIR)}"
        except ValueError:
            return str(path)
