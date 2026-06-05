"""Slack: channels / DMs / threads the user posted in within the rewind window. Self-contained client (avoids lib/slack.py's socket.setdefaulttimeout side-effect). Privacy: message text never collected; channel name swapped for 'slack message' before sending to Claude."""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

SLACK_API = "https://slack.com/api"
TIMEOUT = 5


def _token():
    return os.environ.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_TOKEN")


def _call(method, params=None):
    token = _token()
    if not token:
        return None
    url = f"{SLACK_API}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _slack_app_url(team_id, channel_id, message_ts=None):
    if not channel_id:
        return ""
    base = f"slack://channel?team={team_id}&id={channel_id}" if team_id else f"slack://channel?id={channel_id}"
    if message_ts:
        try:
            base += f"&message={message_ts.replace('.', '')}"
        except Exception:
            pass
    return base


def fetch_slack(since_ts, max_items=10):
    """Channels / DMs / threads the user posted in since `since_ts`, de-duped per channel."""
    if not _token():
        return []

    info = _call("auth.test")
    if not info or not info.get("ok"):
        return []
    user_name = info.get("user")
    team_id = info.get("team_id")
    if not user_name:
        return []

    after = (datetime.fromtimestamp(since_ts) - timedelta(days=1)).strftime("%Y-%m-%d")
    res = _call("search.messages", {
        "query": f"from:@{user_name} after:{after}",
        "sort": "timestamp",
        "sort_dir": "desc",
        "count": 50,
    })
    if not res or not res.get("ok"):
        return []
    matches = (res.get("messages", {}) or {}).get("matches", []) or []

    seen, out = set(), []
    for m in matches:
        try:
            ts = float(m.get("ts", 0))
        except Exception:
            continue
        if ts < since_ts:
            continue
        ch = m.get("channel") or {}
        ch_id = ch.get("id")
        if not ch_id or ch_id in seen:
            continue
        seen.add(ch_id)

        is_im = bool(ch.get("is_im"))
        is_mpim = bool(ch.get("is_mpim"))
        ch_name = ch.get("name") or ""
        if is_im:
            label = f"DM with {ch.get('user_name') or ch_name or 'someone'}"
        elif is_mpim:
            label = f"group DM ({ch_name})" if ch_name else "group DM"
        elif ch_name:
            label = f"#{ch_name}"
        else:
            label = "Slack"

        thread = m.get("thread_ts") and m.get("thread_ts") != m.get("ts")
        verb = "replied in" if thread else ("DM'd" if is_im else "posted in")

        out.append({
            "ts": ts, "kind": "slack", "icon": "💬",
            "title": f"{verb} {label}",
            "url": _slack_app_url(team_id, ch_id, m.get("ts")),
            "channel": ch_name, "is_im": is_im,
            "claude_safe": True,
        })
        if len(out) >= max_items:
            break
    return out
