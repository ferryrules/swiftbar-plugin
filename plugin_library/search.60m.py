#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Doc Search</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Unified search across Outline, GitHub, Google Drive</bitbar.desc>
# <swiftbar.refreshOnOpen>false</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from dashboard import api_request, load_env, print_footer
from paths import SEARCH_RECENT, SEARCH_RESULT_HTML, ensure_dirs
from style import EMOJI_BOOK, EMOJI_FOLDER, EMOJI_CURSOR, EMOJI_SEARCH

ensure_dirs()
RECENT_FILE = SEARCH_RECENT
RESULTS_FILE = SEARCH_RESULT_HTML
PLUGIN_PATH = os.path.abspath(__file__)

load_env()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTLINE_API_KEY = os.environ.get("OUTLINE_API_KEY", "")
_OUTLINE_RAW = os.environ.get("OUTLINE_BASE_URL", "").rstrip("/")
# Be forgiving: strip trailing /api if user included it
OUTLINE_BASE_URL = _OUTLINE_RAW[:-4] if _OUTLINE_RAW.endswith("/api") else _OUTLINE_RAW
GITHUB_ORG = os.environ.get("GITHUB_ORG", "twothinkinc")


# ---------------------------------------------------------------------------
# Recent searches
# ---------------------------------------------------------------------------


def load_recent():
    if not RECENT_FILE.exists():
        return []
    try:
        return json.loads(RECENT_FILE.read_text())
    except Exception:
        return []


def save_recent(query):
    recent = load_recent()
    if query in recent:
        recent.remove(query)
    recent.insert(0, query)
    recent = recent[:8]
    try:
        RECENT_FILE.write_text(json.dumps(recent))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Search backends
# ---------------------------------------------------------------------------


def search_outline(query):
    if not OUTLINE_API_KEY or not OUTLINE_BASE_URL:
        return []
    result = api_request(
        f"{OUTLINE_BASE_URL}/api/documents.search",
        headers={"Authorization": f"Bearer {OUTLINE_API_KEY}"},
        data={"query": query, "limit": 15},
    )
    if not result or "data" not in result:
        return []
    out = []
    for item in result["data"]:
        doc = item.get("document", {})
        out.append({
            "title": doc.get("title", "Untitled"),
            "url": f"{OUTLINE_BASE_URL}{doc.get('url', '')}",
            "snippet": (item.get("context") or "")[:240],
            "source": "Outline",
        })
    return out


def search_github_code(query):
    if not GITHUB_TOKEN:
        return []
    encoded = urllib.parse.quote(f"{query} org:{GITHUB_ORG}")
    result = api_request(
        f"https://api.github.com/search/code?q={encoded}&per_page=15",
        headers={
            "Authorization": f"bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    if not result or "items" not in result:
        return []
    out = []
    for item in result["items"]:
        repo = item.get("repository", {}).get("full_name", "")
        out.append({
            "title": item.get("name", ""),
            "url": item.get("html_url", ""),
            "snippet": f"{repo} / {item.get('path', '')}",
            "source": "GitHub",
        })
    return out


def google_drive_search_url(query):
    return f"https://drive.google.com/drive/search?q={urllib.parse.quote(query)}"


# ---------------------------------------------------------------------------
# HTML results
# ---------------------------------------------------------------------------


def html_escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html(query, outline_results, github_results, drive_url):
    q = html_escape(query)

    def render_result(r):
        return f"""<div class="result">
  <a href="{html_escape(r['url'])}" target="_blank">{html_escape(r['title'])}</a>
  <span class="badge badge-{r['source'].lower()}">{r['source']}</span>
  <p class="snippet">{html_escape(r.get('snippet', ''))}</p>
</div>"""

    ol = "\n".join(render_result(r) for r in outline_results) if outline_results else '<p class="empty">No results</p>'
    gh = "\n".join(render_result(r) for r in github_results) if github_results else '<p class="empty">No results</p>'
    total = len(outline_results) + len(github_results)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><title>Search: {q}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"SF Pro",system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:32px;max-width:860px;margin:0 auto;line-height:1.5}}
