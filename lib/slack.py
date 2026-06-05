"""Slack helpers for swiftbar-dashboard plugins.

Uses a User OAuth token (xoxp-) so we can read DMs and search for our own
@mentions. See docs/SLACK_SETUP.md for one-time setup.

Optimized for SwiftBar: parallel HTTP, short per-call timeouts, persistent
caches for identity, and search.messages as the primary unread fetcher
(falls back to polling for real-time accuracy on recent DMs).
"""

import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import datetime, timedelta

import slack_cache

SLACK_API = "https://slack.com/api"

HTTP_TIMEOUT = 5
MAX_WORKERS = 12

USER_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
CHANNEL_RE = re.compile(r"<#[A-Z0-9]+\|([^>]+)>")
LINK_LABELED_RE = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")
LINK_BARE_RE = re.compile(r"<(https?://[^>]+)>")

socket.setdefaulttimeout(HTTP_TIMEOUT)


def _token():
    return os.environ.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_TOKEN")


def has_token():
    return bool(_token())


def slack_call(method, params=None, timeout=HTTP_TIMEOUT):
    token = _token()
    if not token:
        return None
    url = f"{SLACK_API}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def auth_test():
    """Return (team_id, user_id, team_name, user_name). Cached across runs."""
    cached = slack_cache.load_auth()
    if cached and cached[0] and cached[1]:
        team_id, user_id, user_name, team_name = cached
        return (team_id, user_id, team_name, user_name)
    info = slack_call("auth.test")
    if not info or not info.get("ok"):
        return (None, None, None, None)
    team_id = info.get("team_id")
    user_id = info.get("user_id")
    team_name = info.get("team")
    user_name = info.get("user")
    slack_cache.save_auth(team_id, user_id, user_name, team_name)
    return (team_id, user_id, team_name, user_name)


# ----- User display-name cache (in-memory + persistent) -----

_user_cache = {}


def _init_user_cache():
    if not _user_cache:
        _user_cache.update(slack_cache.load_users())


def _flush_user_cache():
    slack_cache.save_users(_user_cache)


def user_display_name(user_id):
    if not user_id:
        return ""
    _init_user_cache()
    if user_id in _user_cache:
        return _user_cache[user_id]
    out = slack_call("users.info", {"user": user_id})
    if not out or not out.get("ok"):
        _user_cache[user_id] = user_id
        return user_id
    u = out.get("user", {})
    profile = u.get("profile", {}) or {}
    name = (
        profile.get("display_name_normalized")
        or profile.get("real_name_normalized")
        or u.get("real_name")
        or u.get("name")
        or user_id
    )
    _user_cache[user_id] = name
    return name


def prewarm_users(user_ids):
    """Resolve a batch of user IDs in parallel; populates the cache."""
    _init_user_cache()
    todo = [uid for uid in user_ids if uid and uid not in _user_cache]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(ex.map(user_display_name, todo))


def clean_text(text):
    if not text:
        return ""
    text = USER_RE.sub(lambda m: f"@{user_display_name(m.group(1))}", text)
    text = CHANNEL_RE.sub(r"#\1", text)
    text = LINK_LABELED_RE.sub(r"\2", text)
    text = LINK_BARE_RE.sub(r"\1", text)
    text = text.replace("<!channel>", "@channel").replace("<!here>", "@here").replace("<!everyone>", "@everyone")
    return text.replace("\n", " ").strip()


def _is_bot_message(msg):
    return bool(msg.get("bot_id")) or msg.get("subtype") == "bot_message"


