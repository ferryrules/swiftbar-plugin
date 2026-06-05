#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Cursor Recent Projects</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Quick-jump to recent Cursor workspaces</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import is_compact
from dashboard import print_footer
from style import HEX_DIM, HEX_MUTED, HEX_TEXT

PLUGIN_PATH = os.path.abspath(__file__)
SLUG = "cursor-recent"

WORKSPACE_STORAGE = Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "workspaceStorage"
MAX_RECENT = 12


def fetch_recent():
    """Return list of (path, mtime) sorted by recency."""
    if not WORKSPACE_STORAGE.exists():
        return []
    seen_paths = set()
    out = []
    for hash_dir in WORKSPACE_STORAGE.iterdir():
        ws_file = hash_dir / "workspace.json"
        if not ws_file.exists():
            continue
        try:
            data = json.loads(ws_file.read_text())
        except Exception:
            continue
        folder_uri = data.get("folder") or data.get("workspace") or ""
        if not folder_uri.startswith("file://"):
            continue
        path_str = urllib.parse.unquote(folder_uri[len("file://"):])
        path = Path(path_str)
        if path_str in seen_paths or not path.exists():
            continue
        seen_paths.add(path_str)
        try:
            mtime = ws_file.stat().st_mtime
        except OSError:
            continue
        out.append((path, mtime))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:MAX_RECENT]


def render(recents):
    if is_compact(SLUG):
        print("📂")
    else:
        print(f"📂 {len(recents)}")
    print("---")

    if not recents:
        print(f"No recent Cursor workspaces | color={HEX_DIM}")
        print_footer()
        return

    print(f"Recent projects | size=11 color={HEX_MUTED}")
    print("---")

    home = str(Path.home())
    for path, _ in recents:
        display = str(path)
        if display.startswith(home):
            display = "~" + display[len(home):]
        name = path.name or display
        print(f"📁 {name} | color={HEX_TEXT}")
        print(f"--{display} | size=11 color={HEX_MUTED}")
        print(f"--💻 Open in Cursor | bash='open' param1=-a param2=Cursor param3='{path}' terminal=false refresh=false")
        print(f"--📂 Reveal in Finder | bash='open' param1='{path}' terminal=false refresh=false")
        print(f"--🖥️  Open Terminal here | bash='open' param1=-a param2=Terminal param3='{path}' terminal=false refresh=false")

    print_footer()


def main():
    recents = fetch_recent()
    render(recents)


if __name__ == "__main__":
    main()
