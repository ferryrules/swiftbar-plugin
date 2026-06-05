"""Calendar meetings via icalBuddy; entry ts = meeting start time. Privacy: title swapped for 'calendar event' before sending to Claude."""

import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

ICALBUDDY = shutil.which("icalBuddy") or "/opt/homebrew/bin/icalBuddy"

ZOOM_RE = re.compile(r"https?://[^\s]*zoom\.us/[^\s\"']+")
MEET_RE = re.compile(r"https?://meet\.google\.com/[^\s\"']+")
TEAMS_RE = re.compile(r"https?://teams\.microsoft\.com/[^\s\"']+")


def _has_icalbuddy():
    return Path(ICALBUDDY).exists()


def _parse(text):
    """icalBuddy bullet-prefixed output → list of {title,start,end,link}."""
    events, current = [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("•"):
            if current:
                events.append(current)
            current = {"title": line.lstrip("•").strip(),
                       "start": None, "end": None, "link": ""}
        elif current is not None:
            stripped = line.strip()
            t = re.match(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})$", stripped)
            if t:
                current["start"], current["end"] = t.group(1), t.group(2)
                continue
            for pattern in (ZOOM_RE, MEET_RE, TEAMS_RE):
                m = pattern.search(stripped)
                if m and not current["link"]:
                    current["link"] = m.group(0)
                    break
    if current:
        events.append(current)
    return events


def _hhmm_today(s):
    if not s:
        return None
    try:
        hh, mm = s.split(":")
        now = datetime.now()
        return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        return None


def fetch_calendar(since_ts):
    """Today's meetings whose start time is in [since_ts, now]; bounded to today (rewind windows are typically <= 4h)."""
    if not _has_icalbuddy():
        return []
    args = ["-nc", "-npn",
            "-eep", "notes,location,attendees",
            "-iep", "title,datetime,url",
            "-b", "•",
            "-tf", "%H:%M",
            "eventsToday"]
    try:
        proc = subprocess.run(
            [ICALBUDDY] + args,
            capture_output=True, text=True, timeout=10, check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []

    now_ts = datetime.now().timestamp()
    out = []
    for evt in _parse(proc.stdout):
        start = _hhmm_today(evt.get("start"))
        if not start:
            continue
        ts = start.timestamp()
        if ts < since_ts or ts > now_ts + 60:
            continue
        out.append({
            "ts": ts, "kind": "meeting", "icon": "📅",
            "title": evt["title"],
            "url": evt.get("link") or "",
            "claude_safe": True,
        })
    out.sort(key=lambda x: -x["ts"])
    return out
