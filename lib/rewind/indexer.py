"""Background indexer: keeps .cache/rewind-snapshot.json fresh so the plugin
opens in <50ms instead of fanning out 12 fetches on every hotkey press.

Two layers of cache:

- rewind-sources.json — per-source raw fetch results keyed by source name,
  each with `fetched_at`. Sources are re-fetched only when their TTL has
  expired (see SOURCE_TTL). Always fetched with `since = now - MAX_WINDOW_MIN*60`
  so the user can switch window without an extra round-trip.

- rewind-snapshot.json — the rendered bundle the plugin reads: signals trimmed
  to the user's current (window_min, ignore_min), merged timeline, the synth
  dict, and any FDA / browser-permission hints. Re-built from the source cache
  on every tick; synth is reused when the timeline hash hasn't changed (so the
  LLM only fires when reality actually changes).

Single-flight via fcntl.flock on REWIND_INDEXER_LOCK; concurrent calls fall
through silently when the lock is held.
"""

import contextlib
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from paths import (
    REWIND_DEMO_FLAG,
    REWIND_IGNORE,
    REWIND_INDEXER_LOCK,
    REWIND_SNAPSHOT,
    REWIND_SOURCE_CACHE,
    REWIND_WINDOW,
)

from .core import safe_result
from .synth import synthesize_llm, synthesize_template

MAX_WINDOW_MIN = 240
DEFAULT_WINDOW_MIN = 30

TIMELINE_KEYS = (
    "browser", "git", "editor", "linear", "github",
    "apps", "notes", "stickies", "slack", "meeting", "ssh",
)
SNAPSHOT_KEYS = ("clipboard", "frontmost")
LIVE_ONLY_KEYS = ("clipboard", "frontmost", "open_tabs")

# How stale each source is allowed to get before the indexer re-fetches it.
# Cheap + volatile sources tick fastest; HTTP and slow sqlite sources tick slowest.
SOURCE_TTL = {
    "frontmost": 30,
    "clipboard": 30,
    "open_tabs": 60,
    "apps":      120,
    "browser":   120,
    "editor":    120,
    "git":       120,
    "github":    300,
    "linear":    300,
    "slack":     300,
    "meeting":   300,
    "ssh":       300,
    "notes":     300,
    "stickies":  300,
    "reminders": 300,
}

# kwarg-shape: True  -> fetcher takes since_ts; False -> fetcher takes no args.
SOURCE_TAKES_SINCE = {
    "browser":   True,
    "open_tabs": False,
    "git":       True,
    "editor":    True,
    "linear":    True,
    "github":    True,
    "apps":      True,
    "notes":     True,
    "stickies":  True,
    "slack":     True,
    "meeting":   True,
    "ssh":       True,
    "reminders": False,
    "clipboard": False,
    "frontmost": False,
}


def _fetchers():
    """Lazy-import the source modules — we only pay the import cost when
    the indexer is actually fetching."""
    from .sources.apps import fetch_apps, fetch_frontmost
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

    return {
        "browser":   fetch_history,
        "open_tabs": fetch_open_tabs,
        "git":       fetch_git,
        "editor":    fetch_editor,
        "linear":    fetch_linear,
        "github":    fetch_github,
        "apps":      fetch_apps,
        "notes":     fetch_notes,
        "stickies":  fetch_stickies,
        "slack":     fetch_slack,
        "meeting":   fetch_calendar,
        "ssh":       fetch_terminal,
        "reminders": fetch_reminders,
        "clipboard": fetch_clipboard,
        "frontmost": fetch_frontmost,
    }


def get_window_minutes():
    try:
        return max(5, int(REWIND_WINDOW.read_text().strip()))
    except Exception:
        return DEFAULT_WINDOW_MIN


def get_ignore_minutes():
    try:
        val = int(REWIND_IGNORE.read_text().strip())
        return val if val > 0 else 0
    except Exception:
        return 0