def _after_date(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d")


def _search(query, count=50):
    return slack_call("search.messages", {
        "query": query,
        "sort": "timestamp",
        "sort_dir": "desc",
        "count": count,
    })


def _drain(futures, timeout):
    """Yield (key, result) pairs from {future: key}; ignore individual
    exceptions and stop early if the overall as_completed timeout fires.
    Returns whatever finished — we'd rather render partial results than
    crash the plugin."""
    try:
        for fut in as_completed(futures, timeout=timeout):
            try:
                yield futures[fut], fut.result()
            except Exception:
                continue
    except FuturesTimeoutError:
        return


# ----- DMs via search (fast path) -----

def _fetch_unread_dms_via_search(exclude_bots=True):
    """Group unread DM messages by channel. Returns list of {channel, name,
    unread, last_text, ts, is_im}. Fast (1 API call) but lags real-time."""
    res = _search("is:unread in:dms", count=100) or _search("is:unread in:dm,mpim", count=100)
    if not res or not res.get("ok"):
        return []
    matches = (res.get("messages", {}) or {}).get("matches", []) or []
    if exclude_bots:
        matches = [m for m in matches if not _is_bot_message(m)]

    by_channel = {}
    for m in matches:
        ch = m.get("channel", {}) or {}
        ch_id = ch.get("id")
        if not ch_id:
            continue
        bucket = by_channel.setdefault(ch_id, {"channel": ch, "msgs": []})
        bucket["msgs"].append(m)

    prewarm_users({m.get("user") for m in matches if m.get("user")})

    out = []
    for ch_id, bucket in by_channel.items():
        ch = bucket["channel"]
        msgs = sorted(bucket["msgs"], key=lambda x: float(x.get("ts", 0)), reverse=True)
        latest = msgs[0]
        is_im = bool(ch.get("is_im"))
        if is_im:
            name = user_display_name(latest.get("user")) if latest.get("user") else (ch.get("name") or "DM")
        else:
            name = ch.get("name") or "Group DM"
        out.append({
            "channel": ch_id,
            "name": name,
            "unread": len(msgs),
            "last_text": clean_text(latest.get("text", "")),
            "ts": float(latest.get("ts", 0)),
            "is_im": is_im,
        })
    return out


def _fetch_unread_dms_quick_poll(n=10, exclude_bots=True):
    """Poll the N most-recent IMs/MPIMs for real-time unread counts."""
    convs_resp = slack_call("users.conversations", {
        "types": "im,mpim", "limit": n, "exclude_archived": "true",
    })
    if not convs_resp or not convs_resp.get("ok"):
        return []
    convs = convs_resp.get("channels", [])[:n]
    if not convs:
        return []

    infos = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(slack_call, "conversations.info",
                          {"channel": c["id"], "include_num_members": "false"}): c["id"]
                for c in convs}
        for ch_id, r in _drain(futs, HTTP_TIMEOUT * 2):
            if r and r.get("ok"):
                infos[ch_id] = r.get("channel")

    prewarm_users({c["user"] for c in convs if c.get("is_im") and c.get("user")})

    out = []
    for c in convs:
        info = infos.get(c["id"])
        if not info:
            continue
        unread = info.get("unread_count_display") or info.get("unread_count") or 0
        if not unread:
            continue
        latest = info.get("latest") or {}
        if exclude_bots and _is_bot_message(latest):
            continue
        is_im = bool(c.get("is_im"))
        if is_im and c.get("user"):
            name = user_display_name(c["user"])
        else:
            name = info.get("name") or c.get("name") or "Group DM"
        try:
            ts = float(latest.get("ts", 0)) if latest else 0
        except (TypeError, ValueError):
            ts = 0
        out.append({
            "channel": c["id"],
            "name": name,
            "unread": unread,
            "last_text": clean_text(latest.get("text", "")) if latest else "",
            "ts": ts,
            "is_im": is_im,
        })
    return out


def fetch_unread_dms(speed_mode="balanced", quick_poll_n=10, exclude_bots=True,
                    include_1to1=True, include_group=True):
    """Returns list of unread DM entries split by type via post-filter."""
    if speed_mode == "poll_only":
        results = _fetch_unread_dms_quick_poll(n=200, exclude_bots=exclude_bots)
    elif speed_mode == "search_only":
        results = _fetch_unread_dms_via_search(exclude_bots=exclude_bots)
    else:
        search = _fetch_unread_dms_via_search(exclude_bots=exclude_bots)
        poll = _fetch_unread_dms_quick_poll(n=quick_poll_n, exclude_bots=exclude_bots)
        merged = {d["channel"]: d for d in search}
        for d in poll:
            merged[d["channel"]] = d
        results = list(merged.values())
    if not include_1to1:
        results = [d for d in results if not d["is_im"]]
    if not include_group:
        results = [d for d in results if d["is_im"]]
    results.sort(key=lambda d: d["ts"], reverse=True)
    return results


# ----- @mentions in channels -----

