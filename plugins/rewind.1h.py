#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Rewind</bitbar.title>
# <bitbar.version>v2.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Reconstruct your working context after an interruption</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.shortcut>cmd+shift+r</swiftbar.shortcut>

import json
import os
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import is_compact
from dashboard import print_footer, sanitize
from paths import (
    FOCUS_STATE,
    PRESENTATION_INDEX,
    REWIND_ACTIVE_PIN,
    REWIND_DEMO_FLAG,
    REWIND_FORGET_LEDGER,
    REWIND_IGNORE,
    REWIND_INDEXER_LOG,
    REWIND_SNAPSHOT,
    REWIND_WINDOW,
)
from style import HEX_BLUE, HEX_DIM, HEX_GREEN, HEX_MUTED, HEX_TEXT, HEX_WARN

PLUGIN_PATH = os.path.abspath(__file__)
INDEXER_PATH = str(Path(__file__).resolve().parent.parent / "tools" / "rewind-indexer.py")
WRAPUP_PATH = str(Path(__file__).resolve().parent.parent / "tools" / "rewind-wrapup.py")
SLUG = "rewind"
CURSOR_BUNDLE = "com.todesktop.230313mzl4w4u92"

WINDOW_CHOICES = [15, 30, 60, 120, 240]
IGNORE_CHOICES = [0, 5, 10, 15, 30, 60]
STALE_SECONDS = 90


def fmt_ago(ts):
    secs = int(datetime.now(timezone.utc).timestamp() - ts)
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    rem = mins % 60
    return f"{hours}h{rem}m ago" if rem else f"{hours}h ago"


def kind_color(kind):
    return {
        "pr": HEX_BLUE, "ticket": "#a371f7", "git": HEX_GREEN,
        "editor": HEX_TEXT, "web": HEX_MUTED, "tab": HEX_BLUE,
        "app": "#79c0ff", "note": "#e3b341", "sticky": "#e3b341",
        "slack": "#a371f7", "meeting": "#f0883e", "ssh": "#3fb950",
    }.get(kind, HEX_MUTED)


def _link_attrs(link):
    """Convert a synth link descriptor into SwiftBar key=value attrs."""
    if not link:
        return ""
    if link.get("href"):
        return f"href={link['href']}"
    if link.get("bash"):
        parts = [f"bash={link['bash']}"]
        for i, a in enumerate(link.get("args") or [], 1):
            parts.append(f"param{i}='{a}'")
        parts.append("terminal=false")
        parts.append("refresh=false")
        return " ".join(parts)
    return ""


FORGET_DEBOUNCE_SEC = 300
FORGET_ESCALATE_AT = 3
FORGET_LEDGER_TTL_SEC = 7 * 24 * 3600


def _fingerprint_forget(text):
    """Stable identifier for a forget line so we can track it across snapshots.
    Prefers ticket IDs (PROJ-123) → PR numbers (#456) → first 60 chars of text."""
    if not text:
        return None
    m = re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", text)
    if m:
        return m.group(0)
    m = re.search(r"#(\d+)", text)
    if m:
        return f"#{m.group(1)}"
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return norm[:60] or None


def _read_forget_ledger():
    try:
        return json.loads(REWIND_FORGET_LEDGER.read_text())
    except Exception:
        return {}


def _write_forget_ledger(ledger):
    try:
        REWIND_FORGET_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        REWIND_FORGET_LEDGER.write_text(json.dumps(ledger))
    except Exception:
        pass


def _bump_forget_ledger(fingerprint):
    """Bump the seen-count for `fingerprint` (debounced). Also gc-s stale entries.
    Returns the entry's count after bumping (0 if no fingerprint)."""
    if not fingerprint:
        return 0
    now = time.time()
    ledger = _read_forget_ledger()

    cutoff = now - FORGET_LEDGER_TTL_SEC
    ledger = {k: v for k, v in ledger.items()
              if isinstance(v, dict) and v.get("last_seen", 0) >= cutoff}

    entry = ledger.get(fingerprint, {"first_seen": now, "last_seen": 0, "count": 0})
    if now - entry.get("last_seen", 0) >= FORGET_DEBOUNCE_SEC:
        entry["count"] = entry.get("count", 0) + 1
        entry["last_seen"] = now
        entry.setdefault("first_seen", now)
        ledger[fingerprint] = entry
        _write_forget_ledger(ledger)
    return entry.get("count", 0)


