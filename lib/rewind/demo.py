"""Fake-but-realistic data for hackathon demos.

Three scenarios, each producing a complete snapshot:

- morning           : start-of-day, lots of unfinished context (approved PR, in-flight
                      ticket with a due date, recent git checkout, multiple browser tabs)
- after-meeting     : just came back from a Zoom — recent activity is meeting + Slack;
                      flipping 🙈 Ignore last 15 min pivots the synth to the real work
- quiet             : deep in a single task, minimal context-switch noise

All timestamps are relative to "now" so the snapshot always looks fresh. Synth
lines are pre-baked so the template branch produces the line you want at demo
time — no LLM round-trip required (the indexer is paused in demo mode anyway).

The plugin renders these as if they came from a live tick. Toggle from the
🎬 Demo submenu, or via `tools/rewind-indexer.py --demo morning`.
"""

import json
import time

from paths import REWIND_DEMO_FLAG, REWIND_PINS_DIR, REWIND_SNAPSHOT

# Alembic-shaped fixtures — repo names, ticket prefixes, channels, app bundles.
CAUSAL_GRAPH_PATH = "/Users/ferris.boran/src/alembic/causal_graph"
ALEMBIC_TERRAFORM_PATH = "/Users/ferris.boran/src/alembic/alembic-terraform"
ALEMBIC_CLI_PATH = "/Users/ferris.boran/src/alembic/alembic_cli"

CURSOR_BUNDLE = "com.todesktop.230313mzl4w4u92"
SLACK_BUNDLE = "com.tinyspeck.slackmacgap"
CHROME_BUNDLE = "com.google.Chrome"
ZOOM_BUNDLE = "us.zoom.xos"
ITERM_BUNDLE = "com.googlecode.iterm2"


def _link_url(url):
    return {"href": url} if url else None


def _link_app(bundle, *extra):
    return {"bash": "/usr/bin/open", "args": ["-b", bundle, *[a for a in extra if a]]}


def _ago(now, minutes):
    return now - minutes * 60


def _trim_for_ignore(items, now, ignore_min):
    """Drop items more recent than (now - ignore_min*60) — matches the real
    indexer's behaviour when ignore_min > 0."""
    if not ignore_min:
        return items
    cutoff = now - ignore_min * 60
    return [it for it in items if it.get("ts", 0) <= cutoff]


