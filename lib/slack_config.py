"""Slack plugin config — edit this file directly.

This is the single source of truth for what the Slack menubar plugin shows.
Change the values below, save, and the next plugin refresh picks them up.

Reference / recipe examples: docs/slack-config-reference.md
"""

from pathlib import Path

CONFIG_FILE = Path(__file__).resolve()


CONFIG = {

    # ----- Which sections show up in the dropdown -----
    "show": {
        "dms":             True,   # unread 1:1 DMs
        "group_dms":       True,   # unread group DMs (mpims)
        "mentions":        True,   # @you mentions in channels
        "thread_replies":  True,   # new replies to threads I'm in
        "keywords":        True,   # keyword watchlist (see "keywords" below)
        "watched_channels": True,  # every message in channels listed in "watched_channels"
    },

    # ----- Time windows (in hours) -----
    "windows": {
        "mention_hours":         24,
        "thread_hours":          48,
        "keyword_hours":         24,
        "watched_channel_hours":  6,
    },
    "keywords": ["ferris", "devpod"], # Case-insensitive string match across all channels you're in.

    "watched_channels": ["infra-internal", "devpod-help"], # Every message in these channels will surface in the dropdown (excluding your own messages, and bots if exclude_bots=True).

    # ----- Filters that apply everywhere -----
    "filters": {
        "exclude_bots":      True, # Hide messages posted by bots / apps.
        "show_preview":      True,
        "exclude_channels":  ["standup"], # Hide matches from these channels (mentions + keywords).
    },

    # ----- Max items rendered per section -----
    "limits": {
        "dms":                       8,
        "mentions":                 10,
        "thread_replies":            8,
        "keywords":                  6,
        "watched_channel_messages":  5,
        "quick_poll":               10,   # how many recent DMs we poll for real-time
    },

    # ----- Speed vs real-time accuracy -----
    # "balanced"    — ~1s, top 10 DMs real-time, older lags 30-90s   (recommended)
    # "search_only" — ~0.5s, EVERYTHING lags 30-90s
    # "poll_only"   — ~3s+, fully real-time, no search-index lag
    "speed_mode": "balanced",
}


def load_config():
    return CONFIG