def _ack_forget(fingerprint):
    if not fingerprint:
        return
    ledger = _read_forget_ledger()
    if fingerprint in ledger:
        del ledger[fingerprint]
        _write_forget_ledger(ledger)


FOCUS_DURATIONS = [(25, "focus"), (50, "deep work")]


def _focus_active():
    """True iff a focus timer is currently running (state file exists, end_at in future)."""
    try:
        data = json.loads(FOCUS_STATE.read_text())
        end_at = datetime.fromisoformat(data["end_at"])
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
        return end_at > datetime.now(timezone.utc)
    except Exception:
        return False


def _focus_script():
    """Locate focus.NN.py — checks plugins/ first, then plugin_library/."""
    here = Path(__file__).resolve().parent
    for d in (here, here.parent / "plugin_library"):
        if not d.exists():
            continue
        matches = sorted(d.glob("focus.*.py"))
        if matches:
            return matches[0]
    return None


def render_focus_suggestion(synth):
    """One-click 'start a focus timer on the next action'. Hidden when a timer
    is already running, when synth has no next action, or when the focus
    plugin can't be located."""
    nxt = (synth or {}).get("next")
    if not nxt or _focus_active():
        return
    focus = _focus_script()
    if not focus:
        return
    label = sanitize(nxt, 40)
    arg_label = label.replace("'", "\u2019")
    print(f"🎯 Focus on: {label} | size=12 color={HEX_GREEN}")
    for minutes, kind in FOCUS_DURATIONS:
        print(f"--Start {minutes}-min {kind} | bash='{focus}' param1=start param2='{arg_label}' param3={minutes} terminal=false refresh=true")
    print("---")


def render_recap(synth):
    """LLM-only narrative paragraph. Hidden when Ollama is unreachable
    (template synth never sets `recap`)."""
    recap = (synth or {}).get("recap")
    if not recap:
        return
    print(f"📖 Recap | size=11 color={HEX_MUTED}")
    for line in textwrap.wrap(recap, width=68):
        print(f"{line} | color={HEX_TEXT} size=12")
    print("---")


def render_synth(synth):
    src = (synth or {}).get("_source")
    runtime = (synth or {}).get("_runtime") or ""
    if src == "ollama":
        src_tag = " · cloud AI" if "cloud" in runtime else " · local AI"
    elif src == "empty":
        src_tag = " · warming up"
    else:
        src_tag = ""
    print(f"Re-entry{src_tag} | size=11 color={HEX_MUTED}")

    links = (synth or {}).get("_links") or {}

    if (synth or {}).get("where"):
        print(f"📍 Where you were | color={HEX_MUTED} size=12")
        attrs = _link_attrs(links.get("where"))
        print(f"{sanitize(synth['where'], 75)} | color={HEX_TEXT} {attrs}".rstrip())
    if (synth or {}).get("next"):
        print(f"→ Next action | color={HEX_MUTED} size=12")
        attrs = _link_attrs(links.get("next"))
        print(f"{sanitize(synth['next'], 75)} | color={HEX_GREEN} {attrs}".rstrip())
    if (synth or {}).get("forget"):
        forget = synth["forget"]
        attrs = _link_attrs(links.get("forget"))
        fp = _fingerprint_forget(forget)
        count = _bump_forget_ledger(fp) if fp else 0
        escalated = count >= FORGET_ESCALATE_AT
        header = "⚠️ Don't forget"
        if escalated:
            header += f" · seen {count}× — still ignored"
        print(f"{header} | color={HEX_MUTED} size=12")
        line_color = "#f0883e" if escalated else HEX_WARN
        print(f"{sanitize(forget, 75)} | color={line_color} {attrs}".rstrip())
        if escalated and fp:
            print(f"--✓ Mark handled | bash='{PLUGIN_PATH}' param1=forget-ack param2='{fp}' terminal=false refresh=true color={HEX_MUTED}")