def scenario_morning(now=None, window_min=30, ignore_min=0):
    """Start of day. INF-1734 in flight, #1093 approved and waiting, CAU-892 due tomorrow.

    Demo beat: hit ⌘⇧R, audience sees three crisp actionable lines, each one a click
    away from its underlying entity.
    """
    now = now or time.time()
    git = [
        {
            "ts": _ago(now, 5), "kind": "git", "icon": "🔀",
            "title": "switched to ferrisboran/inf-1734-devpods",
            "repo": "causal_graph", "url": "",
            "repo_path": CAUSAL_GRAPH_PATH,
        },
        {
            "ts": _ago(now, 18), "kind": "git", "icon": "💾",
            "title": "committed: WIP persistence layer for devpod restarts",
            "repo": "causal_graph", "url": "",
            "repo_path": CAUSAL_GRAPH_PATH,
        },
        {
            "ts": _ago(now, 22), "kind": "git", "icon": "💾",
            "title": "committed: add migration for devpod_state table",
            "repo": "causal_graph", "url": "",
            "repo_path": CAUSAL_GRAPH_PATH,
        },
    ]
    github = [
        {
            "ts": _ago(now, 12), "kind": "pr", "icon": "🔀",
            "title": "#1093: SV11 DevPod — persistent workspace volumes",
            "url": "https://github.com/twothinkinc/causal_graph/pull/1093",
            "repo": "causal_graph",
            "review": "APPROVED", "draft": False, "branch": "ferrisboran/sv11-devpod",
        },
        {
            "ts": _ago(now, 26), "kind": "pr", "icon": "🔀",
            "title": "#889: add metrics endpoint for graph builder",
            "url": "https://github.com/twothinkinc/causal_graph/pull/889",
            "repo": "causal_graph",
            "review": "CHANGES_REQUESTED", "draft": False, "branch": "ferrisboran/metrics",
        },
        {
            "ts": _ago(now, 90), "kind": "pr", "icon": "🔀",
            "title": "#1234: refactor auth context — extract token store",
            "url": "https://github.com/twothinkinc/alembic_cli/pull/1234",
            "repo": "alembic_cli",
            "review": None, "draft": True, "branch": "ferrisboran/auth-context",
        },
    ]
    linear = [
        {
            "ts": _ago(now, 9), "kind": "ticket", "icon": "🟢",
            "title": "INF-1734: Reliable devpod persistence across restarts",
            "url": "https://linear.app/alembic/issue/INF-1734",
            "identifier": "INF-1734", "state": "In Progress", "state_type": "started",
            "priority": 1, "due": None,
        },
        {
            "ts": _ago(now, 14), "kind": "ticket", "icon": "🟢",
            "title": "CAU-892: Graph builder rejects malformed edges with cycle",
            "url": "https://linear.app/alembic/issue/CAU-892",
            "identifier": "CAU-892", "state": "In Progress", "state_type": "started",
            "priority": 2, "due": "tomorrow",
        },
        {
            "ts": _ago(now, 19), "kind": "ticket", "icon": "☐",
            "title": "DAT-203: Data classification for new event types",
            "url": "https://linear.app/alembic/issue/DAT-203",
            "identifier": "DAT-203", "state": "Todo", "state_type": "unstarted",
            "priority": 3, "due": None,
        },
    ]
    editor = [
        {
            "ts": _ago(now, 3), "kind": "editor", "icon": "💻",
            "title": "causal_graph · lib/devpods/persistence.py",
            "path": f"{CAUSAL_GRAPH_PATH}/lib/devpods/persistence.py",
            "uri": "",
        },
        {
            "ts": _ago(now, 11), "kind": "editor", "icon": "💻",
            "title": "causal_graph · tests/test_persistence.py",
            "path": f"{CAUSAL_GRAPH_PATH}/tests/test_persistence.py",
            "uri": "",
        },
    ]
    apps = [
        {"ts": _ago(now, 1), "kind": "app", "icon": "🪟",
         "title": "Cursor", "app": "Cursor", "bundle": CURSOR_BUNDLE,
         "focus_min": 32, "url": ""},
        {"ts": _ago(now, 6), "kind": "app", "icon": "🪟",
         "title": "Slack", "app": "Slack", "bundle": SLACK_BUNDLE,
         "focus_min": 8, "url": ""},
        {"ts": _ago(now, 14), "kind": "app", "icon": "🪟",
         "title": "Chrome", "app": "Chrome", "bundle": CHROME_BUNDLE,
         "focus_min": 4, "url": ""},
        {"ts": _ago(now, 20), "kind": "app", "icon": "🪟",
         "title": "iTerm", "app": "iTerm", "bundle": ITERM_BUNDLE,
         "focus_min": 2, "url": ""},
    ]
    open_tabs = [
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "#1093: SV11 DevPod · twothinkinc/causal_graph",
         "url": "https://github.com/twothinkinc/causal_graph/pull/1093",
         "domain": "github.com", "browser": "Chrome", "signal": True},
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "INF-1734: Reliable devpod persistence",
         "url": "https://linear.app/alembic/issue/INF-1734",
         "domain": "linear.app", "browser": "Chrome", "signal": True},
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "DevPod persistence design — Engineering wiki",
         "url": "https://notion.so/alembic/devpod-persistence-design",
         "domain": "notion.so", "browser": "Chrome", "signal": True},
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "Inbox (2) — ferris.boran@alembic.com",
         "url": "https://mail.google.com/mail/u/0/",
         "domain": "mail.google.com", "browser": "Chrome", "signal": False},
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "Hackathon hub — Alembic",
         "url": "https://notion.so/alembic/hackathon",
         "domain": "notion.so", "browser": "Chrome", "signal": False},
    ]
    browser = [
        {"ts": _ago(now, 4), "kind": "web", "icon": "🌐",
         "title": "twothinkinc/causal_graph PR #1093",
         "url": "https://github.com/twothinkinc/causal_graph/pull/1093",
         "domain": "github.com", "signal": True},
        {"ts": _ago(now, 10), "kind": "web", "icon": "🌐",
         "title": "INF-1734 · Linear",
         "url": "https://linear.app/alembic/issue/INF-1734",
         "domain": "linear.app", "signal": True},
        {"ts": _ago(now, 14), "kind": "web", "icon": "🌐",
         "title": "DevPod persistence design — Engineering wiki",
         "url": "https://notion.so/alembic/devpod-persistence-design",
         "domain": "notion.so", "signal": True},
        {"ts": _ago(now, 17), "kind": "web", "icon": "🌐",
         "title": "Stack Overflow — sqlite locking modes",
         "url": "https://stackoverflow.com/q/123456",
         "domain": "stackoverflow.com", "signal": False},
        {"ts": _ago(now, 22), "kind": "web", "icon": "🌐",
         "title": "Inbox — ferris.boran@alembic.com",
         "url": "https://mail.google.com/mail/u/0/",
         "domain": "mail.google.com", "signal": False},
    ]
    slack = [
        {"ts": _ago(now, 7), "kind": "slack", "icon": "💬",
         "title": "Reply from @sarah in #infra-on-call: 'devpod 003 restarted clean, ty'",
         "url": "slack://channel?team=T01&id=C0INFRA"},
        {"ts": _ago(now, 13), "kind": "slack", "icon": "💬",
         "title": "DM from @tomas: 'design doc looks good, ship it'",
         "url": "slack://user?team=T01&id=U0TOMAS"},
    ]
    meeting = [
        {"ts": _ago(now, 28), "kind": "meeting", "icon": "📅",
         "title": "Eng standup — wrapped 10:00",
         "url": "https://meet.google.com/abc-defg-hij"},
    ]
    reminders = [
        {"ts": now, "kind": "reminder", "title": "Reply to Sarah re. DevPod config",
         "claude_safe": False},
        {"ts": now, "kind": "reminder", "title": "File expense report",
         "claude_safe": False},
    ]
    clipboard = {
        "kind": "clipboard", "claude_safe": False, "chars": 67, "lines": 1,
        "text": "git rebase -i origin/main  # squash WIP commits before pushing",
    }
    frontmost = {"app": "Cursor", "bundle": CURSOR_BUNDLE,
                 "window": "persistence.py — causal_graph"}

    timeline_all = sorted(
        git + github + linear + editor + apps + slack + meeting,
        key=lambda x: -x["ts"],
    )
    timeline = _trim_for_ignore(timeline_all, now, ignore_min)

    synth = {
        "recap": (
            "You were heads-down on INF-1734 in causal_graph — just switched to "
            "ferrisboran/inf-1734-devpods and were editing lib/devpods/persistence.py. "
            "PR #1093 (SV11 DevPod) is approved and waiting, and Tomas signed off on "
            "the design doc."
        ),
        "where": "causal_graph: switched to ferrisboran/inf-1734-devpods (INF-1734)",
        "next": "Merge #1093: SV11 DevPod — it's approved",
        "forget": "CAU-892 is due tomorrow",
        "tab_classes": {
            "github.com":      "active",
            "linear.app":      "active",
            "notion.so":       "reference",
            "stackoverflow.com": "reference",
            "mail.google.com": "noise",
        },
        "_links": {
            "where": _link_app(CURSOR_BUNDLE, CAUSAL_GRAPH_PATH),
            "next": _link_url("https://github.com/twothinkinc/causal_graph/pull/1093"),
            "forget": _link_url("https://linear.app/alembic/issue/CAU-892"),
        },
        "_source": "ollama",
        "_runtime": "ollama (cloud:gpt-oss:120b) · demo",
    }

    until_ts = now - ignore_min * 60
    signals = {
        "browser": _trim_for_ignore(browser, now, ignore_min),
        "git": _trim_for_ignore(git, now, ignore_min),
        "editor": _trim_for_ignore(editor, now, ignore_min),
        "linear": _trim_for_ignore(linear, now, ignore_min),
        "github": _trim_for_ignore(github, now, ignore_min),
        "apps": _trim_for_ignore(apps, now, ignore_min),
        "notes": [], "stickies": [],
        "slack": _trim_for_ignore(slack, now, ignore_min),
        "meeting": _trim_for_ignore(meeting, now, ignore_min),
        "ssh": [],
        "reminders": [] if ignore_min else reminders,
        "open_tabs": [] if ignore_min else open_tabs,
        "browser_denied": [],
        "clipboard": None if ignore_min else clipboard,
        "frontmost": None if ignore_min else frontmost,
        "anchor_app": None,
        "_window": {"since_ts": until_ts - window_min * 60, "until_ts": until_ts,
                    "window_min": window_min, "ignore_min": ignore_min},
    }
    return _wrap_snapshot(signals, timeline, synth, now, window_min, ignore_min)