def fetch_recent_mentions(my_user_id, hours=24, limit=15, exclude_bots=True,
                         exclude_channels=None):
    if not my_user_id:
        return []
    after = _after_date(hours)
    res = _search(f"<@{my_user_id}> after:{after}", count=limit * 2)
    if not res or not res.get("ok"):
        return []
    matches = (res.get("messages", {}) or {}).get("matches", []) or []
    cutoff = time.time() - hours * 3600
    excluded = set(c.lstrip("#") for c in (exclude_channels or []))

    kept = []
    for m in matches:
        try:
            ts = float(m.get("ts", 0))
        except (TypeError, ValueError):
            continue
        if ts < cutoff:
            continue
        if (m.get("user") or "") == my_user_id:
            continue
        if exclude_bots and _is_bot_message(m):
            continue
        ch = m.get("channel", {}) or {}
        if ch.get("is_im") or ch.get("is_mpim"):
            continue
        ch_name = (ch.get("name") or "").lstrip("#")
        if ch_name in excluded:
            continue
        kept.append((m, ts))

    prewarm_users({m.get("user") for m, _ in kept if m.get("user")})

    out = []
    for m, ts in kept[:limit]:
        ch = m.get("channel", {}) or {}
        out.append({
            "channel": ch.get("id"),
            "channel_name": ch.get("name") or "?",
            "author": user_display_name(m.get("user", "")) if m.get("user") else (m.get("username") or "bot"),
            "text": clean_text(m.get("text", "")),
            "permalink": m.get("permalink", ""),
            "ts": ts,
        })
    return out


# ----- Thread replies (new replies on threads I've participated in) -----

def _get_thread_replies(channel, thread_ts):
    out = slack_call("conversations.replies", {"channel": channel, "ts": thread_ts})
    if not out or not out.get("ok"):
        return []
    return out.get("messages", [])


def fetch_thread_replies(my_user_id, hours=48, max_threads=15, limit=8,
                        exclude_bots=True):
    if not my_user_id:
        return []
    after = _after_date(hours)
    res = _search(f"from:<@{my_user_id}> threaded:true after:{after}", count=50)
    if not res or not res.get("ok"):
        return []
    matches = (res.get("messages", {}) or {}).get("matches", []) or []

    seen = set()
    threads = []
    for m in matches:
        ch = m.get("channel", {}) or {}
        thread_ts = m.get("thread_ts") or m.get("ts")
        ch_id = ch.get("id")
        if not ch_id or not thread_ts:
            continue
        key = (ch_id, thread_ts)
        if key in seen:
            continue
        seen.add(key)
        threads.append({
            "channel_id": ch_id,
            "channel_name": ch.get("name") or "?",
            "thread_ts": thread_ts,
            "my_text": clean_text(m.get("text", "")),
            "my_ts": float(m.get("ts", 0)),
            "is_im": bool(ch.get("is_im")),
            "is_mpim": bool(ch.get("is_mpim")),
        })
        if len(threads) >= max_threads:
            break

    thread_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_get_thread_replies, t["channel_id"], t["thread_ts"]): t
                for t in threads}
        for t, replies in _drain(futs, HTTP_TIMEOUT * 2):
            thread_data[(t["channel_id"], t["thread_ts"])] = replies

    out = []
    for t in threads:
        replies = thread_data.get((t["channel_id"], t["thread_ts"]), [])
        new_replies = [
            r for r in replies
            if float(r.get("ts", 0)) > t["my_ts"]
            and r.get("user") != my_user_id
            and not (exclude_bots and _is_bot_message(r))
        ]
        if not new_replies:
            continue
        latest = max(new_replies, key=lambda r: float(r.get("ts", 0)))
        prewarm_users({latest.get("user")} if latest.get("user") else set())
        out.append({
            "channel_id": t["channel_id"],
            "channel_name": t["channel_name"],
            "thread_ts": t["thread_ts"],
            "my_preview": t["my_text"][:60],
            "new_reply_count": len(new_replies),
            "latest_author": user_display_name(latest.get("user", "")) if latest.get("user") else "",
            "latest_text": clean_text(latest.get("text", "")),
            "latest_ts": float(latest.get("ts", 0)),
            "is_dm": t["is_im"] or t["is_mpim"],
        })
    out.sort(key=lambda r: r["latest_ts"], reverse=True)
    return out[:limit]


# ----- Keyword watchlist -----