TIMELINE_GROUPS = [
    ("Code", "💻", {"git", "editor"}),
    ("Pull Requests", "🔀", {"pr"}),
    ("Tickets", "📋", {"ticket"}),
    ("Slack", "💬", {"slack"}),
    ("Meetings", "📅", {"meeting"}),
    ("Web", "🌐", {"web"}),
    ("Notes", "📝", {"note", "sticky"}),
    ("SSH", "🛰️", {"ssh"}),
    ("Apps", "🪟", {"app"}),
]


def _timeline_item_action(s):
    """Return the SwiftBar params suffix that makes a timeline row clickable
    (or '' if there's no sensible target).

    Priority: explicit url → app bundle → editor path / workspace URI → git
    repo path → app fallback by name.
    """
    kind = s.get("kind")
    if s.get("url"):
        return f"href={s['url']}"
    if kind == "app" and s.get("bundle"):
        return f"bash=/usr/bin/open param1=-b param2={s['bundle']} terminal=false refresh=false"
    if kind == "editor":
        path = s.get("path")
        if path:
            return f"bash=/usr/bin/open param1=-b param2={CURSOR_BUNDLE} param3='{path}' terminal=false refresh=false"
        uri = s.get("uri")
        if uri:
            return f"href={uri}"
    if kind == "git" and s.get("repo_path"):
        return f"bash=/usr/bin/open param1=-b param2={CURSOR_BUNDLE} param3='{s['repo_path']}' terminal=false refresh=false"
    if kind == "app" and s.get("app"):
        return f"bash=/usr/bin/open param1=-a param2='{s['app']}' terminal=false refresh=false"
    return ""


def _print_timeline_item(s, indent=""):
    ago = fmt_ago(s["ts"])
    icon = s.get("icon", "·")
    title = sanitize(s.get("title", ""), 60)
    repo = s.get("repo", "")
    tail = f"  · {repo}" if repo else ""
    focus_min = s.get("focus_min") or 0
    if s.get("kind") == "app" and focus_min >= 3:
        tail = f"  · {focus_min}m focused"
    color = kind_color(s.get("kind"))
    line = f"{indent}{icon} {title}{tail}  · {ago}"
    action = _timeline_item_action(s)
    suffix = f" {action} color={color}" if action else f" color={color}"
    print(f"{line} |{suffix}")


def render_timeline(timeline, window_min, ignore_min=0, group_cap=12, pinned=False):
    if pinned:
        count = f"{len(timeline)} event" + ("" if len(timeline) == 1 else "s")
        header = f"📌 Pinned timeline · {count}"
    elif ignore_min:
        header = f"Timeline · {window_min} min before {ignore_min}m ago ({len(timeline)})"
    else:
        header = f"Timeline · last {window_min} min ({len(timeline)})"
    print(f"{header} | size=11 color={HEX_MUTED}")
    if not timeline:
        print(f"No activity in this window | color={HEX_DIM}")
        return

    # Bucket events by kind, preserving the input order (which is already
    # recency-desc from the indexer).
    buckets = []
    for label, icon, kinds in TIMELINE_GROUPS:
        items = [s for s in timeline if s.get("kind") in kinds]
        if items:
            buckets.append((label, icon, items))
    known = {k for _, _, ks in TIMELINE_GROUPS for k in ks}
    other = [s for s in timeline if s.get("kind") not in known]
    if other:
        buckets.append(("Other", "·", other))

    # Most-recently-active group first, so the freshest context is at the top.
    buckets.sort(key=lambda b: -max(it["ts"] for it in b[2]))

    for label, icon, items in buckets:
        latest_ago = fmt_ago(items[0]["ts"])
        count = f"{len(items)} event" + ("" if len(items) == 1 else "s")
        print(f"{icon} {label} · {count} · last {latest_ago} | color={HEX_MUTED}")
        for s in items[:group_cap]:
            _print_timeline_item(s, indent="--")
        if len(items) > group_cap:
            print(f"--… +{len(items) - group_cap} more | color={HEX_DIM}")