def scenario_after_meeting(now=None, window_min=30, ignore_min=0):
    """Just back from a 30-min Architecture sync. Recent activity is all meeting/Slack noise.

    Demo beat: open the menu first → synth says 'in Zoom — Architecture sync'.
    Flip 🙈 Ignore last 15 min → synth pivots to the real work (INF-1734 / causal_graph)
    from the 15–30 minute slice before the meeting.
    """
    now = now or time.time()

    meeting = [
        {"ts": _ago(now, 2), "kind": "meeting", "icon": "📅",
         "title": "Architecture sync — just wrapped (Zoom)",
         "url": "https://us02web.zoom.us/j/123456789"},
    ]
    slack = [
        {"ts": _ago(now, 3), "kind": "slack", "icon": "💬",
         "title": "Posted in #eng-foundation: 'sharing my screen now'",
         "url": "slack://channel?team=T01&id=C0ENGF"},
        {"ts": _ago(now, 4), "kind": "slack", "icon": "💬",
         "title": "DM from @lloyd: 'can you join the sync?'",
         "url": "slack://user?team=T01&id=U0LLOYD"},
        {"ts": _ago(now, 11), "kind": "slack", "icon": "💬",
         "title": "Reply in #infra-on-call: 'looking now'",
         "url": "slack://channel?team=T01&id=C0INFRA"},
    ]
    apps = [
        {"ts": _ago(now, 1), "kind": "app", "icon": "🪟",
         "title": "Zoom", "app": "Zoom", "bundle": ZOOM_BUNDLE,
         "focus_min": 28, "url": ""},
        {"ts": _ago(now, 4), "kind": "app", "icon": "🪟",
         "title": "Slack", "app": "Slack", "bundle": SLACK_BUNDLE,
         "focus_min": 6, "url": ""},
        {"ts": _ago(now, 18), "kind": "app", "icon": "🪟",
         "title": "Cursor", "app": "Cursor", "bundle": CURSOR_BUNDLE,
         "focus_min": 24, "url": ""},
    ]

    # Older signals — the work the user was on BEFORE the interruption.
    git = [
        {"ts": _ago(now, 19), "kind": "git", "icon": "🔀",
         "title": "switched to ferrisboran/inf-1734-devpods",
         "repo": "causal_graph", "url": "", "repo_path": CAUSAL_GRAPH_PATH},
        {"ts": _ago(now, 24), "kind": "git", "icon": "💾",
         "title": "committed: WIP persistence layer for devpod restarts",
         "repo": "causal_graph", "url": "", "repo_path": CAUSAL_GRAPH_PATH},
    ]
    editor = [
        {"ts": _ago(now, 20), "kind": "editor", "icon": "💻",
         "title": "causal_graph · lib/devpods/persistence.py",
         "path": f"{CAUSAL_GRAPH_PATH}/lib/devpods/persistence.py", "uri": ""},
    ]
    linear = [
        {"ts": _ago(now, 23), "kind": "ticket", "icon": "🟢",
         "title": "INF-1734: Reliable devpod persistence across restarts",
         "url": "https://linear.app/alembic/issue/INF-1734",
         "identifier": "INF-1734", "state": "In Progress", "state_type": "started",
         "priority": 1, "due": None},
    ]
    github = [
        {"ts": _ago(now, 26), "kind": "pr", "icon": "🔀",
         "title": "#1093: SV11 DevPod — persistent workspace volumes",
         "url": "https://github.com/twothinkinc/causal_graph/pull/1093",
         "repo": "causal_graph",
         "review": "APPROVED", "draft": False, "branch": "ferrisboran/sv11-devpod"},
    ]
    open_tabs = [
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "Architecture sync — Zoom",
         "url": "https://us02web.zoom.us/j/123456789",
         "domain": "zoom.us", "browser": "Chrome", "signal": False},
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "#1093: SV11 DevPod · twothinkinc/causal_graph",
         "url": "https://github.com/twothinkinc/causal_graph/pull/1093",
         "domain": "github.com", "browser": "Chrome", "signal": True},
        {"ts": now, "kind": "tab", "icon": "📑",
         "title": "INF-1734: Reliable devpod persistence",
         "url": "https://linear.app/alembic/issue/INF-1734",
         "domain": "linear.app", "browser": "Chrome", "signal": True},
    ]
    clipboard = {"kind": "clipboard", "claude_safe": False,
                 "chars": 0, "lines": 0, "text": ""}
    frontmost = {"app": "Zoom", "bundle": ZOOM_BUNDLE,
                 "window": "Architecture sync"}

    timeline_all = sorted(
        meeting + slack + apps + git + editor + linear + github,
        key=lambda x: -x["ts"],
    )
    timeline = _trim_for_ignore(timeline_all, now, ignore_min)

    # Headline pivots when the user skips past the meeting/Slack noise.
    if ignore_min >= 10:
        synth = {
            "recap": (
                "Architecture sync just wrapped — before it, you were on INF-1734 in "
                "causal_graph editing lib/devpods/persistence.py. PR #1093 is approved "
                "and Lloyd posted meeting notes in #eng-foundation while you were in "
                "the call."
            ),
            "where": "causal_graph: switched to ferrisboran/inf-1734-devpods (INF-1734)",
            "next": "Resume editing lib/devpods/persistence.py",
            "forget": "#1093 is approved and waiting to merge",
            "_links": {
                "where": _link_app(CURSOR_BUNDLE, CAUSAL_GRAPH_PATH),
                "next": _link_app(CURSOR_BUNDLE,
                                  f"{CAUSAL_GRAPH_PATH}/lib/devpods/persistence.py"),
                "forget": _link_url("https://github.com/twothinkinc/causal_graph/pull/1093"),
            },
            "_source": "ollama",
            "_runtime": "ollama (cloud:gpt-oss:120b) · demo",
        }
    else:
        synth = {
            "recap": (
                "You're still in the Zoom architecture sync. Lloyd just dropped "
                "meeting notes in #eng-foundation — INF-1734 in causal_graph was "
                "your active work before the meeting and is still mid-flight."
            ),
            "where": "in Zoom — Architecture sync",
            "next": "Skim the meeting notes Lloyd posted in #eng-foundation",
            "forget": "INF-1734 is still in progress from before the meeting",
            "_links": {
                "where": _link_app(ZOOM_BUNDLE),
                "next": {"href": "slack://channel?team=T01&id=C0ENGF"},
                "forget": _link_url("https://linear.app/alembic/issue/INF-1734"),
            },
            "_source": "ollama",
            "_runtime": "ollama (cloud:gpt-oss:120b) · demo",
        }

    until_ts = now - ignore_min * 60
    signals = {
        "browser": [], "git": _trim_for_ignore(git, now, ignore_min),
        "editor": _trim_for_ignore(editor, now, ignore_min),
        "linear": _trim_for_ignore(linear, now, ignore_min),
        "github": _trim_for_ignore(github, now, ignore_min),
        "apps": _trim_for_ignore(apps, now, ignore_min),
        "notes": [], "stickies": [],
        "slack": _trim_for_ignore(slack, now, ignore_min),
        "meeting": _trim_for_ignore(meeting, now, ignore_min),
        "ssh": [], "reminders": [],
        "open_tabs": [] if ignore_min else open_tabs,
        "browser_denied": [],
        "clipboard": None if ignore_min else clipboard,
        "frontmost": None if ignore_min else frontmost,
        "anchor_app": None,
        "_window": {"since_ts": until_ts - window_min * 60, "until_ts": until_ts,
                    "window_min": window_min, "ignore_min": ignore_min},
    }
    return _wrap_snapshot(signals, timeline, synth, now, window_min, ignore_min)


