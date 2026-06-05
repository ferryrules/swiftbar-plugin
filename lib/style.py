"""Visual constants for the swiftbar-dashboard plugins.

Edit here to retheme the menubar — colors, emojis, ANSI codes, priority
styles, and state icons all live in this one file.
"""

# ----- ANSI codes (used in the menubar with `ansi=true`) -----
ANSI_RESET = "\033[0m"

# Standard 16-color ANSI (GitHub PR menubar segments)
ANSI_YELLOW = "\033[33m"
ANSI_GREEN = "\033[32m"
ANSI_PURPLE = "\033[35m"
ANSI_CYAN = "\033[36m"

# 256-color ANSI (Linear priorities)
ANSI_URGENT = "\033[38;5;196m"
ANSI_HIGH = "\033[38;5;203m"
ANSI_MEDIUM = "\033[38;5;208m"
ANSI_LOW = "\033[38;5;220m"
ANSI_NEUTRAL = "\033[38;5;244m"

# ----- Hex palette (dropdown menu, GitHub-ish dark theme) -----
HEX_TEXT = "#c9d1d9"
HEX_MUTED = "#8b949e"
HEX_DIM = "#484f58"
HEX_WARN = "#e3b341"
HEX_GREEN = "#3fb950"
HEX_PURPLE = "#a371f7"
HEX_BLUE = "#58a6ff"

# ----- GitHub PR states -----
# state_key -> (hex_color, emoji)
PR_STATE_STYLE = {
    "ready":       (HEX_GREEN,  "✅"),
    "in_progress": (HEX_WARN,   "⏳"),
    "draft":       (HEX_MUTED,  "📝"),
    "merged":      (HEX_PURPLE, "🟣"),
}

# state -> sort rank within a repo group
PR_STATE_RANK = {"ready": 0, "in_progress": 1, "draft": 2, "merged": 3}

# CI rollup state -> menubar suffix
CI_ICON = {"SUCCESS": " ✓", "FAILURE": " ✗", "PENDING": " ⏳"}

# ----- Linear priorities -----
# priority int -> (hex_color, ansi_code)
LINEAR_PRIORITY_STYLE = {
    1: ("#ff4444", ANSI_URGENT),  # Urgent - bright red
    2: ("#ef4444", ANSI_HIGH),    # High    - red
    3: ("#fb923c", ANSI_MEDIUM),  # Medium  - orange
    4: ("#fbbf24", ANSI_LOW),     # Low     - yellow
    0: ("#6b7280", ANSI_NEUTRAL), # None    - gray
}

# Display order: urgent → high → med → low → none
LINEAR_PRIORITY_ORDER = [1, 2, 3, 4, 0]

# ----- Linear workflow states -----
# Section ordering in the dropdown
STATE_TYPE_RANK = {
    "started": 0,
    "unstarted": 1,
    "backlog": 2,
    "triage": 3,
    "completed": 4,
    "canceled": 5,
}

# Default icon by Linear state type
STATE_TYPE_ICON = {
    "started": "🟢",
    "unstarted": "🟡",
    "backlog": "💤",
    "triage": "🔧",
    "completed": "✅",
    "canceled": "❌",
}

# Per-state-name overrides (case-insensitive). Falls back to STATE_TYPE_ICON.
STATE_NAME_ICON = {
    "in progress": "🟢",
    "in review": "👀",
    "todo": "☐",
    "backlog": "💤",
    "icebox": "🧊",
    "triage": "🔧",
    "done": "✅",
    "on staging": "🚧",
    "on prod": "🚀",
    "closed": "🔒",
    "canceled": "❌",
    "cancelled": "❌",
    "duplicate": "👯",
}


def state_icon(name, state_type):
    """Pick the best icon for a Linear workflow state."""
    return STATE_NAME_ICON.get((name or "").lower()) or STATE_TYPE_ICON.get(state_type, "·")


# ----- Generic UI emojis -----
EMOJI_WARN = "⚠️"
EMOJI_REFRESH = "↻"
EMOJI_REPO = "📦"
EMOJI_CLIPBOARD = "📋"
EMOJI_CURSOR = "💻"
EMOJI_MOVE = "↪"
EMOJI_SEARCH = "🔍"
EMOJI_BOOK = "📖"
EMOJI_FOLDER = "📁"
EMOJI_REVIEW = "👀"

# ----- Linear issue relationship & metadata emojis -----
EMOJI_BLOCKED = "🚫"      # this ticket is blocked by another
EMOJI_BLOCKS = "⛔"       # this ticket blocks another
EMOJI_RELATED = "🔗"      # related tickets
EMOJI_PARENT = "↳"        # parent ticket link
EMOJI_SUBISSUES = "🌳"    # has sub-issues
EMOJI_PROJECT = "🗂"      # project
EMOJI_MILESTONE = "🏁"    # project milestone
EMOJI_COMMENT = "💬"      # comments
EMOJI_HISTORY = "🔄"      # activity / history events
EMOJI_ATTACHMENT = "📎"   # attachments