def _atomic_write_json(path, data):
    """Write JSON via tmpfile+rename so the plugin can never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            with contextlib.suppress(OSError):
                os.unlink(tmp)


def _read_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


@contextlib.contextmanager
def _single_flight(wait_seconds=0):
    """Hold REWIND_INDEXER_LOCK exclusively. yields True if acquired, False otherwise.

    With wait_seconds > 0 we spin (cheap) waiting for the lock to free; with
    wait_seconds == 0 we either grab it immediately or yield False.
    """
    REWIND_INDEXER_LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(REWIND_INDEXER_LOCK, "w")
    try:
        deadline = time.time() + wait_seconds
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                yield True
                return
            except OSError:
                if time.time() >= deadline:
                    yield False
                    return
                time.sleep(0.1)
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        finally:
            f.close()


def _fetch_one(key, fetcher, since_ts):
    """Run a single fetcher (with the right arg shape) and never raise."""
    try:
        if SOURCE_TAKES_SINCE.get(key, False):
            return fetcher(since_ts)
        return fetcher()
    except Exception:
        return [] if key not in SNAPSHOT_KEYS and key != "open_tabs" else None


def _refresh_source_cache(force=False):
    """Re-fetch any source whose TTL has expired; return the full source dict.

    Source cache shape:
      {"<key>": {"fetched_at": float, "data": <list|dict|None>}}
    """
    now = time.time()
    cache = _read_json(REWIND_SOURCE_CACHE, {})
    stale = [
        k for k, ttl in SOURCE_TTL.items()
        if force or now - (cache.get(k, {}).get("fetched_at") or 0) > ttl
    ]
    if not stale:
        return cache

    fetchers = _fetchers()
    since_ts = now - MAX_WINDOW_MIN * 60
    with ThreadPoolExecutor(max_workers=min(12, len(stale))) as ex:
        futures = {
            k: ex.submit(_fetch_one, k, fetchers[k], since_ts) for k in stale
        }
        for k, fut in futures.items():
            cache[k] = {"fetched_at": now, "data": safe_result(fut) if k not in SNAPSHOT_KEYS and k != "open_tabs" else fut.result()}

    _atomic_write_json(REWIND_SOURCE_CACHE, cache)
    return cache


def _signals_from_cache(cache, window_min, ignore_min):
    """Build the trimmed signals dict the plugin expects, from the raw source cache."""
    from .sources.apps import fetch_app_at, merge_frontmost_into_apps

    now = time.time()
    until_ts = now - ignore_min * 60
    since_ts = until_ts - window_min * 60

    signals = {}
    for k in (
        "browser", "git", "editor", "linear", "github", "apps",
        "notes", "stickies", "slack", "meeting", "ssh", "reminders",
    ):
        items = (cache.get(k) or {}).get("data") or []
        signals[k] = [it for it in items if since_ts <= it.get("ts", 0) <= until_ts] if k in TIMELINE_KEYS else items

    raw_tabs = (cache.get("open_tabs") or {}).get("data")
    if isinstance(raw_tabs, dict):
        signals["open_tabs"] = raw_tabs.get("tabs") or []
        signals["browser_denied"] = raw_tabs.get("denied") or []
    else:
        signals["open_tabs"] = raw_tabs if isinstance(raw_tabs, list) else []
        signals["browser_denied"] = []

    for k in SNAPSHOT_KEYS:
        val = (cache.get(k) or {}).get("data")
        signals[k] = val if isinstance(val, dict) else None

    if ignore_min > 0:
        for k in LIVE_ONLY_KEYS:
            signals[k] = None if k in SNAPSHOT_KEYS else []
        signals["browser_denied"] = []
        try:
            signals["anchor_app"] = fetch_app_at(until_ts)
        except Exception:
            signals["anchor_app"] = None
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


def _build_timeline(signals, max_generic_web=8):
    """Merge timestamped signals into one reverse-chronological list."""
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


def _timeline_hash(timeline, window_min, ignore_min):
    """Fingerprint a timeline + settings so we can skip the LLM when nothing changed."""
    sig = [(round(t.get("ts", 0)), t.get("kind"), t.get("title", ""), t.get("repo", ""))
           for t in timeline[:20]]
    h = hashlib.sha256()
    h.update(json.dumps([window_min, ignore_min, sig], separators=(",", ":")).encode())
    return h.hexdigest()


def _needs_full_disk_access():
    from .sources.apps import needs_full_disk_access as _impl
    try:
        return _impl()
    except Exception:
        return False


def tick(window_min=None, ignore_min=None, force=False, use_llm=True):
    """Run one indexer cycle. Returns the resulting snapshot dict.

    `window_min` / `ignore_min` default to the user's persisted settings.
    `force=True` re-fetches every source regardless of TTL.

    In demo mode (REWIND_DEMO_FLAG present) the tick is a no-op so the
    pre-rendered demo snapshot isn't clobbered.
    """
    if REWIND_DEMO_FLAG.exists():
        return _read_json(REWIND_SNAPSHOT, None) or _empty_snapshot(
            window_min or get_window_minutes(),
            ignore_min or get_ignore_minutes(),
        )

    if window_min is None:
        window_min = get_window_minutes()
    if ignore_min is None:
        ignore_min = get_ignore_minutes()

    with _single_flight(wait_seconds=3) as got_lock:
        if not got_lock:
            existing = _read_json(REWIND_SNAPSHOT, None)
            return existing or _empty_snapshot(window_min, ignore_min)

        cache = _refresh_source_cache(force=force)
        signals = _signals_from_cache(cache, window_min, ignore_min)
        timeline = _build_timeline(signals)
        fingerprint = _timeline_hash(timeline, window_min, ignore_min)

        prev = _read_json(REWIND_SNAPSHOT, None) or {}
        synth = None
        if (
            not force
            and prev.get("timeline_hash") == fingerprint
            and prev.get("synth")
            and prev["synth"].get("_source") == ("ollama" if use_llm else "template")
        ):
            synth = prev["synth"]

        if synth is None:
            synth = synthesize_llm(signals, timeline) if use_llm else None
            if synth is None:
                synth = synthesize_template(signals)
                synth["_source"] = "template"

        snapshot = {
            "generated_at": time.time(),
            "generated_iso": datetime.now(timezone.utc).isoformat(),
            "window_min": window_min,
            "ignore_min": ignore_min,
            "timeline_hash": fingerprint,
            "signals": signals,
            "timeline": timeline,
            "synth": synth,
            "fda_needed": _needs_full_disk_access(),
        }
        _atomic_write_json(REWIND_SNAPSHOT, snapshot)
        return snapshot


def _empty_snapshot(window_min, ignore_min):
    return {
        "generated_at": time.time(),
        "window_min": window_min,
        "ignore_min": ignore_min,
        "timeline_hash": "",
        "signals": {},
        "timeline": [],
        "synth": {
            "where": "Indexer hasn't run yet — give it a few seconds",
            "next": None, "forget": None,
            "_links": {"where": None, "next": None, "forget": None},
            "_source": "empty",
        },
        "fda_needed": False,
    }


def read_snapshot():
    """Read the current snapshot, or None if the indexer hasn't run yet / file is corrupt."""
    return _read_json(REWIND_SNAPSHOT, None)


