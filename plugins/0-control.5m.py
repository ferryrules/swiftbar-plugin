#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Dashboard Control Center</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Toggle plugins on/off, switch full/compact display</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import (
    PLUGIN_LABELS,
    REGISTRY,
    disable,
    enable,
    get_mode,
    is_auto_hidden,
    is_auto_hide_eligible,
    is_hidden,
    mark_auto_hidden,
    refresh,
    refresh_all,
    set_mode,
    update_auto_hide,
)
from dashboard import print_footer
from style import (
    EMOJI_REFRESH,
    HEX_DIM,
    HEX_GREEN,
    HEX_MUTED,
    HEX_TEXT,
    HEX_WARN,
)

PLUGIN_PATH = os.path.abspath(__file__)


def cmd_set_mode(slug, mode):
    set_mode(slug, mode)
    mark_auto_hidden(slug, False)
    enable(slug)
    refresh(slug)


def cmd_hide(slug):
    mark_auto_hidden(slug, False)
    disable(slug)


def cmd_bulk(action):
    for slug in REGISTRY:
        if action == "show_all":
            mark_auto_hidden(slug, False)
            enable(slug)
        elif action == "hide_all":
            mark_auto_hidden(slug, False)
            disable(slug)
        elif action == "compact_all":
            set_mode(slug, "compact")
            refresh(slug)
        elif action == "full_all":
            set_mode(slug, "full")
            refresh(slug)


def state_for(slug):
    """Return (label, color) for a plugin's current state."""
    if is_hidden(slug):
        if is_auto_hidden(slug):
            return "auto-hidden", HEX_DIM
        return "hidden", HEX_DIM
    mode = get_mode(slug)
    return mode, HEX_GREEN if mode == "full" else HEX_WARN


def render():
    update_auto_hide()

    visible = sum(1 for slug in REGISTRY if not is_hidden(slug))
    total = len(REGISTRY)
    auto = sum(1 for slug in REGISTRY if is_auto_hidden(slug))
    print(f"🎛 {visible}/{total}")
    print("---")

    summary = f"Dashboard ({visible} of {total} active"
    if auto:
        summary += f", {auto} auto-hidden"
    summary += ")"
    print(f"{summary} | size=13 color={HEX_MUTED}")
    print("---")

    for slug in REGISTRY:
        label = PLUGIN_LABELS.get(slug, slug)
        state_label, color = state_for(slug)
        marker = {
            "full": "●",
            "compact": "○",
            "hidden": "⊘",
            "auto-hidden": "◌",
        }[state_label]

        suffix = " (auto)" if is_auto_hide_eligible(slug) else ""
        print(f"{marker} {label} · {state_label}{suffix} | color={color}")
        print(f"--Show full | bash='{PLUGIN_PATH}' param1=set param2={slug} param3=full terminal=false refresh=true")
        print(f"--Compact | bash='{PLUGIN_PATH}' param1=set param2={slug} param3=compact terminal=false refresh=true")
        print(f"--Hidden | bash='{PLUGIN_PATH}' param1=hide param2={slug} terminal=false refresh=true")
        print(f"-----")
        print(f"--{EMOJI_REFRESH} Refresh now | bash='{PLUGIN_PATH}' param1=refresh param2={slug} terminal=false refresh=false")

    print("---")
    print(f"Bulk actions | size=11 color={HEX_MUTED}")
    print(f"Show all | bash='{PLUGIN_PATH}' param1=bulk param2=show_all terminal=false refresh=true")
    print(f"Hide all | bash='{PLUGIN_PATH}' param1=bulk param2=hide_all terminal=false refresh=true")
    print(f"Set all to full | bash='{PLUGIN_PATH}' param1=bulk param2=full_all terminal=false refresh=true")
    print(f"Set all to compact | bash='{PLUGIN_PATH}' param1=bulk param2=compact_all terminal=false refresh=true")

    print("---")
    print(f"{EMOJI_REFRESH} Refresh all plugins | bash='{PLUGIN_PATH}' param1=refresh_all terminal=false refresh=true")
    print_footer()


def main():
    args = sys.argv[1:]
    if not args:
        render()
        return

    cmd = args[0]
    if cmd == "set" and len(args) >= 3:
        cmd_set_mode(args[1], args[2])
    elif cmd == "hide" and len(args) >= 2:
        cmd_hide(args[1])
    elif cmd == "refresh" and len(args) >= 2:
        refresh(args[1])
    elif cmd == "refresh_all":
        refresh_all()
    elif cmd == "bulk" and len(args) >= 2:
        cmd_bulk(args[1])


if __name__ == "__main__":
    main()
