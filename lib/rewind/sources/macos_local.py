"""Local-only macOS sources: Notes, Stickies, Reminders, clipboard.

Anything in this file is content-bearing user data. The privacy boundary
(see ../privacy.py) keeps everything here on the box — none of it goes to
Claude. We render it locally in the menubar so the user can see it, but
build_claude_payload() filters all of it out.
"""

import subprocess
from pathlib import Path

from .. import core

NOTES_DB = Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
STICKIES_DIR = Path.home() / "Library/Containers/com.apple.Stickies/Data/Library/Stickies"


def fetch_notes(since_ts):
    if not NOTES_DB.exists():
        return []
    tmp = None
    try:
        tmp = core.copy_sqlite(NOTES_DB)
        con = core.open_readonly(tmp)
        since_mac = since_ts - core.MAC_EPOCH_OFFSET
        rows = con.execute(
            """
            SELECT ZTITLE1 AS title, ZMODIFICATIONDATE1 AS mod
            FROM ZICCLOUDSYNCINGOBJECT
            WHERE ZTITLE1 IS NOT NULL
              AND ZMODIFICATIONDATE1 IS NOT NULL
              AND ZMODIFICATIONDATE1 > ?
              AND (ZMARKEDFORDELETION IS NULL OR ZMARKEDFORDELETION = 0)
            ORDER BY ZMODIFICATIONDATE1 DESC
            LIMIT 10
            """,
            (since_mac,),
        ).fetchall()
        con.close()
    except Exception:
        return []
    finally:
        core.cleanup_sqlite(tmp)

    return [
        {
            "ts": r["mod"] + core.MAC_EPOCH_OFFSET,
            "kind": "note", "icon": "📒",
            "title": f"edited note: {r['title']}", "url": "",
            "claude_safe": False,
        }
        for r in rows
    ]


def fetch_stickies(since_ts):
    if not STICKIES_DIR.exists():
        return []
    out = []
    for rtfd in STICKIES_DIR.glob("*.rtfd"):
        try:
            mtime = rtfd.stat().st_mtime
            if mtime < since_ts:
                continue
        except OSError:
            continue
        first_line = ""
        try:
            txt = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", str(rtfd)],
                capture_output=True, text=True, timeout=4, check=False,
            ).stdout
            first_line = next((l.strip() for l in txt.splitlines() if l.strip()), "")
        except Exception:
            first_line = ""
        label = first_line[:40] if first_line else "(sticky note)"
        out.append({
            "ts": mtime, "kind": "sticky", "icon": "🗒️",
            "title": f"sticky: {label}", "url": "", "claude_safe": False,
        })
    return out


def fetch_reminders():
    """Open reminders (current state, not a timeline event)."""
    script = (
        'tell application "Reminders"\n'
        '  set out to ""\n'
        '  repeat with r in (reminders whose completed is false)\n'
        '    set out to out & (name of r) & "\\n"\n'
        '  end repeat\n'
        '  return out\n'
        'end tell'
    )
    raw = core.osascript(script, timeout=6)
    items = [l.strip() for l in raw.splitlines() if l.strip()]
    return [{"kind": "reminder", "title": t, "claude_safe": False} for t in items[:8]]


def fetch_clipboard():
    """Snapshot of the current clipboard. Local-only."""
    try:
        text = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=3, check=False,
        ).stdout
    except Exception:
        return None
    text = (text or "").strip()
    if not text:
        return None
    one_line = " ".join(text.split())
    return {
        "kind": "clipboard", "text": one_line, "claude_safe": False,
        "lines": text.count("\n") + 1, "chars": len(text),
    }
