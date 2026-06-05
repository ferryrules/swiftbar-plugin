"""Git reflog across every repo in REPOS_DIR.

Surfaces branch switches, commits, pulls, rebases, and resets — the things
that come back as 'wait, where was I' when you swap repos mid-task.
"""

import os
import re
import subprocess
from pathlib import Path

REPOS_DIR = Path(os.environ.get("REPOS_DIR", str(Path.home() / "src" / "alembic")))


def _git(repo, *args, timeout=5):
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _classify_reflog(subject):
    """Turn a reflog subject into (kind, icon, human text). ('','','') means
    drop this entry."""
    m = re.match(r"checkout: moving from (\S+) to (\S+)", subject)
    if m:
        return "git", "🔀", f"switched to {m.group(2)}"
    if subject.startswith("commit:") or subject.startswith("commit (amend):"):
        return "git", "💾", "committed: " + subject.split(":", 1)[1].strip()
    if subject.startswith("commit (initial):"):
        return "git", "💾", "initial commit"
    if subject.startswith("pull") or subject.startswith("merge"):
        return "git", "⬇️", subject
    if subject.startswith("rebase"):
        return "git", "📐", subject
    if subject.startswith("reset:"):
        return "git", "↩️", subject
    return "", "", ""


def fetch_git(since_ts, max_per_repo=15):
    """Branch checkouts and commits from each repo's reflog since `since_ts`."""
    if not REPOS_DIR.exists():
        return []
    out = []
    for repo in sorted(REPOS_DIR.iterdir()):
        if not repo.is_dir() or not (repo / ".git").exists():
            continue
        listing = _git(repo, "reflog", "--date=unix",
                       "--format=%ct|%gs", "-n", "50")
        count = 0
        for line in listing.splitlines():
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            try:
                ts = float(parts[0])
            except ValueError:
                continue
            if ts < since_ts:
                continue
            kind, icon, text = _classify_reflog(parts[1].strip())
            if not text:
                continue
            out.append({
                "ts": ts, "kind": kind, "icon": icon,
                "title": text, "repo": repo.name, "url": "",
                "repo_path": str(repo),
            })
            count += 1
            if count >= max_per_repo:
                break
    return out
