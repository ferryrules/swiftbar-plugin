"""Cursor / VS Code editor activity.

Two sources, merged:
- `workspaceStorage/<hash>/workspace.json`  — workspace **open** events (mtime).
- `History/<hash>/entries.json`             — per-file **edit** events (timestamp ms).

The History feed is the high-resolution one; workspaceStorage gives us a
"switched to project X" event when you actually open a new repo. Both
flow into the timeline as `kind=editor` so the existing render path picks
them up unchanged.
"""

import json
import urllib.parse
from pathlib import Path

CURSOR_USER = Path.home() / "Library/Application Support/Cursor/User"
WORKSPACE_STORAGE = CURSOR_USER / "workspaceStorage"
HISTORY_STORAGE = CURSOR_USER / "History"


def _parse_workspace_uri(uri):
    """Cursor workspace URI → (label, repo, is_remote, path); `path` empty for vscode-remote://."""
    if uri.startswith("file://"):
        path = Path(urllib.parse.unquote(uri[len("file://"):]))
        return path.name, path.name, False, str(path)
    if uri.startswith("vscode-remote://"):
        rest = uri[len("vscode-remote://"):]
        authority, _, path = rest.partition("/")
        authority = urllib.parse.unquote(authority)
        host = authority.split("+", 1)[-1]
        is_devpod = host.endswith(".devpod")
        host_short = host[:-len(".devpod")] if is_devpod else host
        folder = Path(path).name or "workspace"
        suffix = " (devpod)" if is_devpod else " (remote)"
        if folder == host_short or folder in ("content", "workspace"):
            label = f"{host_short}{suffix}"
        else:
            label = f"{folder} · {host_short}{suffix}"
        return label, host_short, True, ""
    return "", "", False, ""


def _fetch_workspace_opens(since_ts):
    if not WORKSPACE_STORAGE.exists():
        return []
    raw = []
    for hash_dir in WORKSPACE_STORAGE.iterdir():
        ws_file = hash_dir / "workspace.json"
        if not ws_file.exists():
            continue
        try:
            mtime = ws_file.stat().st_mtime
            if mtime < since_ts:
                continue
            data = json.loads(ws_file.read_text())
        except Exception:
            continue
        uri = data.get("folder") or data.get("workspace") or ""
        label, repo, is_remote, path = _parse_workspace_uri(uri)
        if not label:
            continue
        raw.append((mtime, uri, label, repo, is_remote, path))

    by_uri = {}
    for mtime, uri, label, repo, is_remote, path in raw:
        prev = by_uri.get(uri)
        if not prev or prev[0] < mtime:
            by_uri[uri] = (mtime, label, repo, is_remote, path, uri)

    out = []
    for mtime, label, repo, is_remote, path, uri in by_uri.values():
        out.append({
            "ts": mtime, "kind": "editor",
            "icon": "🌐" if is_remote else "📝",
            "title": f"opened {label}" if is_remote else f"opened {label} in Cursor",
            "repo": repo, "url": "", "remote": is_remote,
            "path": path, "uri": uri,
        })
    return out


def _path_repo(path):
    """Best-effort repo name: walk up from `path` looking for a `.git` dir."""
    p = Path(path)
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists():
            return parent.name
        if parent == parent.parent:
            break
    parts = p.parts
    if len(parts) >= 2:
        return parts[-2]
    return ""


def _fetch_file_edits(since_ts):
    if not HISTORY_STORAGE.exists():
        return []
    out = []
    for hash_dir in HISTORY_STORAGE.iterdir():
        if not hash_dir.is_dir():
            continue
        try:
            if hash_dir.stat().st_mtime < since_ts:
                continue
        except OSError:
            continue
        entries_file = hash_dir / "entries.json"
        if not entries_file.exists():
            continue
        try:
            data = json.loads(entries_file.read_text())
        except Exception:
            continue
        resource = data.get("resource") or ""
        if not resource.startswith("file://"):
            continue
        path = urllib.parse.unquote(resource[len("file://"):])
        entries = data.get("entries") or []
        if not entries:
            continue
        latest_ms = max(int(e.get("timestamp") or 0) for e in entries)
        ts = latest_ms / 1000.0
        if ts < since_ts:
            continue
        repo = _path_repo(path)
        rel = Path(path).name
        title = f"{repo} · {rel}" if repo else rel
        out.append({
            "ts": ts, "kind": "editor", "icon": "💻",
            "title": title, "repo": repo, "url": "",
            "remote": False, "path": path, "uri": resource,
        })
    return out


def fetch_editor(since_ts):
    """Workspace-open events + per-file edit events from Cursor's History dir."""
    out = _fetch_workspace_opens(since_ts) + _fetch_file_edits(since_ts)
    return sorted(out, key=lambda x: -x["ts"])
