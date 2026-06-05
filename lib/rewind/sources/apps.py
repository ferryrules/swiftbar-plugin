"""macOS app focus history (knowledgeC.db) + real-time frontmost-app snapshot (osascript)."""

from pathlib import Path

from .. import core

KNOWLEDGE_DB = Path.home() / "Library/Application Support/Knowledge/knowledgeC.db"

# Friendly names for common app bundle IDs.
APP_NAMES = {
    "com.tinyspeck.slackmacgap": "Slack",
    "com.google.Chrome": "Chrome",
    "company.thebrowser.Browser": "Arc",
    "com.apple.Safari": "Safari",
    "com.todesktop.230313mzl4w4u92": "Cursor",
    "com.microsoft.VSCode": "VS Code",
    "us.zoom.xos": "Zoom",
    "com.apple.Terminal": "Terminal",
    "com.googlecode.iterm2": "iTerm",
    "com.apple.dt.Xcode": "Xcode",
    "com.apple.Notes": "Notes",
    "com.apple.reminders": "Reminders",
    "com.apple.mail": "Mail",
    "com.apple.iCal": "Calendar",
    "md.obsidian": "Obsidian",
    "notion.id": "Notion",
    "com.figma.Desktop": "Figma",
    "com.postmanlabs.mac": "Postman",
    "com.hnc.Discord": "Discord",
    "com.apple.finder": "Finder",
    "com.docker.docker": "Docker",
    "com.anthropic.claudefordesktop": "Claude",
    "com.apple.systempreferences": "System Settings",
    "com.apple.SystemSettings": "System Settings",
}


def friendly_app(bundle_or_name):
    if not bundle_or_name:
        return ""
    if bundle_or_name in APP_NAMES:
        return APP_NAMES[bundle_or_name]
    if "." in bundle_or_name:
        name = bundle_or_name.split(".")[-1]
        return name[:1].upper() + name[1:] if name else bundle_or_name
    return bundle_or_name