def scenario_quiet(now=None, window_min=30, ignore_min=0):
    """Heads-down, single-task. One repo, one ticket, one file. No interruptions."""
    now = now or time.time()
    git = [
        {"ts": _ago(now, 2), "kind": "git", "icon": "💾",
         "title": "committed: handle empty graph in builder",
         "repo": "causal_graph", "url": "", "repo_path": CAUSAL_GRAPH_PATH},
        {"ts": _ago(now, 8), "kind": "git", "icon": "💾",
         "title": "committed: add test for cycle detection",
         "repo": "causal_graph", "url": "", "repo_path": CAUSAL_GRAPH_PATH},
        {"ts": _ago(now, 16), "kind": "git", "icon": "💾",
         "title": "committed: extract cycle_detector module",
         "repo": "causal_graph", "url": "", "repo_path": CAUSAL_GRAPH_PATH},
    ]
    linear = [
        {"ts": _ago(now, 5), "kind": "ticket", "icon": "🟢",
         "title": "CAU-892: Graph builder rejects malformed edges with cycle",
         "url": "https://linear.app/alembic/issue/CAU-892",
         "identifier": "CAU-892", "state": "In Progress", "state_type": "started",
         "priority": 2, "due": None},
    ]
    editor = [
        {"ts": _ago(now, 1), "kind": "editor", "icon": "💻",
         "title": "causal_graph · lib/builder/cycle_detector.py",
         "path": f"{CAUSAL_GRAPH_PATH}/lib/builder/cycle_detector.py", "uri": ""},
        {"ts": _ago(now, 12), "kind": "editor", "icon": "💻",
         "title": "causal_graph · tests/test_cycle_detector.py",
         "path": f"{CAUSAL_GRAPH_PATH}/tests/test_cycle_detector.py", "uri": ""},
    ]
    apps = [
        {"ts": _ago(now, 1), "kind": "app", "icon": "🪟",
         "title": "Cursor", "app": "Cursor", "bundle": CURSOR_BUNDLE,
         "focus_min": 45, "url": ""},
        {"ts": _ago(now, 28), "kind": "app", "icon": "🪟",
         "title": "iTerm", "app": "iTerm", "bundle": ITERM_BUNDLE,
         "focus_min": 8, "url": ""},
    ]
    clipboard = {"kind": "clipboard", "claude_safe": False,
                 "chars": 42, "lines": 1,
                 "text": "pytest tests/test_cycle_detector.py -v"}
    frontmost = {"app": "Cursor", "bundle": CURSOR_BUNDLE,
                 "window": "cycle_detector.py — causal_graph"}

    timeline_all = sorted(git + linear + editor + apps, key=lambda x: -x["ts"])
    timeline = _trim_for_ignore(timeline_all, now, ignore_min)

    synth = {
        "recap": (
            "Heads-down on CAU-892 in causal_graph — three quick commits on the "
            "cycle-detector extraction, latest covering the empty-graph branch. "
            "Cursor's been your only active app for the last 45 minutes."
        ),
        "where": "causal_graph: committed handle empty graph in builder (CAU-892)",
        "next": "Run pytest tests/test_cycle_detector.py -v",
        "forget": None,
        "_links": {
            "where": _link_app(CURSOR_BUNDLE, CAUSAL_GRAPH_PATH),
            "next": _link_app(ITERM_BUNDLE),
            "forget": None,
        },
        "_source": "ollama",
        "_runtime": "ollama (cloud:gpt-oss:120b) · demo",
    }

    until_ts = now - ignore_min * 60
    signals = {
        "browser": [], "git": _trim_for_ignore(git, now, ignore_min),
        "editor": _trim_for_ignore(editor, now, ignore_min),
        "linear": _trim_for_ignore(linear, now, ignore_min),
        "github": [], "apps": _trim_for_ignore(apps, now, ignore_min),
        "notes": [], "stickies": [], "slack": [], "meeting": [], "ssh": [],
        "reminders": [], "open_tabs": [], "browser_denied": [],
        "clipboard": None if ignore_min else clipboard,
        "frontmost": None if ignore_min else frontmost,
        "anchor_app": None,
        "_window": {"since_ts": until_ts - window_min * 60, "until_ts": until_ts,
                    "window_min": window_min, "ignore_min": ignore_min},
    }
    return _wrap_snapshot(signals, timeline, synth, now, window_min, ignore_min)


