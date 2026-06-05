#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Slack: For Me Only</bitbar.title>
# <bitbar.version>v2.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Unread DMs, group DMs, @mentions, thread replies, keywords. See lib/slack_config.py.</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import os
import re
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import auto_hide_when_empty, is_compact
from dashboard import load_env, print_footer, sanitize
from slack import (
    auth_test,
    fetch_keyword_matches,
    fetch_recent_mentions,
    fetch_thread_replies,
    fetch_unread_dms,
    fetch_watched_channels,
    finalize,
    has_token,
    relative_age,
    slack_app_url,
)
from slack_config import CONFIG_FILE, load_config
from style import HEX_DIM, HEX_MUTED, HEX_TEXT, HEX_WARN

PLUGIN_PATH = os.path.abspath(__file__)
SLUG = "slack"
WALL_TIMEOUT_SEC = 12


def _watched_msg_count(state):
    return sum(len(g["messages"]) for g in state["watched_channels"])


def render_compact(state):
    total = (
        sum(d["unread"] for d in state["dms"])
        + sum(d["unread"] for d in state["group_dms"])
        + len(state["mentions"])
        + sum(t["new_reply_count"] for t in state["thread_replies"])
        + len(state["keywords"])
        + _watched_msg_count(state)
    )
    if total:
        print(f"💬 {total}")
    else:
        print("💬 ✓")


def render_full(state):
    parts = []
    dms_count = sum(d["unread"] for d in state["dms"])
    gdms_count = sum(d["unread"] for d in state["group_dms"])
    if dms_count:
        parts.append(f"{dms_count} DM" + ("s" if dms_count != 1 else ""))
    if gdms_count:
        parts.append(f"{gdms_count} group")
    if state["mentions"]:
        parts.append(f"{len(state['mentions'])} @")
    if state["thread_replies"]:
        parts.append(f"{len(state['thread_replies'])} thread" + ("s" if len(state['thread_replies']) != 1 else ""))
    if state["keywords"]:
        parts.append(f"{len(state['keywords'])} kw")
    watched = _watched_msg_count(state)
    if watched:
        parts.append(f"{watched} ch")
    if parts:
        print("💬 " + " · ".join(parts))
    else:
        print("💬 ✓")


def render_dm_section(title, dms, team_id, limit, color_header, show_preview):
    if not dms:
        return
    print(f"{title} ({len(dms)}) | size=12 color={color_header}")
    for d in dms[:limit]:
        label = sanitize(d["name"], 32)
        badge = f"({d['unread']})"
        url = slack_app_url(team_id, d["channel"])
        print(f"{label}  {badge} | color={HEX_TEXT} href={url}")
        if show_preview and d["last_text"]:
            snippet = sanitize(d["last_text"], 60)
            age = relative_age(d["ts"])
            age_label = f"  · {age}" if age else ""
            print(f"--{snippet}{age_label} | color={HEX_DIM} href={url}")
    if len(dms) > limit:
        print(f"… +{len(dms) - limit} more | color={HEX_DIM} href=slack://open")
    print("---")


def _is_group_dm_name(name):
    """Detect Slack's group-DM channel naming convention (mpdm-...)."""
    return bool(name) and name.startswith("mpdm-")


def _is_dm_like(channel_id, channel_name):
    """True if a channel is a 1:1 DM, group DM, or shows up here as a user-id."""
    if _is_group_dm_name(channel_name):
        return True
    # 1:1 DMs in Slack: channel IDs start with D. User-id-as-channel: U-prefix.
    if channel_id and channel_id.startswith(("D", "U")):
        return True
    return False


def _prettify_group_dm_name(name, my_handle=None):
    """Turn 'mpdm-ferris.boran--bode.faleye--carlos-1' into 'bode, carlos'."""
    if not _is_group_dm_name(name):
        return name
    inner = re.sub(r"-\d+$", "", name[5:])
    users = [u.split(".")[0] for u in inner.split("--") if u]
    if my_handle:
        my_first = my_handle.split(".")[0].lower()
        users = [u for u in users if u.lower() != my_first]
    return ", ".join(users) if users else "(group)"