def render_open_tabs(signals, synth=None):
    """Tabs that are open AND were visited within the active window.
    Cross-refs `open_tabs` (currently open) with `browser` (window-filtered
    history). Each surviving tab is annotated with its last-visit time, then
    bucketed by `synth.tab_classes` (LLM-classified, domain-keyed) into
    active / reference / noise — noise collapses into a submenu."""
    tabs = signals.get("open_tabs") or []
    if not tabs:
        return

    last_visit = {}
    for h in signals.get("browser") or []:
        url, ts = h.get("url"), h.get("ts")
        if url and ts and ts > last_visit.get(url, 0):
            last_visit[url] = ts

    tabs = [t for t in tabs if t.get("url") in last_visit]
    if not tabs:
        return
    tabs.sort(key=lambda t: -last_visit.get(t.get("url"), 0))

    classes = (synth or {}).get("tab_classes") or {}

    def _class(t):
        cls = classes.get((t.get("domain") or "").lower())
        if cls in ("active", "reference", "noise"):
            return cls
        return "active" if t.get("signal") else "reference"

    bucketed = {"active": [], "reference": [], "noise": []}
    for t in tabs:
        bucketed[_class(t)].append(t)

    visible = bucketed["active"] + bucketed["reference"]
    if not visible and not bucketed["noise"]:
        return

    print("---")
    print(f"📑 Open tabs · touched recently ({len(tabs)}) | size=11 color={HEX_MUTED}")

    def _render_row(t, indent=""):
        title = sanitize(t.get("title", "") or t.get("domain", ""), 60)
        domain = t.get("domain") or ""
        marker = "★ " if t.get("signal") else ""
        ago = fmt_ago(last_visit[t["url"]])
        line = f"{indent}{marker}{title}  · {domain}  · {ago}"
        color = HEX_BLUE if t.get("signal") else HEX_TEXT
        print(f"{line} | href={t['url']} color={color}")

    for t in visible[:12]:
        _render_row(t)
    if len(visible) > 12:
        print(f"… +{len(visible) - 12} more | color={HEX_DIM}")

    if bucketed["noise"]:
        n = len(bucketed["noise"])
        print(f"🙈 Hidden noise ({n}) | size=11 color={HEX_DIM}")
        for t in bucketed["noise"][:12]:
            _render_row(t, indent="--")


def render_closed_tabs(signals):
    """Pages visited inside the active window that aren't currently open tabs.

    Catches the case where you finished with a doc, closed it, but want to
    re-find it. Domains in SIGNAL_DOMAINS (work tools) are pinned to the top."""
    history = signals.get("browser") or []
    if not history:
        return

    open_urls = {t.get("url") for t in (signals.get("open_tabs") or []) if t.get("url")}

    latest = {}
    for h in history:
        url = h.get("url")
        if not url or url in open_urls:
            continue
        prev = latest.get(url)
        if not prev or (h.get("ts") or 0) > (prev.get("ts") or 0):
            latest[url] = h

    closed = sorted(latest.values(), key=lambda h: -(h.get("ts") or 0))
    closed.sort(key=lambda h: (0 if h.get("signal") else 1))
    if not closed:
        return

    print(f"📕 Closed tabs · visited & closed ({len(closed)}) | size=11 color={HEX_MUTED}")
    for h in closed[:25]:
        title = sanitize(h.get("title", "") or h.get("domain", ""), 60)
        domain = h.get("domain") or ""
        marker = "★ " if h.get("signal") else ""
        ago = fmt_ago(h.get("ts") or 0)
        color = HEX_BLUE if h.get("signal") else HEX_TEXT
        print(f"--{marker}{title}  · {domain}  · {ago} | href={h['url']} color={color}")
    if len(closed) > 25:
        print(f"--… +{len(closed) - 25} more | color={HEX_DIM}")


def render_browser_permission(denied):
    if not denied:
        return
    apps = ", ".join(denied)
    print("---")
    print(f"⚠️ Can't read {apps} tabs · permission needed | color={HEX_WARN}")
    print("--Grant SwiftBar automation access for your browser, then refresh | size=11 color=#8b949e")
    print("--Open Privacy & Security › Automation | href=x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")


def render_open_items(signals):
    reminders = signals.get("reminders") or []
    if reminders:
        print("---")
        print(f"☑️ Still open ({len(reminders)}) | size=11 color={HEX_MUTED}")
        for r in reminders[:6]:
            print(f"○ {sanitize(r['title'], 60)} | color={HEX_TEXT} href=x-apple-reminderkit://")


