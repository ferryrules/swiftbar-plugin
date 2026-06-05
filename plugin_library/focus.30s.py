#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Focus Timer</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Pomodoro timer in the menubar</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import is_compact
from dashboard import notify, print_footer
from paths import FOCUS_STATE, ensure_dirs
from style import HEX_DIM, HEX_GREEN, HEX_MUTED, HEX_TEXT, HEX_WARN

PLUGIN_PATH = os.path.abspath(__file__)
SLUG = "focus"

STATE_FILE = FOCUS_STATE
ensure_dirs()

DURATIONS = [
    ("25 min focus", 25),
    ("50 min deep work", 50),
    ("5 min break", 5),
    ("15 min long break", 15),
]


def load_state():
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        end_at = datetime.fromisoformat(data["end_at"])
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
        return {"end_at": end_at, "label": data.get("label", "Focus")}
    except Exception:
        return None


def save_state(label, minutes):
    end_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    STATE_FILE.write_text(json.dumps({"end_at": end_at.isoformat(), "label": label}))


def clear_state():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def fmt_remaining(delta):
    secs = int(delta.total_seconds())
    if secs < 0:
        return "0:00"
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"


def render():
    state = load_state()

    if state is None:
        if is_compact(SLUG):
            print("⏱")
        else:
            print("⏱ idle")
        print("---")
        print(f"No active timer | color={HEX_DIM}")
        print_segments()
        print_footer()
        return

    now = datetime.now(timezone.utc)
    delta = state["end_at"] - now

    if delta.total_seconds() <= 0:
        notify(f"{state['label']} done", "Focus Timer")
        clear_state()
        if is_compact(SLUG):
            print("⏱ ✓")
        else:
            print(f"⏱ done · {state['label']}")
        print("---")
        print(f"Timer finished | color={HEX_GREEN}")
        print_segments()
        print_footer()
        return

    remaining = fmt_remaining(delta)
    label = state["label"]
    secs = int(delta.total_seconds())

    if secs < 60:
        color = HEX_WARN
        icon = "⏰"
    elif secs < 300:
        color = HEX_WARN
        icon = "⏱"
    else:
        color = HEX_GREEN
        icon = "⏱"

    if is_compact(SLUG):
        print(f"{icon} {remaining}")
    else:
        print(f"{icon} {remaining} · {label}")
    print("---")

    print(f"{label} · {remaining} remaining | color={color}")
    print(f"--Stop timer | bash='{PLUGIN_PATH}' param1=stop terminal=false refresh=true")
    print("---")

    print_segments()
    print_footer()


def print_segments():
    print(f"Start | size=11 color={HEX_MUTED}")
    for label, minutes in DURATIONS:
        print(f"--{label} ({minutes}m) | bash='{PLUGIN_PATH}' param1=start param2='{label}' param3={minutes} terminal=false refresh=true")


def main():
    args = sys.argv[1:]
    if args:
        cmd = args[0]
        if cmd == "start" and len(args) >= 3:
            label = args[1]
            try:
                minutes = int(args[2])
            except ValueError:
                return
            save_state(label, minutes)
            notify(f"{label} started ({minutes}m)", "Focus Timer")
            return
        if cmd == "stop":
            clear_state()
            notify("Timer stopped", "Focus Timer")
            return

    render()


if __name__ == "__main__":
    main()
