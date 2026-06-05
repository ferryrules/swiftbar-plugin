#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Git WIP</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>Repos with uncommitted or unpushed work</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import auto_hide_when_empty, is_compact
from dashboard import print_footer
from style import HEX_DIM, HEX_GREEN, HEX_MUTED, HEX_TEXT, HEX_WARN

PLUGIN_PATH = os.path.abspath(__file__)
SLUG = "git-wip"

REPOS_DIR = Path(os.environ.get("REPOS_DIR", str(Path.home() / "src" / "alembic")))


def run_git(repo, *args, timeout=5):
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except Exception:
        return None


def repo_status(repo):
    """Return dict with branch, dirty (file count), unpushed (commit count), or None."""
    head = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if not head or head.returncode != 0:
        return None
    branch = head.stdout.strip()

    porcelain = run_git(repo, "status", "--porcelain")
    dirty = len([l for l in porcelain.stdout.splitlines() if l]) if porcelain else 0

    ahead = run_git(repo, "rev-list", "--count", "@{u}..HEAD")
    unpushed = int(ahead.stdout.strip()) if ahead and ahead.returncode == 0 and ahead.stdout.strip().isdigit() else 0

    return {"name": repo.name, "path": repo, "branch": branch, "dirty": dirty, "unpushed": unpushed}


def scan():
    """Find all git repos directly under REPOS_DIR."""
    if not REPOS_DIR.exists():
        return []
    results = []
    for child in sorted(REPOS_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if not (child / ".git").exists():
            continue
        status = repo_status(child)
        if status:
            results.append(status)
    return results


def render(repos):
    wip = [r for r in repos if r["dirty"] or r["unpushed"]]

    if is_compact(SLUG):
        if wip:
            print(f"🔧 {len(wip)}")
        else:
            print("🔧 ✓")
    else:
        if wip:
            total_files = sum(r["dirty"] for r in wip)
            print(f"WIP: {len(wip)}/{len(repos)} ({total_files} files)")
        else:
            print(f"WIP: ✓ ({len(repos)} clean)")
    print("---")

    if not repos:
        print(f"No repos at {REPOS_DIR} | color={HEX_DIM}")
        print_footer()
        return

    print(f"{REPOS_DIR.name}/ | size=11 color={HEX_MUTED}")
    print("---")

    if wip:
        for r in wip:
            parts = []
            if r["dirty"]:
                parts.append(f"{r['dirty']} dirty")
            if r["unpushed"]:
                parts.append(f"{r['unpushed']} unpushed")
            color = HEX_WARN if r["dirty"] else HEX_TEXT
            label = f"🔧 {r['name']} · {r['branch']} · {' / '.join(parts)}"
            print(f"{label} | color={color}")
            print(f"--💻 Open in Cursor | bash='open' param1=-a param2=Cursor param3='{r['path']}' terminal=false refresh=false")
            print(f"--📂 Reveal in Finder | bash='open' param1='{r['path']}' terminal=false refresh=false")

        print("---")

    clean = [r for r in repos if not r["dirty"] and not r["unpushed"]]
    if clean:
        print(f"Clean ({len(clean)}) | size=11 color={HEX_MUTED}")
        for r in clean:
            print(f"--✓ {r['name']} · {r['branch']} | color={HEX_DIM}")

    print_footer()


def is_empty():
    """No repos have uncommitted or unpushed work."""
    return not any(r["dirty"] or r["unpushed"] for r in scan())


def main():
    if "--probe" in sys.argv:
        sys.exit(0 if is_empty() else 1)

    repos = scan()
    wip = [r for r in repos if r["dirty"] or r["unpushed"]]
    render(repos)
    auto_hide_when_empty(SLUG, not wip)


if __name__ == "__main__":
    main()