SCENARIOS = {
    "morning": ("Morning · INF-1734 in flight, #1093 approved", scenario_morning),
    "after-meeting": ("After meeting · Zoom-heavy recent, real work behind it", scenario_after_meeting),
    "quiet": ("Quiet · heads-down on CAU-892", scenario_quiet),
}


def _wrap_snapshot(signals, timeline, synth, now, window_min, ignore_min):
    return {
        "generated_at": now,
        "generated_iso": "",
        "window_min": window_min,
        "ignore_min": ignore_min,
        "timeline_hash": "demo",
        "signals": signals,
        "timeline": timeline,
        "synth": synth,
        "fda_needed": False,
        "_demo": True,
    }


# Pre-fab pinned moments — drop into .cache/rewind-pins/ via --seed-demo-pins.
def demo_pins(now=None):
    """Three pins seeded at plausibly-recent timestamps so the menu reads naturally."""
    now = now or time.time()
    morning_snap = scenario_morning(_ago(now, 45))
    after_snap = scenario_after_meeting(_ago(now, 110))
    quiet_snap = scenario_quiet(_ago(now, 8 * 60))

    return [
        (
            f"{int(now - 45 * 60)}-before-standup.json",
            {
                "label": "before standup — INF-1734 mid-edit",
                "ts": now - 45 * 60,
                "window_min": 30, "ignore_min": 0,
                "synth": morning_snap["synth"],
                "timeline": morning_snap["timeline"][:15],
            },
        ),
        (
            f"{int(now - 110 * 60)}-pre-arch-sync.json",
            {
                "label": "before Architecture sync",
                "ts": now - 110 * 60,
                "window_min": 30, "ignore_min": 0,
                "synth": after_snap["synth"],
                "timeline": after_snap["timeline"][:15],
            },
        ),
        (
            f"{int(now - 8 * 60 * 60)}-yesterday-eod.json",
            {
                "label": "yesterday EOD — CAU-892 deep work",
                "ts": now - 8 * 60 * 60,
                "window_min": 30, "ignore_min": 0,
                "synth": quiet_snap["synth"],
                "timeline": quiet_snap["timeline"][:15],
            },
        ),
    ]


