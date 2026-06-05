"""Shared helpers for the swiftbar-dashboard plugins.

Lives outside the SwiftBar plugin directory so it isn't picked up as a
plugin; sibling plugins add the repo root to sys.path and import it.
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from paths import ENV_FILE
from style import EMOJI_REFRESH, HEX_DIM

CONFIG_FILE = ENV_FILE


def load_env():
    if not CONFIG_FILE.exists():
        return
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def api_request(url, headers=None, data=None, timeout=15):
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers or {})
        if body:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def gql(url, headers, query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    return api_request(url, headers=headers, data=payload)


def sanitize(text, max_len=60):
    text = str(text).replace("|", "—").replace("\n", " ").replace("\r", "")
    if text.startswith("--"):
        text = text.lstrip("-").lstrip()
    return text[:max_len] + "…" if len(text) > max_len else text


def time_ago(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        if diff.days > 0:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        return f"{diff.seconds // 60}m ago"
    except (ValueError, TypeError):
        return ""


def notify(message, title="Dashboard"):
    safe_msg = str(message).replace('"', "'")
    safe_title = str(title).replace('"', "'")
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
        check=False,
    )


def copy_to_clipboard(text, title="Copied"):
    if not text:
        return
    subprocess.run(["pbcopy"], input=text.encode(), check=False)
    notify(text, title)


def print_footer(label="Updated"):
    plugin_name = Path(sys.argv[0]).name
    print("---")
    now = datetime.now().strftime("%-I:%M %p")
    print(f"{label} {now} | color={HEX_DIM} size=11")
    print(f"{EMOJI_REFRESH} Refresh | refresh=true")
    print(
        f"⚡ Force refresh | "
        f"shell=open param1='-g' param2='swiftbar://refreshplugin?name={plugin_name}' "
        f"terminal=false refresh=false"
    )