def fetch_apps(since_ts):
    """Apps focused since `since_ts`, newest first, de-duped per app; empty if Full Disk Access isn't granted."""
    if not KNOWLEDGE_DB.exists():
        return []
    tmp = None
    try:
        tmp = core.copy_sqlite(KNOWLEDGE_DB)
        con = core.open_readonly(tmp)
        since_mac = since_ts - core.MAC_EPOCH_OFFSET
        rows = con.execute(
            """
            SELECT ZVALUESTRING AS bundle,
                   MAX(ZENDDATE) AS end_mac,
                   SUM(ZENDDATE - ZSTARTDATE) AS secs
            FROM ZOBJECT
            WHERE ZSTREAMNAME IN ('/app/inFocus', '/app/usage')
              AND ZENDDATE > ?
              AND ZVALUESTRING IS NOT NULL
            GROUP BY ZVALUESTRING
            ORDER BY end_mac DESC
            LIMIT 25
            """,
            (since_mac,),
        ).fetchall()
        con.close()
    except Exception:
        return []
    finally:
        core.cleanup_sqlite(tmp)

    out = []
    for r in rows:
        secs = int(r["secs"] or 0)
        mins = max(1, secs // 60)
        out.append({
            "ts": r["end_mac"] + core.MAC_EPOCH_OFFSET,
            "kind": "app", "icon": "🪟",
            "title": friendly_app(r["bundle"]),
            "app": friendly_app(r["bundle"]),
            "bundle": r["bundle"] or "",
            "focus_min": mins,
            "url": "",
        })
    return out


_FRONTMOST_SCRIPT = (
    'tell application "System Events"\n'
    '  set frontApp to first application process whose frontmost is true\n'
    '  set appName to name of frontApp\n'
    '  set appBundle to ""\n'
    '  try\n'
    '    set appBundle to bundle identifier of frontApp\n'
    '  end try\n'
    '  set winTitle to ""\n'
    '  try\n'
    '    set winTitle to name of front window of frontApp\n'
    '  end try\n'
    'end tell\n'
    'return appName & (character id 9) & appBundle & (character id 9) & winTitle'
)


def fetch_frontmost():
    """Real-time osascript snapshot of the frontmost app (knowledgeC won't include the in-progress focus session)."""
    raw = core.osascript(_FRONTMOST_SCRIPT, timeout=2).strip()
    if not raw:
        return None
    parts = raw.split("\t", 2)
    name = parts[0].strip() if len(parts) > 0 else ""
    bundle = parts[1].strip() if len(parts) > 1 else ""
    window = parts[2].strip() if len(parts) > 2 else ""
    return {"app": friendly_app(bundle) or friendly_app(name), "bundle": bundle, "window": window}


def fetch_app_at(ts):
    """Whichever app's focus session contained `ts` (or, failing that, the most recent session ending at-or-before `ts`).

    Used by Rewind during 'ignore last N min': fetch_apps' GROUP BY MAX(ZENDDATE)
    reports a still-open Cursor session as ending 'now' so the ignore upper bound
    drops it; this query asks the more useful 'who was on screen at moment T'.
    """
    if not KNOWLEDGE_DB.exists():
        return None
    target_mac = ts - core.MAC_EPOCH_OFFSET
    tmp = None
    try:
        tmp = core.copy_sqlite(KNOWLEDGE_DB)
        con = core.open_readonly(tmp)
        row = con.execute(
            """
            SELECT ZVALUESTRING AS bundle, ZENDDATE AS end_mac
            FROM ZOBJECT
            WHERE ZSTREAMNAME IN ('/app/inFocus', '/app/usage')
              AND ZSTARTDATE <= ? AND ZENDDATE >= ?
              AND ZVALUESTRING IS NOT NULL
            ORDER BY (ZENDDATE - ZSTARTDATE) DESC
            LIMIT 1
            """,
            (target_mac, target_mac),
        ).fetchone()
        if not row:
            row = con.execute(
                """
                SELECT ZVALUESTRING AS bundle, ZENDDATE AS end_mac
                FROM ZOBJECT
                WHERE ZSTREAMNAME IN ('/app/inFocus', '/app/usage')
                  AND ZENDDATE <= ?
                  AND ZVALUESTRING IS NOT NULL
                ORDER BY end_mac DESC
                LIMIT 1
                """,
                (target_mac,),
            ).fetchone()
        con.close()
    except Exception:
        return None
    finally:
        core.cleanup_sqlite(tmp)

    if not row:
        return None
    bundle = row["bundle"] or ""
    end_mac = row["end_mac"]
    return {
        "app": friendly_app(bundle),
        "bundle": bundle,
        "ts": (end_mac + core.MAC_EPOCH_OFFSET) if end_mac else ts,
    }


def merge_frontmost_into_apps(apps_list, frontmost, ts=None):
    """Inject a frontmost app into the apps list when knowledgeC didn't record it.

    Electron apps (Cursor, VS Code, Slack-on-some-versions, Discord, …)
    occasionally skip macOS's NSUserActivity logging, so `fetch_apps`
    never sees them. The live osascript frontmost probe always sees them
    though, so we use that as ground truth for 'right now'."""
    import time as _time
    if not frontmost:
        return apps_list
    bundle = (frontmost or {}).get("bundle")
    if not bundle:
        return apps_list
    apps_list = list(apps_list or [])
    if apps_list and apps_list[0].get("bundle") == bundle:
        return apps_list
    apps_list.insert(0, {
        "ts": ts or _time.time(),
        "kind": "app", "icon": "🪟",
        "title": frontmost.get("app") or "",
        "app": frontmost.get("app") or "",
        "bundle": bundle,
        "focus_min": 1,
        "url": "",
        "live": True,
    })
    return apps_list


def needs_full_disk_access():
    """True if knowledgeC exists but we can't read it."""
    if not KNOWLEDGE_DB.exists():
        return False
    tmp = None
    try:
        tmp = core.copy_sqlite(KNOWLEDGE_DB)
        con = core.open_readonly(tmp)
        con.execute("SELECT 1 FROM ZOBJECT LIMIT 1").fetchone()
        con.close()
        return False
    except Exception:
        return True
    finally:
        core.cleanup_sqlite(tmp)