def render_clipboard(signals):
    clip = signals.get("clipboard")
    if not isinstance(clip, dict) or not clip.get("text"):
        return
    print("---")
    meta = f"{clip['chars']} chars" + (f", {clip['lines']} lines" if clip.get("lines", 1) > 1 else "")
    print(f"📋 On your clipboard · {meta} | size=11 color={HEX_MUTED}")
    print(f"{sanitize(clip['text'], 70)} | color={HEX_DIM}")


def render_window_switcher(window_min, ignore_min):
    print(f"⏱ Rewind further | size=11 color={HEX_MUTED}")
    for choice in WINDOW_CHOICES:
        label = f"{choice} min" if choice < 60 else (f"{choice // 60} hr" + ("s" if choice >= 120 else ""))
        selected = choice == window_min
        dot = "●" if selected else "○"
        color = HEX_GREEN if selected else HEX_TEXT
        print(f"{dot}  {label} | bash='{PLUGIN_PATH}' param1=window param2={choice} terminal=false refresh=true color={color}")

    print(f"🙈 Ignore last… | size=12 color={HEX_MUTED}")
    print(f"--Skip the most recent activity (e.g. an interruption) | size=11 color={HEX_DIM}")
    for choice in IGNORE_CHOICES:
        label = "off" if choice == 0 else (f"{choice} min" if choice < 60 else "1 hr")
        mark = " ✓" if choice == ignore_min else ""
        print(f"--{label}{mark} | bash='{PLUGIN_PATH}' param1=ignore param2={choice} terminal=false refresh=true")


def render_wrapup_action():
    print("---")
    print(f"📓 Wrap up today | bash={sys.executable} param1='{WRAPUP_PATH}' terminal=false refresh=false")
    print(f"--…since 9am | bash={sys.executable} param1='{WRAPUP_PATH}' param2=--start-hour param3=9 terminal=false refresh=false")
    print(f"--…last 4 hours | bash={sys.executable} param1='{WRAPUP_PATH}' param2=--since-min param3=240 terminal=false refresh=false")


def render_pin_actions(active_pin_name):
    print("---")
    if active_pin_name:
        print(f"📌 Viewing pinned moment | color={HEX_WARN} size=12")
        print(f"--Back to live | bash='{PLUGIN_PATH}' param1=pin-clear terminal=false refresh=true")
    else:
        print(f"📌 Pin this moment… | bash='{PLUGIN_PATH}' param1=pin-prompt terminal=false refresh=true")

    from rewind import list_pins
    pins = list_pins()
    if pins:
        print(f"📁 Pinned moments ({len(pins)}) | size=12 color={HEX_MUTED}")
        for p in pins[:12]:
            label = sanitize(p.get("label") or "(unlabeled)", 50)
            when = datetime.fromtimestamp(p.get("ts", 0)).strftime("%b %-d, %-I:%M %p")
            active = p.get("_filename") == active_pin_name
            mark = " ✓" if active else ""
            print(f"--{label}{mark} · {when} | bash='{PLUGIN_PATH}' param1=pin-set param2='{p['_filename']}' terminal=false refresh=true")
            print(f"----Delete | bash='{PLUGIN_PATH}' param1=pin-delete param2='{p['_filename']}' terminal=false refresh=true color={HEX_WARN}")


def render_indexer_controls(snapshot, age):
    print("---")
    print(f"⚙️ Indexer | size=12 color={HEX_MUTED}")
    if age is None:
        print(f"--Status: no snapshot yet | color={HEX_WARN}")
    else:
        mark = HEX_GREEN if age < STALE_SECONDS else HEX_WARN
        print(f"--Updated {int(age)}s ago | color={mark}")
    src = (snapshot.get("synth") or {}).get("_source") or "?"
    print(f"--Synth source: {src} | color={HEX_DIM}")
    print(f"--Re-index now | bash='{PLUGIN_PATH}' param1=reindex terminal=false refresh=true")
    print(f"--Force re-fetch all sources | bash='{PLUGIN_PATH}' param1=reindex param2=force terminal=false refresh=true")
    print(f"--View indexer log | bash=/usr/bin/open param1='{REWIND_INDEXER_LOG}' terminal=false refresh=false")
    print(f"--Install launchd agent (every 30s) | bash={sys.executable} param1='{INDEXER_PATH}' param2=--install-launchd terminal=true refresh=true")


