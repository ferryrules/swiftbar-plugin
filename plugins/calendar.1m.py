#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Calendar</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Next meeting + today's agenda from macOS Calendar</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import auto_hide_when_empty, is_compact
from dashboard import print_footer
from style import HEX_DIM, HEX_GREEN, HEX_MUTED, HEX_TEXT, HEX_WARN

PLUGIN_PATH = os.path.abspath(__file__)
SLUG = "calendar"

ICALBUDDY = shutil.which("icalBuddy") or "/opt/homebrew/bin/icalBuddy"

ZOOM_RE = re.compile(r"https?://[^\s]*zoom\.us/[^\s\"']+")
MEET_RE = re.compile(r"https?://meet\.google\.com/[^\s\"']+")
TEAMS_RE = re.compile(r"https?://teams\.microsoft\.com/[^\s\"']+")


def has_icalbuddy():
    return Path(ICALBUDDY).exists()


def fetch_today():
    """Run icalBuddy and return a list of {title, start, end, link} dicts."""
    if not has_icalbuddy():
        return None
    fmt = ["-nc", "-npn", "-eep", "notes,location,attendees,url",
           "-iep", "title,datetime,notes,url",
           "-b", "•", "-tf", "%H:%M",
           "eventsToday"]
    try:
        proc = subprocess.run(
            [ICALBUDDY] + fmt,
            capture_output=True, text=True, timeout=10, check=False,
        )
    except Exception:
        return []
    return parse_icalbuddy(proc.stdout)


def parse_icalbuddy(text):
    """Parse icalBuddy's bullet-prefixed output into structured events."""
    events = []
    current = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("•"):
            if current:
                events.append(current)
            current = {"title": line.lstrip("•").strip(), "start": None, "end": None, "link": ""}
        elif current is not None:
            stripped = line.strip()
            time_match = re.match(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})$", stripped)
            if time_match:
                current["start"] = time_match.group(1)
                current["end"] = time_match.group(2)
                continue
            if stripped == "today":
                continue
            link = (
                (ZOOM_RE.search(stripped) or [None])[0] if ZOOM_RE.search(stripped)
                else (MEET_RE.search(stripped) or [None])[0] if MEET_RE.search(stripped)
                else (TEAMS_RE.search(stripped) or [None])[0] if TEAMS_RE.search(stripped)
                else None
            )
            for pattern in (ZOOM_RE, MEET_RE, TEAMS_RE):
                m = pattern.search(stripped)
                if m and not current["link"]:
                    current["link"] = m.group(0)
                    break
    if current:
        events.append(current)
    return events


def parse_hhmm(s):
    if not s:
        return None
    try:
        hh, mm = s.split(":")
        now = datetime.now()
        return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        return None


def time_until(dt):
    if not dt:
        return None
    delta = dt - datetime.now()
    return delta


def fmt_until(delta):
    if delta is None:
        return ""
    secs = int(delta.total_seconds())
    if secs < 0:
        return "now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    rem = mins % 60
    return f"{hours}h{rem}m" if rem else f"{hours}h"


def color_for(delta):
    if delta is None:
        return HEX_MUTED
    secs = int(delta.total_seconds())
    if secs < 120:
        return "#ff4444"
    if secs < 600:
        return HEX_WARN
    return HEX_GREEN


def find_next(events):
    now = datetime.now()
    upcoming = []
    for e in events:
        start = parse_hhmm(e["start"])
        if start and start >= now - timedelta(minutes=5):
            upcoming.append((start, e))
    upcoming.sort(key=lambda x: x[0])
    return upcoming[0] if upcoming else (None, None)


def render_compact(events):
    start, evt = find_next(events)
    if not evt:
        print("📅 ✓")
        return
    delta = time_until(start)
    until = fmt_until(delta)
    print(f"📅 {until}")


def render(events):
    start, next_evt = find_next(events)

    if is_compact(SLUG):
        render_compact(events)
    else:
        if next_evt:
            delta = time_until(start)
            until = fmt_until(delta)
            short_title = next_evt["title"][:28]
            print(f"📅 {until} · {short_title}")
        elif events:
            print("📅 done")
        else:
            print("📅 ✓")
    print("---")

    if not events:
        print(f"No events today | color={HEX_DIM}")
        print_footer()
        return

    print(f"Today's agenda | size=13 color={HEX_MUTED}")
    print("---")
    now = datetime.now()
    for e in events:
        start_dt = parse_hhmm(e["start"])
        is_next = start_dt is not None and next_evt is e
        is_past = start_dt is not None and start_dt < now - timedelta(minutes=5)

        time_label = f"{e['start'] or '??'}"
        title = e["title"]
        if is_past:
            color = HEX_DIM
        elif is_next:
            color = color_for(time_until(start_dt))
        else:
            color = HEX_TEXT

        line = f"{time_label}  {title}"
        if is_next:
            until = fmt_until(time_until(start_dt))
            line = f"▶ {time_label}  {title}  · in {until}"
        print(f"{line} | color={color}")

        if e.get("link"):
            print(f"--🎥 Join meeting | href={e['link']}")

    print_footer()


def has_upcoming(events):
    """True if any event today is starting now or in the future."""
    if not events:
        return False
    now = datetime.now()
    for e in events:
        start = parse_hhmm(e["start"])
        if start and start >= now - timedelta(minutes=5):
            return True
    return False


def main():
    if not has_icalbuddy():
        if "--probe" in sys.argv:
            sys.exit(1)
        print("📅 ⚠️")
        print("---")
        print(f"icalBuddy not installed | color={HEX_WARN}")
        print(f"Install: brew install ical-buddy | size=11 color={HEX_MUTED}")
        print("---")
        print("Open Calendar.app | href=ical://")
        print_footer()
        return

    if "--probe" in sys.argv:
        events = fetch_today() or []
        sys.exit(0 if not has_upcoming(events) else 1)

    events = fetch_today() or []
    render(events)
    auto_hide_when_empty(SLUG, not has_upcoming(events))


if __name__ == "__main__":
    main()