def render_dms_combined(state, dm_channels, team_id, limit, show_preview, my_handle=None):
    """Render all DM-like content as a single 'Direct Messages' block:
       - auto-fetched 1:1 + group DMs (state["dms"], state["group_dms"])
       - DM thread replies (state["thread_replies"] with is_dm=True)
       - any DM-like channels (1:1 or mpdm) where mentions/keywords/watched
         messages occurred (dm_channels, from aggregate_activity_by_channel)
    """
    one_on_one = state["dms"]
    group = state["group_dms"]
    dm_threads = [t for t in state["thread_replies"] if t["is_dm"]]

    all_dms = one_on_one + group
    if not all_dms and not dm_threads and not dm_channels:
        return

    all_dms.sort(key=lambda d: -float(d.get("ts") or 0))

    total = (
        sum(d["unread"] for d in all_dms)
        + sum(t["new_reply_count"] for t in dm_threads)
        + sum(
            len(ch["mentions"]) + len(ch["threads"]) + len(ch["keywords"]) + len(ch["watched"])
            for ch in dm_channels.values()
        )
    )
    print(f"Direct Messages ({total}) | size=12 color={HEX_MUTED}")

    for d in all_dms[:limit]:
        prefix = "👥 " if not d.get("is_im") else ""
        label = sanitize(d["name"], 32)
        badge = f"({d['unread']})"
        url = slack_app_url(team_id, d["channel"])
        print(f"{prefix}{label}  {badge} | color={HEX_TEXT} href={url}")
        if show_preview and d["last_text"]:
            snippet = sanitize(d["last_text"], 60)
            age = relative_age(d["ts"])
            age_label = f"  · {age}" if age else ""
            print(f"--{snippet}{age_label} | color={HEX_DIM} href={url}")

    if len(all_dms) > limit:
        print(f"… +{len(all_dms) - limit} more | color={HEX_DIM} href=slack://open")

    for t in dm_threads[:limit]:
        head = f"↳ thread · {t['new_reply_count']} new · {relative_age(t['latest_ts'])}"
        url = slack_app_url(team_id, t["channel_id"], f"{t['thread_ts']}")
        print(f"{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
        if show_preview and t.get("latest_text"):
            preview = f"{t['latest_author']}: {t['latest_text']}" if t.get('latest_author') else t['latest_text']
            print(f"--{sanitize(preview, 60)} | color={HEX_DIM} href={url}")

    # DM-like channels (mpdm group DMs or 1:1) with mentions/keywords/etc.
    for cid, ch in dm_channels.items():
        pretty = _prettify_group_dm_name(ch["name"], my_handle) if _is_group_dm_name(ch["name"]) else ch["name"]
        items = len(ch["mentions"]) + len(ch["threads"]) + len(ch["keywords"]) + len(ch["watched"])
        channel_url = slack_app_url(team_id, cid) if cid else ""
        header = f"👥 {pretty}  ({items})"
        if channel_url:
            print(f"{header} | color={HEX_TEXT} href={channel_url}")
        else:
            print(f"{header} | color={HEX_TEXT}")

        # Reuse the per-line rendering from render_channel as sub-items
        for m in ch["mentions"]:
            head = f"@you · {m.get('author', '?')} · {relative_age(m['ts'])}"
            url = m.get("permalink") or slack_app_url(team_id, m["channel"], f"{m['ts']:.6f}")
            print(f"--{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
            if show_preview and m.get("text"):
                print(f"----{sanitize(m['text'], 60)} | color={HEX_DIM} href={url}")
        for t in ch["threads"]:
            head = f"↳ thread · {t['new_reply_count']} new · {relative_age(t['latest_ts'])}"
            url = slack_app_url(team_id, t["channel_id"], f"{t['thread_ts']}")
            print(f"--{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
            if show_preview and t.get("latest_text"):
                preview = f"{t['latest_author']}: {t['latest_text']}" if t.get('latest_author') else t['latest_text']
                print(f"----{sanitize(preview, 60)} | color={HEX_DIM} href={url}")
        for k in ch["keywords"]:
            head = f"“{k['keyword']}” · {k.get('author', '?')} · {relative_age(k['ts'])}"
            url = k.get("permalink") or slack_app_url(team_id, k["channel_id"], f"{k['ts']:.6f}")
            print(f"--{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
            if show_preview and k.get("text"):
                print(f"----{sanitize(k['text'], 60)} | color={HEX_DIM} href={url}")
        for m in ch["watched"]:
            head = f"{m.get('author', '?')} · {relative_age(m['ts'])}"
            url = m.get("permalink") or channel_url
            print(f"--{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
            if show_preview and m.get("text"):
                print(f"----{sanitize(m['text'], 80)} | color={HEX_DIM} href={url}")

    print("---")


def aggregate_activity_by_channel(state):
    """Group ALL channel-keyed activity (mentions, thread replies, keyword
    matches, watched messages) by channel_id. Returns dict of:
        channel_id -> {"id", "name", "is_dm",
                       "mentions", "threads", "keywords", "watched"}
    Caller splits DM-like channels from real channels by the "is_dm" flag.
    """
    channels = {}

    def _bucket(cid, name):
        return channels.setdefault(cid, {
            "id": cid, "name": name,
            "is_dm": _is_dm_like(cid, name),
            "mentions": [], "threads": [],
            "keywords": [], "watched": [],
        })

    for m in state["mentions"]:
        _bucket(m["channel"], m.get("channel_name", "?"))["mentions"].append(m)
    for t in state["thread_replies"]:
        # is_dm is provided directly by the fetcher for 1:1 DM threads
        if t.get("is_dm"):
            continue
        _bucket(t["channel_id"], t.get("channel_name", "?"))["threads"].append(t)
    for k in state["keywords"]:
        _bucket(k["channel_id"], k.get("channel_name", "?"))["keywords"].append(k)
    for group in state["watched_channels"]:
        bucket = _bucket(group["channel_id"], group.get("channel_name", "?"))
        bucket["watched"].extend(group["messages"])

    return channels


def render_channel(channel_id, ch, team_id, show_preview):
    """Render a single channel section with all activity in it."""
    channel_url = slack_app_url(team_id, channel_id) if channel_id else ""
    total = len(ch["mentions"]) + len(ch["threads"]) + len(ch["keywords"]) + len(ch["watched"])
    header = f"#{ch['name']} ({total})"
    if channel_url:
        print(f"{header} | size=12 color={HEX_MUTED} href={channel_url}")
    else:
        print(f"{header} | size=12 color={HEX_MUTED}")

    for m in ch["mentions"]:
        head = f"@you · {m.get('author', '?')} · {relative_age(m['ts'])}"
        url = m.get("permalink") or slack_app_url(team_id, m["channel"], f"{m['ts']:.6f}")
        print(f"{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
        if show_preview and m.get("text"):
            print(f"--{sanitize(m['text'], 60)} | color={HEX_DIM} href={url}")

    for t in ch["threads"]:
        head = f"↳ thread · {t['new_reply_count']} new · {relative_age(t['latest_ts'])}"
        url = slack_app_url(team_id, t["channel_id"], f"{t['thread_ts']}")
        print(f"{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
        if show_preview and t.get("my_preview"):
            print(f"--You: {sanitize(t['my_preview'], 60)} | color={HEX_DIM} href={url}")
        if show_preview and t.get("latest_text"):
            preview = f"{t['latest_author']}: {t['latest_text']}" if t.get('latest_author') else t['latest_text']
            print(f"--{sanitize(preview, 60)} | color={HEX_DIM} href={url}")

    for k in ch["keywords"]:
        head = f"“{k['keyword']}” · {k.get('author', '?')} · {relative_age(k['ts'])}"
        url = k.get("permalink") or slack_app_url(team_id, k["channel_id"], f"{k['ts']:.6f}")
        print(f"{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
        if show_preview and k.get("text"):
            print(f"--{sanitize(k['text'], 60)} | color={HEX_DIM} href={url}")

    for m in ch["watched"]:
        head = f"{m.get('author', '?')} · {relative_age(m['ts'])}"
        url = m.get("permalink") or channel_url
        print(f"{sanitize(head, 60)} | color={HEX_TEXT} href={url}")
        if show_preview and m.get("text"):
            print(f"--{sanitize(m['text'], 80)} | color={HEX_DIM} href={url}")

    print("---")


def render(team_id, user_name, state, cfg):
    if is_compact(SLUG):
        render_compact(state)
    else:
        render_full(state)
    print("---")

    if user_name:
        print(f"Slack · @{user_name} | size=11 color={HEX_MUTED}")
        print("---")

    if not _any_content(state):
        print(f"All caught up | color={HEX_DIM}")
        print("Open Slack | href=slack://open")
        print_footer()
        return

    show_preview = cfg["filters"]["show_preview"]
    limits = cfg["limits"]

    # Bucket all channel-keyed activity, then split DM-like channels from real ones.
    all_channels = aggregate_activity_by_channel(state)
    dm_channels = {cid: ch for cid, ch in all_channels.items() if ch["is_dm"]}
    real_channels = {cid: ch for cid, ch in all_channels.items() if not ch["is_dm"]}

    # DMs (collective): 1:1 + group DMs (auto-fetched) + any activity in DM-like channels
    render_dms_combined(state, dm_channels, team_id, limits["dms"], show_preview, my_handle=user_name)

    # Channels (individual): one section per real channel
    if real_channels:
        def sort_key(item):
            _, ch = item
            return (-len(ch["mentions"]),
                    -(len(ch["threads"]) + len(ch["keywords"]) + len(ch["watched"])),
                    ch["name"].lower())
        for cid, ch in sorted(real_channels.items(), key=sort_key):
            render_channel(cid, ch, team_id, show_preview)

    print(f"Edit preferences | bash='open' param1='-t' param2='{CONFIG_FILE}' terminal=false refresh=false")
    print("Open Slack | href=slack://open")
    print_footer()


def render_setup_needed():
    print("💬 ⚙")
    print("---")
    print(f"Slack token not set | color={HEX_WARN}")
    print(f"Add SLACK_USER_TOKEN to config/.env | size=11 color={HEX_MUTED}")
    print("---")
    print("Setup docs | href=https://api.slack.com/apps")
    print_footer()


def render_auth_failed():
    print("💬 ⚠️")
    print("---")
    print(f"Slack auth failed | color={HEX_WARN}")
    print(f"Token may be invalid or missing scopes | size=11 color={HEX_MUTED}")
    print("---")
    print("Reauthorize the app | href=https://api.slack.com/apps")
    print_footer()


def render_timeout():
    print("💬 ⏱")
    print("---")
    print(f"Slack fetch timed out after {WALL_TIMEOUT_SEC}s | color={HEX_WARN}")
    print(f"Slack API may be slow | size=11 color={HEX_MUTED}")
    print("---")
    print("↻ Retry | refresh=true")
    print("Open Slack | href=slack://open")
    print_footer()


class _Timeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _Timeout()


def _any_content(state):
    return any((
        state["dms"], state["group_dms"], state["mentions"],
        state["thread_replies"], state["keywords"], state["watched_channels"],
    ))


def gather(cfg):
    """Run all enabled fetchers in parallel. Returns (team_id, user_name, state)
    or None on auth failure."""
    team_id, user_id, _, user_name = auth_test()
    if not team_id or not user_id:
        return None

    filters = cfg["filters"]
    windows = cfg["windows"]
    show = cfg["show"]
    limits = cfg["limits"]

    def fetch_dms():
        if not (show["dms"] or show["group_dms"]):
            return []
        return fetch_unread_dms(
            speed_mode=cfg["speed_mode"],
            quick_poll_n=limits["quick_poll"],
            exclude_bots=filters["exclude_bots"],
            include_1to1=show["dms"],
            include_group=show["group_dms"],
        )

    def fetch_mentions_():
        if not show["mentions"]:
            return []
        return fetch_recent_mentions(
            user_id,
            hours=windows["mention_hours"],
            limit=limits["mentions"],
            exclude_bots=filters["exclude_bots"],
            exclude_channels=filters["exclude_channels"],
        )

    def fetch_threads_():
        if not show["thread_replies"]:
            return []
        return fetch_thread_replies(
            user_id,
            hours=windows["thread_hours"],
            limit=limits["thread_replies"],
            exclude_bots=filters["exclude_bots"],
        )

    def fetch_keywords_():
        if not show["keywords"] or not cfg["keywords"]:
            return []
        return fetch_keyword_matches(
            cfg["keywords"], user_id,
            hours=windows["keyword_hours"],
            max_per_keyword=limits["keywords"],
            exclude_bots=filters["exclude_bots"],
            exclude_channels=filters["exclude_channels"],
        )

    def fetch_channels_():
        if not show["watched_channels"] or not cfg["watched_channels"]:
            return []
        return fetch_watched_channels(
            cfg["watched_channels"], my_user_id=user_id,
            hours=windows["watched_channel_hours"],
            max_per_channel=limits["watched_channel_messages"],
            exclude_bots=filters["exclude_bots"],
        )

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_dms = ex.submit(fetch_dms)
        f_mentions = ex.submit(fetch_mentions_)
        f_threads = ex.submit(fetch_threads_)
        f_keywords = ex.submit(fetch_keywords_)
        f_channels = ex.submit(fetch_channels_)
        all_dms = f_dms.result()
        mentions = f_mentions.result()
        threads = f_threads.result()
        keywords = f_keywords.result()
        watched = f_channels.result()

    state = {
        "dms": [d for d in all_dms if d["is_im"]],
        "group_dms": [d for d in all_dms if not d["is_im"]],
        "mentions": mentions,
        "thread_replies": threads,
        "keywords": keywords,
        "watched_channels": watched,
    }
    return (team_id, user_name, state)


def is_empty():
    load_env()
    if not has_token():
        return False
    cfg = load_config()
    data = gather(cfg)
    if data is None:
        return False
    _, _, state = data
    return not _any_content(state)


def main():
    if "--probe" in sys.argv:
        sys.exit(0 if is_empty() else 1)

    load_env()

    if not has_token():
        render_setup_needed()
        return

    cfg = load_config()

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(WALL_TIMEOUT_SEC)
    try:
        data = gather(cfg)
    except _Timeout:
        render_timeout()
        return
    finally:
        signal.alarm(0)

    if data is None:
        render_auth_failed()
        return

    team_id, user_name, state = data
    render(team_id, user_name, state, cfg)
    finalize()
    auto_hide_when_empty(SLUG, not _any_content(state))


if __name__ == "__main__":
    main()