def snapshot_age_seconds(snap):
    if not snap or not snap.get("generated_at"):
        return None
    return time.time() - snap["generated_at"]


def install_launchd():
    """Render and load the launchd plist. Returns the destination path."""
    import plistlib
    repo_root = REWIND_SNAPSHOT.parent.parent
    indexer = repo_root / "tools" / "rewind-indexer.py"
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(plist_dir, exist_ok=True)
    plist_path = os.path.join(plist_dir, "com.alembic.rewind-indexer.plist")
    plist = {
        "Label": "com.alembic.rewind-indexer",
        "ProgramArguments": [sys.executable, str(indexer), "--once"],
        "StartInterval": 30,
        "RunAtLoad": True,
        "StandardOutPath": str(repo_root / ".cache" / "rewind-indexer.log"),
        "StandardErrorPath": str(repo_root / ".cache" / "rewind-indexer.log"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "HOME": os.path.expanduser("~"),
        },
    }
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)
    os.system(f'launchctl unload "{plist_path}" 2>/dev/null')
    rc = os.system(f'launchctl load "{plist_path}"')
    return plist_path, rc == 0


def uninstall_launchd():
    plist_path = os.path.expanduser("~/Library/LaunchAgents/com.alembic.rewind-indexer.plist")
    os.system(f'launchctl unload "{plist_path}" 2>/dev/null')
    if os.path.exists(plist_path):
        os.unlink(plist_path)
    return plist_path