header{{display:flex;align-items:baseline;gap:12px;margin-bottom:32px;padding-bottom:16px;border-bottom:1px solid #21262d}}
h1{{font-size:20px;color:#f0f6fc;font-weight:600}}
h1 .q{{color:#58a6ff}}
.count{{font-size:13px;color:#8b949e}}
h2{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:.8px;margin:32px 0 12px;font-weight:600}}
.result{{padding:14px 16px;margin:8px 0;background:#161b22;border-radius:8px;border:1px solid #21262d;transition:all .15s}}
.result:hover{{border-color:#388bfd;background:#1c2128}}
.result a{{color:#58a6ff;text-decoration:none;font-size:15px;font-weight:500}}
.result a:hover{{text-decoration:underline}}
.badge{{font-size:10px;color:#8b949e;background:#21262d;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle;text-transform:uppercase;letter-spacing:.5px;font-weight:600}}
.badge-outline{{background:#1f6feb33;color:#79c0ff}}
.badge-github{{background:#23863633;color:#7ee787}}
.snippet{{color:#8b949e;font-size:13px;margin-top:6px}}
.empty{{color:#484f58;font-style:italic;padding:14px 16px;background:#161b22;border-radius:8px;border:1px solid #21262d}}
.drive{{display:inline-flex;align-items:center;margin-top:8px;padding:12px 20px;background:#238636;color:#fff;border-radius:8px;text-decoration:none;font-size:14px;font-weight:500;transition:background .15s}}
.drive:hover{{background:#2ea043}}
.drive::after{{content:" →";margin-left:6px}}
</style>
</head>
<body>
<header>
  <h1>Results for <span class="q">"{q}"</span></h1>
  <span class="count">{total} matches across Outline + GitHub</span>
</header>

<h2>Outline Wiki ({len(outline_results)})</h2>
{ol}

<h2>GitHub Code ({len(github_results)})</h2>
{gh}

<h2>Google Drive</h2>
<a href="{html_escape(drive_url)}" target="_blank" class="drive">Search Google Drive for "{q}"</a>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def prompt_for_query(default=""):
    default_escaped = default.replace('"', '\\"')
    script = (
        'tell application "System Events"\n'
        f'  display dialog "Search docs:" default answer "{default_escaped}" '
        'buttons {"Cancel","Search"} default button "Search" '
        'with title "Doc Search"\n'
        '  set q to text returned of result\n'
        "end tell"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None
    except Exception:
        return None


def cmd_search(initial=""):
    query = prompt_for_query(initial)
    if not query:
        return

    save_recent(query)

    outline = search_outline(query)
    github = search_github_code(query)
    drive_url = google_drive_search_url(query)

    html = render_html(query, outline, github, drive_url)
    RESULTS_FILE.write_text(html)
    subprocess.run(["open", str(RESULTS_FILE)])


def cmd_render():
    print(EMOJI_SEARCH)
    print("---")
    print(f"{EMOJI_SEARCH} Search docs… | bash='{PLUGIN_PATH}' param1=search terminal=false refresh=false")
    print("---")

    recent = load_recent()
    if recent:
        print("Recent")
        for q in recent:
            safe = q.replace("'", "")
            print(f"--{q} | bash='{PLUGIN_PATH}' param1=search param2='{safe}' terminal=false refresh=false")
        print("---")

    print("Jump to")
    if OUTLINE_BASE_URL:
        print(f"--{EMOJI_BOOK} Outline Wiki | href={OUTLINE_BASE_URL}")
    print(f"--{EMOJI_CURSOR} GitHub ({GITHUB_ORG}) | href=https://github.com/{GITHUB_ORG}")
    print(f"--{EMOJI_FOLDER} Google Drive | href=https://drive.google.com")

    print_footer(label="Loaded")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        initial = sys.argv[2] if len(sys.argv) > 2 else ""
        cmd_search(initial)
        return
    cmd_render()


if __name__ == "__main__":
    main()