def write_snapshot(snapshot):
    """Write `snapshot` to REWIND_SNAPSHOT atomically (same pattern as the indexer)."""
    import os
    import tempfile
    REWIND_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=REWIND_SNAPSHOT.name + ".",
                               suffix=".tmp", dir=str(REWIND_SNAPSHOT.parent))
    with os.fdopen(fd, "w") as f:
        json.dump(snapshot, f, separators=(",", ":"))
    os.replace(tmp, REWIND_SNAPSHOT)


def enable(scenario, window_min=30, ignore_min=0):
    """Flip on demo mode and write the requested scenario's snapshot."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r} (choices: {sorted(SCENARIOS)})")
    snap = SCENARIOS[scenario][1](window_min=window_min, ignore_min=ignore_min)
    write_snapshot(snap)
    REWIND_DEMO_FLAG.parent.mkdir(parents=True, exist_ok=True)
    REWIND_DEMO_FLAG.write_text(scenario)


def refresh(window_min=None, ignore_min=None):
    """Re-render the active scenario at new window/ignore settings. No-op if demo
    mode is off. Returns the scenario name on success, None otherwise."""
    scenario = active_scenario()
    if not scenario or scenario not in SCENARIOS:
        return None
    fn = SCENARIOS[scenario][1]
    snap = fn(window_min=window_min or 30, ignore_min=ignore_min or 0)
    write_snapshot(snap)
    return scenario


def disable():
    """Turn off demo mode so the indexer resumes overwriting the snapshot."""
    try:
        REWIND_DEMO_FLAG.unlink()
    except FileNotFoundError:
        pass


def active_scenario():
    """Return the active demo scenario name, or None when demo mode is off."""
    try:
        return REWIND_DEMO_FLAG.read_text().strip() or None
    except FileNotFoundError:
        return None


def seed_pins():
    """Write the three demo pins to REWIND_PINS_DIR; returns the list of filenames."""
    REWIND_PINS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for fname, payload in demo_pins():
        (REWIND_PINS_DIR / fname).write_text(json.dumps(payload))
        written.append(fname)
    return written


def unseed_pins():
    """Remove only the pins this module created (by filename suffix)."""
    if not REWIND_PINS_DIR.exists():
        return 0
    removed = 0
    for p in REWIND_PINS_DIR.glob("*.json"):
        if p.name.endswith(("-before-standup.json", "-pre-arch-sync.json",
                            "-yesterday-eod.json")):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
