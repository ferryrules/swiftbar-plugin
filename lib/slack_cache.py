"""Persistent caches for Slack auth + user display names.

Lives at <repo>/.cache/slack-*.json so it survives plugin runs and
SwiftBar restarts.
"""

import hashlib
import json
import os
import time

from paths import CACHE_DIR, SLACK_AUTH_CACHE, SLACK_USERS_CACHE

AUTH_FILE = SLACK_AUTH_CACHE
USERS_FILE = SLACK_USERS_CACHE

USERS_TTL_SEC = 7 * 24 * 3600


def token_hash():
    t = os.environ.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_TOKEN") or ""
    return hashlib.sha256(t.encode()).hexdigest()[:12] if t else ""


def load_auth():
    """Return (team_id, user_id, user_name, team_name) or None.
    Skips cache if token has changed since last save."""
    try:
        data = json.loads(AUTH_FILE.read_text())
    except Exception:
        return None
    if data.get("token_hash") != token_hash():
        return None
    return (data.get("team_id"), data.get("user_id"), data.get("user_name"), data.get("team_name"))


def save_auth(team_id, user_id, user_name, team_name):
    if not team_id or not user_id:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps({
        "token_hash": token_hash(),
        "team_id": team_id,
        "user_id": user_id,
        "user_name": user_name,
        "team_name": team_name,
        "saved_at": int(time.time()),
    }))


def load_users():
    """Return {user_id: name} for non-expired entries."""
    try:
        data = json.loads(USERS_FILE.read_text())
    except Exception:
        return {}
    if data.get("token_hash") != token_hash():
        return {}
    now = time.time()
    return {
        uid: entry["name"]
        for uid, entry in (data.get("users") or {}).items()
        if now - entry.get("saved_at", 0) < USERS_TTL_SEC
    }


def save_users(cache):
    """cache: {user_id: name} mapping."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    USERS_FILE.write_text(json.dumps({
        "token_hash": token_hash(),
        "users": {uid: {"name": name, "saved_at": now} for uid, name in cache.items()},
    }))