def render_demo_controls(active_scenario):
    from rewind import demo
    if active_scenario:
        label = demo.SCENARIOS.get(active_scenario, ("(unknown)",))[0]
        print(f"🎬 Demo mode · {label} | size=12 color={HEX_WARN}")
    else:
        print(f"🎬 Demo mode | size=12 color={HEX_MUTED}")

    live_dot = "○" if active_scenario else "●"
    live_color = HEX_TEXT if active_scenario else HEX_GREEN
    print(f"--{live_dot}  Live data | bash='{PLUGIN_PATH}' param1=demo-off terminal=false refresh=true color={live_color}")

    print(f"--― Scenarios ― | color={HEX_DIM}")
    for name, (label, _fn) in demo.SCENARIOS.items():
        is_active = name == active_scenario
        dot = "●" if is_active else "○"
        color = HEX_WARN if is_active else HEX_TEXT
        print(f"--{dot}  {label} | bash='{PLUGIN_PATH}' param1=demo-on param2={name} terminal=false refresh=true color={color}")

    print(f"--― Pinned moments ― | color={HEX_DIM}")
    print(f"--Seed 3 demo pins | bash='{PLUGIN_PATH}' param1=demo-seed-pins terminal=false refresh=true")
    print(f"--Remove demo pins | bash='{PLUGIN_PATH}' param1=demo-unseed-pins terminal=false refresh=true")


def render(window_min, ignore_min, snapshot, fda_needed=False, age=None,
           active_pin_name=None, pinned_at=None, demo_scenario=None):
    signals = snapshot.get("signals") or {}
    timeline = snapshot.get("timeline") or []
    synth = snapshot.get("synth") or {}

    if is_compact(SLUG):
        print("⏪")
    elif demo_scenario:
        suffix = f" · skipping last {ignore_min}m" if ignore_min else ""
        print(f"⏪ Rewind · DEMO ({demo_scenario}){suffix}")
    elif active_pin_name:
        print("⏪ Rewind · pinned")
    else:
        suffix = f" · skipping last {ignore_min}m" if ignore_min else ""
        print(f"⏪ Rewind {window_min}m{suffix}")
    print("---")

    if PRESENTATION_INDEX.exists():
        print(f"🎩 Tomas Verifier 2.0 | bash=/usr/bin/open param1='{PRESENTATION_INDEX}' terminal=false refresh=false color={HEX_GREEN}")
        print(f"--Verdict: Tomas is right · 99.973% confident | color={HEX_MUTED} size=11")
        print("---")

    if demo_scenario:
        print(f"🎬 Demo mode · {demo_scenario} · synthetic data, indexer paused | size=11 color={HEX_WARN}")
        print("---")
    elif active_pin_name and pinned_at:
        when = datetime.fromtimestamp(pinned_at).strftime("%b %-d, %-I:%M %p")
        print(f"📌 Restored from pin · saved {when} | size=11 color={HEX_WARN}")
        print("---")
    elif age is not None and age > STALE_SECONDS:
        print(f"Snapshot is {int(age)}s old — refreshing in background | size=11 color={HEX_WARN}")
        print("---")

    if ignore_min and not active_pin_name:
        print(f"Skipping last {ignore_min} min — showing the {window_min} min before that | size=11 color={HEX_WARN}")
        print("---")

    render_recap(synth)
    render_focus_suggestion(synth)
    render_synth(synth)
    print("---")

    render_timeline(timeline, window_min, ignore_min, pinned=bool(active_pin_name))
    render_open_tabs(signals, synth)
    render_closed_tabs(signals)
    render_open_items(signals)
    render_clipboard(signals)

    render_browser_permission(signals.get("browser_denied"))

    print("---")
    if not active_pin_name:
        render_window_switcher(window_min, ignore_min)
    render_wrapup_action()
    render_pin_actions(active_pin_name)
    render_demo_controls(demo_scenario)
    render_indexer_controls(snapshot, age)

    if fda_needed:
        print("---")
        print(f"⚠️ Enable app + Notes history | color={HEX_WARN}")
        print("--Grant SwiftBar Full Disk Access, then refresh | size=11 color=#8b949e")
        print("--Open Full Disk Access settings | href=x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")

    print("---")
    print("🔄 Rebuild context | refresh=true")
    print_footer()


