"""Browser sources: Chrome-family history (WAL-aware) + currently-open tabs (osascript)."""

import re
from pathlib import Path

from .. import core

CHROME_FAMILY_DBS = [
    Path.home() / "Library/Application Support/Google/Chrome/Default/History",
    Path.home() / "Library/Application Support/Arc/User Data/Default/History",
    Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Default/History",
    Path.home() / "Library/Application Support/Microsoft Edge/Default/History",
]

SIGNAL_DOMAINS = (
    "github.com", "linear.app", "outline", "datadoghq", "console.aws",
    "grafana", "notion.so", "docs.google.com", "stackoverflow.com",
    "kubernetes.io", "terraform.io", "vault", "argo", "runai",
)

# Auth/SSO/loading pages — never useful context.
BROWSER_NOISE = (
    "sign-in", "sign in", "signin", "my sign-ins", "log in", "login",
    "sign in to your account", "redirecting", "loading", "new tab",
    "authenticator", "verify your identity", "duo", "okta", "sso",
    "my account", "verification code", "email verification",
    "two-factor", "2fa", "captcha", "just a moment",
)
NOISE_DOMAINS = (
    "login.microsoftonline.com", "accounts.google.com",
    "login.live.com", "mysignins.microsoft.com", "device.login",
)


def _domain(url):
    m = re.match(r"https?://([^/]+)/?", url or "")
    return m.group(1).replace("www.", "") if m else ""


def _is_signal(url):
    return any(d in _domain(url) for d in SIGNAL_DOMAINS)


def _is_noise(title, url):
    t = (title or "").strip().lower()
    if not t:
        return True
    if any(n in t for n in BROWSER_NOISE):
        return True
    return any(n in _domain(url) for n in NOISE_DOMAINS)


# Seconds between the Chrome epoch (1601-01-01) and the Unix epoch.
CHROME_EPOCH_OFFSET = 11644473600


def fetch_history(since_ts, limit=40):
    """Recent browser visits since `since_ts`, de-duped, noise-filtered, work-domains tagged signal=True."""
    out = []
    for db_path in CHROME_FAMILY_DBS:
        if not db_path.exists():
            continue
        tmp = None
        try:
            tmp = core.copy_sqlite(db_path)
            con = core.open_readonly(tmp)
            since_chrome = int((since_ts + CHROME_EPOCH_OFFSET) * 1_000_000)
            rows = con.execute(
                """
                SELECT u.url AS url, u.title AS title, v.visit_time AS vt
                FROM visits v JOIN urls u ON u.id = v.url
                WHERE v.visit_time > ?
                ORDER BY v.visit_time DESC
                LIMIT ?
                """,
                (since_chrome, limit),
            ).fetchall()
            con.close()
            for r in rows:
                ts = r["vt"] / 1_000_000 - CHROME_EPOCH_OFFSET
                out.append({
                    "ts": ts, "kind": "web", "icon": "🌐",
                    "title": r["title"] or _domain(r["url"]),
                    "url": r["url"], "domain": _domain(r["url"]),
                })
        except Exception:
            continue
        finally:
            core.cleanup_sqlite(tmp)

    seen_urls, seen_titles, deduped = set(), set(), []
    for v in sorted(out, key=lambda x: -x["ts"]):
        title_key = (v["title"] or "").strip().lower()
        if v["url"] in seen_urls or title_key in seen_titles:
            continue
        if _is_noise(v["title"], v["url"]):
            continue
        seen_urls.add(v["url"])
        seen_titles.add(title_key)
        v["signal"] = _is_signal(v["url"])
        deduped.append(v)
    return deduped


# Currently-open tabs (live, via osascript).

# Inside `tell application "Google Chrome"` (and Arc/Safari), bare `tab` is the *tab class* — use `character id 9` for the real ASCII-9 tab character.
_TAB_SCRIPT_CHROME = '''tell application "Google Chrome"
  set TAB_CHAR to (character id 9)
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      set out to out & (title of t) & TAB_CHAR & (URL of t) & linefeed
    end repeat
  end repeat
  return out
end tell'''

_TAB_SCRIPT_ARC = '''tell application "Arc"
  set TAB_CHAR to (character id 9)
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      set out to out & (title of t) & TAB_CHAR & (URL of t) & linefeed
    end repeat
  end repeat
  return out
end tell'''

_TAB_SCRIPT_SAFARI = '''tell application "Safari"
  set TAB_CHAR to (character id 9)
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      set out to out & (name of t) & TAB_CHAR & (URL of t) & linefeed
    end repeat
  end repeat
  return out
end tell'''

# (process name as `pgrep -x` sees it, friendly name, script).
_TAB_BROWSERS = [
    ("Google Chrome", "Chrome", _TAB_SCRIPT_CHROME),
    ("Arc",           "Arc",    _TAB_SCRIPT_ARC),
    ("Safari",        "Safari", _TAB_SCRIPT_SAFARI),
]


def fetch_open_tabs():
    """Currently-open browser tabs across Chrome / Arc / Safari, de-duped by URL.

    Returns: {"tabs": [...], "denied": [browsers we couldn't read]} so the
    plugin can surface a 'grant browser automation' fix-it link.
    """
    import time
    now = time.time()
    seen, out, denied = set(), [], []
    for proc_name, browser, script in _TAB_BROWSERS:
        if not core.is_app_running(proc_name):
            continue
        stdout, stderr, rc = core.osascript_full(script, timeout=3)
        if rc != 0:
            if "-1743" in stderr or "Not authorized" in stderr:
                denied.append(browser)
            continue
        for line in stdout.splitlines():
            if "\t" not in line:
                continue
            title, url = line.split("\t", 1)
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                continue
            if url in seen:
                continue
            if _is_noise(title, url):
                continue
            seen.add(url)
            out.append({
                "ts": now, "kind": "tab", "icon": "📑",
                "title": (title or _domain(url)).strip(),
                "url": url, "domain": _domain(url),
                "browser": browser, "signal": _is_signal(url),
            })
    out.sort(key=lambda t: (0 if t["signal"] else 1, t["title"].lower()))
    return {"tabs": out, "denied": denied}
