"""Per-plugin display config + SwiftBar control helpers.

Single source of truth: <repo>/config/plugins.json mapping plugin slug ->
"full" or "compact". The "hidden" state is owned by SwiftBar's own
DisabledPlugins preference, which we toggle via the swiftbar:// URL scheme.
"""

import json
import os
import subprocess

from paths import AUTO_HIDDEN_FILE, CONFIG_DIR, PLUGINS_CONFIG_FILE, PLUGINS_DIR

CONFIG_FILE = PLUGINS_CONFIG_FILE

SWIFTBAR_BUNDLE = "com.ameba.SwiftBar"

# Plugin slug -> filename glob. The actual filename is resolved at runtime
# (see _plugin_filename below) so renaming `foo.10m.py` → `foo.5m.py` Just
# Works without code edits.
REGISTRY = {
    "github-prs":     "github-prs.*.py",
    "linear-tickets": "linear-tickets.*.py",
    "slack":          "slack.*.py",
    "search":         "search.*.py",
    "calendar":       "calendar.*.py",
    "git-wip":        "git-wip.*.py",
    "cursor-recent":  "cursor-recent.*.py",
    "focus":          "focus.*.py",
    "rewind":         "rewind.*.py",
}

PLUGIN_LABELS = {
    "github-prs":     "GitHub PRs",
    "linear-tickets": "Linear Tickets",
    "slack":          "Slack",
    "search":         "Doc Search",
    "calendar":       "Calendar",
    "git-wip":        "Git WIP",
    "cursor-recent":  "Recent Projects",
    "focus":          "Focus Timer",
    "rewind":         "Rewind",
}

VALID_MODES = ("full", "compact")

# Plugins that auto-hide from the menubar when their state is "empty"
AUTO_HIDE_DEFAULT = {"git-wip", "calendar", "slack"}


def _plugin_filename(slug):
    """Resolve a slug to its on-disk filename. None if no matching file exists."""
    pattern = REGISTRY.get(slug)
    if not pattern:
        return None
    matches = sorted(PLUGINS_DIR.glob(pattern))
    return matches[0].name if matches else None


def _load():
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def _save(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))


def get_mode(slug):
    """Return 'full' or 'compact' (defaults to 'full')."""
    mode = _load().get(slug, "full")
    return mode if mode in VALID_MODES else "full"


def set_mode(slug, mode):
    if mode not in VALID_MODES:
        raise ValueError(f"bad mode: {mode}")
    data = _load()
    data[slug] = mode
    _save(data)


def is_compact(slug):
    return get_mode(slug) == "compact"


def disabled_plugins():
    """Read SwiftBar's DisabledPlugins list (filenames)."""
    try:
        proc = subprocess.run(
            ["defaults", "read", SWIFTBAR_BUNDLE, "DisabledPlugins"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return set()
    if proc.returncode != 0:
        return set()
    names = set()
    for line in proc.stdout.splitlines():
        line = line.strip().rstrip(",").strip('"').strip("'")
        if line and line not in ("(", ")"):
            names.add(line)
    return names


def is_hidden(slug):
    name = _plugin_filename(slug)
    return bool(name) and name in disabled_plugins()


def _swiftbar_url(action, name):
    subprocess.run(
        ["open", "-g", f"swiftbar://{action}?name={name}"],
        check=False,
    )


def enable(slug):
    name = _plugin_filename(slug)
    if name:
        _swiftbar_url("enableplugin", name)


def disable(slug):
    name = _plugin_filename(slug)
    if name:
        _swiftbar_url("disableplugin", name)


def refresh(slug):
    name = _plugin_filename(slug)
    if name:
        _swiftbar_url("refreshplugin", name)


def refresh_all():
    subprocess.run(["open", "-g", "swiftbar://refreshallplugins"], check=False)


# ----- Auto-hide tracking -----
# A plugin is "auto-hidden" when it disabled itself because its state was empty.
# Distinct from a user-initiated Hide via the control center; this set tracks
# only the auto-disabled plugins so the control center can re-enable them when
# they have content again.


def is_auto_hide_eligible(slug):
    return slug in AUTO_HIDE_DEFAULT


def _load_auto_hidden_set():
    if not AUTO_HIDDEN_FILE.exists():
        return set()
    try:
        return set(json.loads(AUTO_HIDDEN_FILE.read_text()))
    except Exception:
        return set()


def _save_auto_hidden_set(slugs):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_HIDDEN_FILE.write_text(json.dumps(sorted(slugs)))


def is_auto_hidden(slug):
    return slug in _load_auto_hidden_set()


def mark_auto_hidden(slug, hidden):
    s = _load_auto_hidden_set()
    if hidden:
        s.add(slug)
    else:
        s.discard(slug)
    _save_auto_hidden_set(s)


def auto_hide_when_empty(slug, empty):
    """Plugin-side: disable self if empty, clear marker if not."""
    if not is_auto_hide_eligible(slug):
        return
    if empty:
        disable(slug)
        mark_auto_hidden(slug, True)
    elif is_auto_hidden(slug):
        mark_auto_hidden(slug, False)


def update_auto_hide():
    """Control-center-side: probe each auto-hidden plugin; re-enable if it
    no longer reports empty."""
    auto_hidden = _load_auto_hidden_set()
    for slug in list(auto_hidden):
        plugin_name = _plugin_filename(slug)
        if not plugin_name:
            mark_auto_hidden(slug, False)
            continue
        plugin_path = PLUGINS_DIR / plugin_name
        try:
            probe_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            result = subprocess.run(
                ["python3", str(plugin_path), "--probe"],
                capture_output=True, text=True, timeout=15, check=False,
                env=probe_env,
            )
        except Exception:
            continue
        empty = (result.returncode == 0)
        if not empty:
            enable(slug)
            mark_auto_hidden(slug, False)