def _kick_indexer(background=True, force=False, wait_timeout=None):
    """Run the indexer subprocess. background=True fires-and-forgets (for stale
    refreshes); background=False waits (for window/ignore/reindex actions)."""
    cmd = [sys.executable, INDEXER_PATH, "--once"]
    if force:
        cmd.append("--force")
    if background:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return None
    try:
        return subprocess.run(cmd, timeout=wait_timeout, check=False)
    except subprocess.TimeoutExpired:
        return None


def _read_snapshot():
    """Read the snapshot JSON directly (avoid importing all of lib/rewind on the hot path)."""
    try:
        return json.loads(REWIND_SNAPSHOT.read_text())
    except Exception:
        return None


def _snapshot_age(snapshot):
    if not snapshot or not snapshot.get("generated_at"):
        return None
    return time.time() - snapshot["generated_at"]


def _current_settings(snapshot):
    """Prefer the user's persisted choices over whatever the snapshot was built with."""
    try:
        window_min = max(5, int(REWIND_WINDOW.read_text().strip()))
    except Exception:
        window_min = (snapshot or {}).get("window_min", 30)
    try:
        ignore_min = max(0, int(REWIND_IGNORE.read_text().strip()))
    except Exception:
        ignore_min = (snapshot or {}).get("ignore_min", 0)
    return window_min, ignore_min


def _empty_snapshot(window_min, ignore_min):
    return {
        "window_min": window_min,
        "ignore_min": ignore_min,
        "signals": {},
        "timeline": [],
        "synth": {
            "where": "Indexer hasn't run yet — give it a few seconds, then re-open this menu",
            "next": None, "forget": None,
            "_links": {"where": None, "next": None, "forget": None},
            "_source": "empty",
        },
        "fda_needed": False,
    }


def _active_pin_name():
    try:
        name = REWIND_ACTIVE_PIN.read_text().strip()
        return name or None
    except Exception:
        return None


def _read_demo_flag():
    try:
        return REWIND_DEMO_FLAG.read_text().strip() or None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _set_active_pin(name):
    REWIND_ACTIVE_PIN.parent.mkdir(parents=True, exist_ok=True)
    REWIND_ACTIVE_PIN.write_text(name or "")


def _clear_active_pin():
    try:
        REWIND_ACTIVE_PIN.unlink()
    except FileNotFoundError:
        pass


def _snapshot_from_pin(pin):
    """Adapt a pinned-moment dict (label/ts/window_min/ignore_min/synth/timeline) into a snapshot-shaped dict for render()."""
    return {
        "generated_at": pin.get("ts"),
        "window_min": pin.get("window_min", 30),
        "ignore_min": pin.get("ignore_min", 0),
        "signals": {},
        "timeline": pin.get("timeline") or [],
        "synth": pin.get("synth") or {},
        "fda_needed": False,
    }


def cmd_pin(label):
    """Pin the current snapshot to disk under the given label."""
    from rewind import save_pin
    snapshot = _read_snapshot()
    if not snapshot:
        _kick_indexer(background=False, wait_timeout=10)
        snapshot = _read_snapshot()
    if not snapshot:
        return
    save_pin(
        label=label,
        window_min=snapshot.get("window_min", 30),
        ignore_min=snapshot.get("ignore_min", 0),
        synth=snapshot.get("synth") or {},
        timeline=snapshot.get("timeline") or [],
    )


def _pin_label_suggestion():
    """LLM-suggested 3-5 word label for the current snapshot. Empty string on any failure."""
    snapshot = _read_snapshot()
    if not snapshot:
        return ""
    try:
        from rewind import suggest_label
        return suggest_label(
            timeline=snapshot.get("timeline") or [],
            synth=snapshot.get("synth") or {},
        ) or ""
    except Exception:
        return ""


def cmd_pin_prompt():
    """Pop a native dialog to label the pin (pre-filled with an LLM suggestion), then save."""
    suggestion = _pin_label_suggestion().replace('"', "'")
    script = (
        'tell application "System Events"\n'
        '  activate\n'
        '  try\n'
        '    set theLabel to text returned of (display dialog '
        f'"Pin this moment as:" default answer "{suggestion}" buttons {{"Cancel","Pin"}} '
        'default button "Pin" with title "Rewind")\n'
        '    return theLabel\n'
        '  on error\n'
        '    return ""\n'
        '  end try\n'
        'end tell'
    )
    label = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, check=False,
    ).stdout.strip()
    if label:
        cmd_pin(label)


