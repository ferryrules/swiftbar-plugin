"""Rewind — reconstruct your recent working context after an interruption.

Each source lives in sources/<thing>.py and exposes either fetch_<thing>(since_ts)
or fetch_<thing>(). The background indexer (lib/rewind/indexer.py + tools/
rewind-indexer.py) re-fetches each source on its own TTL, writes a unified
snapshot to .cache/rewind-snapshot.json, and only re-runs the LLM synth when
the timeline hash actually changes. The SwiftBar plugin just reads the snapshot.

gather() / build_timeline() are kept for ad-hoc / test callers that want the
old "fetch-everything-now" behaviour. The plugin no longer uses them.

Privacy boundary: privacy.py + tests/test_rewind_privacy.py.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from paths import REWIND_IGNORE, REWIND_WINDOW

from . import demo
from .core import safe_result
from .indexer import (
    DEFAULT_WINDOW_MIN,
    MAX_WINDOW_MIN,
    SNAPSHOT_KEYS,
    SOURCE_TTL,
    TIMELINE_KEYS,
    install_launchd,
    read_snapshot,
    snapshot_age_seconds,
    tick,
    uninstall_launchd,
)
from .pins import delete_pin, list_pins, load_pin, save_pin
from .privacy import build_claude_payload, build_llm_payload
from .sources.apps import (
    fetch_app_at,
    fetch_apps,
    fetch_frontmost,
    merge_frontmost_into_apps,
    needs_full_disk_access,
)
from .sources.browser import fetch_history, fetch_open_tabs
from .sources.calendar import fetch_calendar
from .sources.editor import fetch_editor
from .sources.git import fetch_git
from .sources.github import fetch_github
from .sources.linear import fetch_linear
from .sources.macos_local import (
    fetch_clipboard, fetch_notes, fetch_reminders, fetch_stickies,
)
from .sources.slack import fetch_slack
from .sources.terminal import fetch_terminal
from .synth import (
    suggest_label,
    synthesize,
    synthesize_claude,
    synthesize_llm,
    synthesize_template,
    synthesize_wrapup,
)

__all__ = [
    "DEFAULT_WINDOW_MIN",
    "IGNORE_FILE",
    "MAX_WINDOW_MIN",
    "SNAPSHOT_KEYS",
    "SOURCE_TTL",
    "TIMELINE_KEYS",
    "WINDOW_FILE",
    "build_claude_payload",
    "build_llm_payload",
    "build_timeline",
    "delete_pin",
    "demo",
    "gather",
    "get_ignore_minutes",
    "get_window_minutes",
    "install_launchd",
    "list_pins",
    "load_pin",
    "needs_full_disk_access",
    "read_snapshot",
    "save_pin",
    "set_ignore_minutes",
    "set_window_minutes",
    "snapshot_age_seconds",
    "suggest_label",
    "synthesize",
    "synthesize_claude",
    "synthesize_llm",
    "synthesize_template",
    "synthesize_wrapup",
    "tick",
    "uninstall_launchd",
]

WINDOW_FILE = REWIND_WINDOW
IGNORE_FILE = REWIND_IGNORE

# Live-state keys suppressed when ignore_min > 0 (they describe right-now state).
LIVE_ONLY_KEYS = ("clipboard", "frontmost", "open_tabs")


def get_window_minutes():
    try:
        return max(5, int(WINDOW_FILE.read_text().strip()))
    except Exception:
        return DEFAULT_WINDOW_MIN


def set_window_minutes(minutes):
    try:
        WINDOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        WINDOW_FILE.write_text(str(int(minutes)))
    except Exception:
        pass


def get_ignore_minutes():
    """Minutes of recent activity to skip; 0 means 'use right now as upper bound'."""
    try:
        val = int(IGNORE_FILE.read_text().strip())
        return val if val > 0 else 0
    except Exception:
        return 0


def set_ignore_minutes(minutes):
    try:
        IGNORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        IGNORE_FILE.write_text(str(max(0, int(minutes))))
    except Exception:
        pass


def gather(window_min, ignore_min=0):
    """Run every source in parallel and return one signals dict; `ignore_min` shifts the window upper bound back to skip a recent interruption."""
    now = datetime.now(timezone.utc).timestamp()
    until_ts = now - ignore_min * 60
    since_ts = until_ts - window_min * 60
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {
            "browser":   ex.submit(fetch_history, since_ts),
            "open_tabs": ex.submit(fetch_open_tabs),
            "git":       ex.submit(fetch_git, since_ts),
            "editor":    ex.submit(fetch_editor, since_ts),
            "linear":    ex.submit(fetch_linear, since_ts),
            "github":    ex.submit(fetch_github, since_ts),
            "apps":      ex.submit(fetch_apps, since_ts),
            "notes":     ex.submit(fetch_notes, since_ts),
            "stickies":  ex.submit(fetch_stickies, since_ts),
            "slack":     ex.submit(fetch_slack, since_ts),
            "meeting":   ex.submit(fetch_calendar, since_ts),
            "ssh":       ex.submit(fetch_terminal, since_ts),
            "reminders": ex.submit(fetch_reminders),
            "clipboard": ex.submit(fetch_clipboard),
            "frontmost": ex.submit(fetch_frontmost),
        }
        signals = {}
        for k, f in futures.items():
            if k in SNAPSHOT_KEYS:
                try:
                    val = f.result()
                except Exception:
                    val = None
                signals[k] = val if isinstance(val, dict) else None
            else:
                signals[k] = safe_result(f)

    raw_tabs = signals.get("open_tabs")
    if isinstance(raw_tabs, dict):
        signals["open_tabs"] = raw_tabs.get("tabs") or []
        signals["browser_denied"] = raw_tabs.get("denied") or []
    else:
        signals["open_tabs"] = raw_tabs if isinstance(raw_tabs, list) else []
        signals["browser_denied"] = []

    if ignore_min > 0:
        for k in TIMELINE_KEYS:
            items = signals.get(k) or []
            signals[k] = [it for it in items if it.get("ts", 0) <= until_ts]
        for k in LIVE_ONLY_KEYS:
            signals[k] = None if k in SNAPSHOT_KEYS else []
        signals["browser_denied"] = []
        signals["anchor_app"] = fetch_app_at(until_ts)
    else:
        signals["anchor_app"] = None
        signals["apps"] = merge_frontmost_into_apps(
            signals.get("apps") or [], signals.get("frontmost"), ts=now
        )

    signals["_window"] = {
        "since_ts": since_ts, "until_ts": until_ts,
        "window_min": window_min, "ignore_min": ignore_min,
    }
    return signals


def build_timeline(signals, max_generic_web=8):
    """Merge timestamped signals into one reverse-chronological list, capping generic browsing so it can't bury work signals."""
    everything = []
    for key in TIMELINE_KEYS:
        items = signals.get(key) or []
        if key == "browser":
            generic = 0
            for v in items:
                if v.get("signal"):
                    everything.append(v)
                elif generic < max_generic_web:
                    everything.append(v)
                    generic += 1
        else:
            everything.extend(items)
    everything.sort(key=lambda x: -x.get("ts", 0))
    return everything