def fetch_keyword_matches(keywords, my_user_id, hours=24, max_per_keyword=5,
                         exclude_bots=True, exclude_channels=None):
    if not keywords:
        return []
    after = _after_date(hours)
    cutoff = time.time() - hours * 3600
    excluded = set(c.lstrip("#") for c in (exclude_channels or []))

    keyword_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_search, f'"{kw}" after:{after}', max_per_keyword * 3): kw
                for kw in keywords}
        for kw, res in _drain(futs, HTTP_TIMEOUT * 2):
            if res and res.get("ok"):
                keyword_results[kw] = (res.get("messages", {}) or {}).get("matches", []) or []

    out = []
    seen = set()
    for kw in keywords:
        matches = keyword_results.get(kw, [])
        kept_for_kw = 0
        for m in matches:
            ch = m.get("channel", {}) or {}
            ch_id = ch.get("id")
            ts_raw = m.get("ts")
            if not ch_id or not ts_raw:
                continue
            try:
                ts = float(ts_raw)
            except (TypeError, ValueError):
                continue
            if ts < cutoff:
                continue
            if (m.get("user") or "") == my_user_id:
                continue
            if exclude_bots and _is_bot_message(m):
                continue
            ch_name = (ch.get("name") or "").lstrip("#")
            if ch_name in excluded:
                continue
            key = (ch_id, ts_raw)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "keyword": kw,
                "channel_id": ch_id,
                "channel_name": ch.get("name") or "?",
                "author": user_display_name(m.get("user", "")) if m.get("user") else (m.get("username") or "bot"),
                "text": clean_text(m.get("text", "")),
                "permalink": m.get("permalink", ""),
                "ts": ts,
            })
            kept_for_kw += 1
            if kept_for_kw >= max_per_keyword:
                break

    prewarm_users({k["author"] for k in out if k["author"]})
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


# ----- Watched channels (full feed for specific channels) -----

def fetch_watched_channels(channel_names, my_user_id=None, hours=6,
                          max_per_channel=5, exclude_bots=True):
    """Return latest messages from each watched channel grouped by channel.
    Each group is {channel_name, channel_id, messages: [...]}."""
    if not channel_names:
        return []
    after = _after_date(hours)
    cutoff = time.time() - hours * 3600

    channel_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {
            ex.submit(_search, f"in:#{ch.lstrip('#')} after:{after}",
                     max_per_channel * 3): ch.lstrip("#")
            for ch in channel_names
        }
        for ch_name, res in _drain(futs, HTTP_TIMEOUT * 2):
            if res and res.get("ok"):
                channel_results[ch_name] = (res.get("messages", {}) or {}).get("matches", []) or []

    groups = []
    for ch_name in (c.lstrip("#") for c in channel_names):
        matches = channel_results.get(ch_name, [])
        kept = []
        for m in matches:
            try:
                ts = float(m.get("ts", 0))
            except (TypeError, ValueError):
                continue
            if ts < cutoff:
                continue
            if my_user_id and (m.get("user") or "") == my_user_id:
                continue
            if exclude_bots and _is_bot_message(m):
                continue
            ch_obj = m.get("channel", {}) or {}
            kept.append({
                "author": user_display_name(m.get("user", "")) if m.get("user") else (m.get("username") or "bot"),
                "text": clean_text(m.get("text", "")),
                "permalink": m.get("permalink", ""),
                "ts": ts,
                "channel_id": ch_obj.get("id"),
            })
            if len(kept) >= max_per_channel:
                break
        if not kept:
            continue
        kept.sort(key=lambda x: x["ts"], reverse=True)
        groups.append({
            "channel_name": ch_name,
            "channel_id": kept[0]["channel_id"],
            "messages": kept,
        })
    prewarm_users({msg["author"] for g in groups for msg in g["messages"] if msg["author"]})
    return groups


# ----- Util -----

def relative_age(ts):
    if not ts:
        return ""
    secs = int(time.time() - ts)
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def slack_app_url(team_id, channel_id, message_ts=None):
    if not team_id or not channel_id:
        return ""
    base = f"slack://channel?team={team_id}&id={channel_id}"
    if message_ts:
        base += f"&message={message_ts}"
    return base


def finalize():
    """Persist any in-memory caches to disk. Call at end of plugin run."""
    if _user_cache:
        _flush_user_cache()