def cmd_speak():
    """Print the three synth lines as plain text (for bin/rewind-speak.sh → say)."""
    snapshot = _read_snapshot()
    if not snapshot:
        _kick_indexer(background=False, wait_timeout=10)
        snapshot = _read_snapshot()
    synth = (snapshot or {}).get("synth") or {}
    print(synth.get("where") or "")
    print(synth.get("next") or "")
    print(synth.get("forget") or "")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "window":
        try:
            from rewind import demo, set_window_minutes
            new_w = int(sys.argv[2])
            set_window_minutes(new_w)
            if demo.active_scenario():
                _, ign = _current_settings(_read_snapshot())
                demo.refresh(window_min=new_w, ignore_min=ign)
            else:
                _kick_indexer(background=False, wait_timeout=5)
        except ValueError:
            pass
        return
    if len(sys.argv) > 2 and sys.argv[1] == "ignore":
        try:
            from rewind import demo, set_ignore_minutes
            new_i = int(sys.argv[2])
            set_ignore_minutes(new_i)
            if demo.active_scenario():
                w, _ = _current_settings(_read_snapshot())
                demo.refresh(window_min=w, ignore_min=new_i)
            else:
                _kick_indexer(background=False, wait_timeout=5)
        except ValueError:
            pass
        return
    if len(sys.argv) > 1 and sys.argv[1] == "reindex":
        force = len(sys.argv) > 2 and sys.argv[2] == "force"
        _kick_indexer(background=False, force=force, wait_timeout=20)
        return
    if len(sys.argv) > 2 and sys.argv[1] == "demo-on":
        from rewind import demo
        w, ign = _current_settings(_read_snapshot())
        try:
            demo.enable(sys.argv[2], window_min=w, ignore_min=ign)
        except ValueError:
            pass
        return
    if len(sys.argv) > 1 and sys.argv[1] == "demo-off":
        from rewind import demo
        demo.disable()
        _kick_indexer(background=False, wait_timeout=5)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "demo-seed-pins":
        from rewind import demo
        demo.seed_pins()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "demo-unseed-pins":
        from rewind import demo
        demo.unseed_pins()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "pin-prompt":
        cmd_pin_prompt()
        return
    if len(sys.argv) > 2 and sys.argv[1] == "pin":
        cmd_pin(sys.argv[2])
        return
    if len(sys.argv) > 2 and sys.argv[1] == "pin-set":
        _set_active_pin(sys.argv[2])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "pin-clear":
        _clear_active_pin()
        return
    if len(sys.argv) > 2 and sys.argv[1] == "pin-delete":
        from rewind import delete_pin
        delete_pin(sys.argv[2])
        if _active_pin_name() == sys.argv[2]:
            _clear_active_pin()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "speak":
        cmd_speak()
        return
    if len(sys.argv) > 2 and sys.argv[1] == "forget-ack":
        _ack_forget(sys.argv[2])
        return

    active = _active_pin_name()
    if active:
        from rewind import load_pin
        pin = load_pin(active)
        if not pin:
            _clear_active_pin()
            active = None
        else:
            window_min = pin.get("window_min", 30)
            ignore_min = pin.get("ignore_min", 0)
            render(
                window_min, ignore_min, _snapshot_from_pin(pin),
                fda_needed=False, age=None,
                active_pin_name=active, pinned_at=pin.get("ts"),
                demo_scenario=_read_demo_flag(),
            )
            return

    snapshot = _read_snapshot()
    window_min, ignore_min = _current_settings(snapshot)
    age = _snapshot_age(snapshot)
    demo_scenario = _read_demo_flag()

    if not demo_scenario and (snapshot is None or age is None or age > STALE_SECONDS):
        _kick_indexer(background=True)

    render(
        window_min, ignore_min,
        snapshot or _empty_snapshot(window_min, ignore_min),
        fda_needed=(snapshot or {}).get("fda_needed", False),
        age=age,
        demo_scenario=demo_scenario,
    )


if __name__ == "__main__":
    main()
