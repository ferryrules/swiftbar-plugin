#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>GitHub PRs</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>My GitHub PRs and reviews requested of me</bitbar.desc>
# <swiftbar.refreshOnOpen>false</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from config import is_compact
from dashboard import (
    copy_to_clipboard,
    gql,
    load_env,
    notify,
    print_footer,
    sanitize,
    time_ago,
)
from style import (
    ANSI_CYAN,
    ANSI_GREEN,
    ANSI_PURPLE,
    ANSI_RESET,
    ANSI_YELLOW,
    CI_ICON,
    EMOJI_CLIPBOARD,
    EMOJI_CURSOR,
    EMOJI_REPO,
    EMOJI_REVIEW,
    EMOJI_WARN,
    HEX_BLUE,
    HEX_DIM,
    HEX_MUTED,
    HEX_WARN,
    PR_STATE_RANK,
    PR_STATE_STYLE,
)

SLUG = "github-prs"

PLUGIN_PATH = os.path.abspath(__file__)
REPOS_DIR = Path(os.environ.get("REPOS_DIR", str(Path.home() / "src" / "alembic")))

load_env()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")
GITHUB_ORG = os.environ.get("GITHUB_ORG", "twothinkinc")


def github_gql(query, variables=None):
    return gql(
        "https://api.github.com/graphql",
        {"Authorization": f"bearer {GITHUB_TOKEN}"},
        query,
        variables,
    )


def fetch_prs():
    """Fetch open PRs (via direct graph — no search-index lag), today's
    merges and review requests (search is fine for these), and a wider
    history of recent PRs (any state) used to exclude already-PR'd branches
    from the orphan-branch list."""
    today = datetime.now().strftime("%Y-%m-%d")
    query = """
    query($merged_q: String!, $reviews_q: String!) {
      viewer {
        pullRequests(states: [OPEN, MERGED, CLOSED], first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            number title url isDraft createdAt updatedAt
            reviewDecision additions deletions headRefName state
            repository { name owner { login } }
            statusCheckRollup { state }
          }
        }
      }
      merged: search(query: $merged_q, type: ISSUE, first: 20) {
        nodes {
          ... on PullRequest {
            number title url mergedAt
            repository { name }
          }
        }
      }
      reviews: search(query: $reviews_q, type: ISSUE, first: 50) {
        nodes {
          ... on PullRequest {
            number title url isDraft createdAt updatedAt
            headRefName
            repository { name }
            author { login }
            statusCheckRollup { state }
          }
        }
      }
    }
    """
    result = github_gql(query, {
        "merged_q": f"is:pr author:{GITHUB_USERNAME} is:merged merged:>={today} org:{GITHUB_ORG}",
        "reviews_q": f"is:pr review-requested:@me is:open draft:false archived:false org:{GITHUB_ORG}",
    })
    if not result or "data" not in result:
        return [], [], [], set()

    org_lower = GITHUB_ORG.lower()
    all_my_prs = [n for n in result["data"]["viewer"]["pullRequests"]["nodes"] if n]
    open_prs = [
        n for n in all_my_prs
        if n.get("state") == "OPEN"
        and (n.get("repository") or {}).get("owner", {}).get("login", "").lower() == org_lower
    ]
    # All branches that ever had a PR (open/merged/closed) by me — used to
    # exclude them from the orphan-branch list.
    all_pr_branches = {
        n.get("headRefName", "").lower()
        for n in all_my_prs
        if n.get("headRefName")
    }
    return (
        open_prs,
        [n for n in result["data"]["merged"]["nodes"] if n],
        [n for n in result["data"]["reviews"]["nodes"] if n],
        all_pr_branches,
    )


def ci_icon(pr):
    r = pr.get("statusCheckRollup")
    if not r:
        return ""
    return CI_ICON.get(r.get("state", ""), "")


def _git(repo_dir, *args, timeout=5):
    """Run a git command, returning stdout or '' on error."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _git_user_email():
    """User's git email from global config (used to identify their branches)."""
    return _git(Path.cwd(), "config", "--global", "user.email").strip().lower()


def _origin_owner(repo_dir):
    """Parse the GitHub org/user from this repo's origin URL."""
    url = _git(repo_dir, "remote", "get-url", "origin", timeout=2).strip()
    m = re.search(r"github\.com[/:]([^/]+)/", url)
    return m.group(1).lower() if m else ""


ORPHAN_BRANCH_MAX_DAYS = int(os.environ.get("ORPHAN_BRANCH_MAX_DAYS", "14"))
ORPHAN_BRANCH_SKIP = {"main", "master", "develop", "trunk", "origin"}


def find_orphan_branches(known_pr_branches):
    """Find local remote-tracking branches authored by the user with no open PR.

    Scans REPOS_DIR for repos whose origin is in GITHUB_ORG. For each repo,
    lists `refs/remotes/origin/*` whose tip-commit author email matches the
    user's git email, skips the default branch and HEAD, excludes any branch
    name already attached to `known_pr_branches`, and filters by recency
    (default: last 14 days; override with ORPHAN_BRANCH_MAX_DAYS).
    """
    user_email = _git_user_email()
    if not user_email or not REPOS_DIR.exists():
        return []

    org_lower = GITHUB_ORG.lower()
    known = {b.lower() for b in known_pr_branches if b}
    cutoff = datetime.now(timezone.utc) - timedelta(days=ORPHAN_BRANCH_MAX_DAYS)
    orphans = []

    for repo_dir in sorted(REPOS_DIR.iterdir()):
        if not repo_dir.is_dir() or not (repo_dir / ".git").exists():
            continue
        if _origin_owner(repo_dir) != org_lower:
            continue

        # Default branch (so we can skip it)
        default_ref = _git(
            repo_dir, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", timeout=2,
        ).strip()
        default = default_ref.replace("origin/", "", 1) if default_ref else "main"

        listing = _git(
            repo_dir, "for-each-ref",
            "--format=%(refname:short)|%(committeremail)|%(committerdate:iso-strict)|%(subject)",
            "refs/remotes/origin/",
        )
        for line in listing.splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            ref, email, date, subject = parts
            branch = ref.replace("origin/", "", 1)
            email = email.strip().strip("<>").lower()

            if branch == default or branch.startswith("HEAD") or branch.lower() in ORPHAN_BRANCH_SKIP:
                continue
            if email != user_email:
                continue
            if branch.lower() in known:
                continue

            # Recency filter — skip branches older than the cutoff
            try:
                branch_dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                if branch_dt < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

            orphans.append({
                "repo": repo_dir.name,
                "branch": branch,
                "date": date,
                "subject": subject,
            })

    return orphans


def open_in_cursor(repo, branch):
    repo_path = REPOS_DIR / repo
    if not repo_path.exists():
        notify(f"Not cloned at {repo_path}", f"Repo {repo} not found")
        return

    co_ok = False
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "fetch", "origin", branch],
            capture_output=True, timeout=30, check=False,
        )
        co = subprocess.run(
            ["git", "-C", str(repo_path), "checkout", branch],
            capture_output=True, timeout=15, check=False,
        )
        co_ok = co.returncode == 0
    except Exception:
        co_ok = False

    subprocess.run(["open", "-a", "Cursor", str(repo_path)], check=False)
    notify(
        f"On {branch}" if co_ok else "Couldn't switch (uncommitted changes?)",
        f"Opened {repo} in Cursor",
    )


def classify(pr, is_merged=False):
    """Return (state_key, color, emoji)."""
    if is_merged:
        state = "merged"
    elif pr.get("reviewDecision") == "APPROVED":
        state = "ready"
    elif pr.get("isDraft"):
        state = "draft"
    else:
        state = "in_progress"
    color, emoji = PR_STATE_STYLE[state]
    return state, color, emoji


def render(open_prs, merged_prs, review_prs, known_pr_branches):
    approved = [p for p in open_prs if p.get("reviewDecision") == "APPROVED"]
    in_progress = [p for p in open_prs if p.get("reviewDecision") != "APPROVED"]

    # ---- Branches that are pushed but have no PR (open OR closed/merged) ----
    orphans = find_orphan_branches(known_pr_branches)

    # ---- Menubar title ----
    if is_compact(SLUG):
        if review_prs and len(review_prs) >= len(open_prs):
            print(f"{EMOJI_REVIEW} {len(review_prs)}")
        else:
            total = len(open_prs)
            if approved:
                _, emoji = PR_STATE_STYLE["ready"]
            elif in_progress:
                _, emoji = PR_STATE_STYLE["in_progress"]
            elif merged_prs:
                _, emoji = PR_STATE_STYLE["merged"]
                total = len(merged_prs)
            elif review_prs:
                emoji = EMOJI_REVIEW
                total = len(review_prs)
            else:
                emoji = "✓"
            print(f"{emoji} {total}" if total else f"{emoji}")
    else:
        segments = []
        if in_progress:
            segments.append(f"{ANSI_YELLOW}{len(in_progress)}{ANSI_RESET}")
        if approved:
            segments.append(f"{ANSI_GREEN}{len(approved)}{ANSI_RESET}")
        if merged_prs:
            segments.append(f"{ANSI_PURPLE}{len(merged_prs)}{ANSI_RESET}")
        mine_part = f"Git: {'; '.join(segments)}" if segments else "Git: ✓"
        review_part = f" · {ANSI_CYAN}{EMOJI_REVIEW} {len(review_prs)}{ANSI_RESET}" if review_prs else ""
        orphan_part = f" · 🌿 {len(orphans)}" if orphans else ""
        print(f"{mine_part}{review_part}{orphan_part} | ansi=true")
    print("---")

    render_my_prs(open_prs, merged_prs)

    if review_prs:
        print("---")
        render_review_requests(review_prs)

    if orphans:
        print("---")
        render_orphan_branches(orphans)

    print_footer()


def render_orphan_branches(orphans):
    print(f"🌿 Pushed but no PR ({len(orphans)}) | size=11 color={HEX_MUTED}")

    by_repo = defaultdict(list)
    for b in orphans:
        by_repo[b["repo"]].append(b)
    for repo in by_repo:
        by_repo[repo].sort(key=lambda x: x.get("date", ""), reverse=True)

    first = True
    for repo in sorted(by_repo.keys()):
        if not first:
            print("---")
        first = False
        branches = by_repo[repo]
        branches_url = f"https://github.com/{GITHUB_ORG}/{repo}/branches"
        print(f"{EMOJI_REPO} {repo} ({len(branches)}) | size=13 color={HEX_MUTED} href={branches_url}")
        for b in branches:
            branch = b["branch"]
            safe_branch = branch.replace("'", "")
            safe_repo = repo.replace("'", "")
            subject = sanitize(b.get("subject", ""), 70)
            age = time_ago(b.get("date", ""))
            branch_url = f"https://github.com/{GITHUB_ORG}/{repo}/tree/{branch}"
            new_pr_url = f"https://github.com/{GITHUB_ORG}/{repo}/pull/new/{branch}"

            print(f"🌿 {sanitize(branch, 60)} | href={branch_url} color={HEX_MUTED}")
            if subject or age:
                print(f"--{subject} · {age} | size=11 color={HEX_DIM}")
            print(f"--✨ Create PR on GitHub | href={new_pr_url}")
            print(f"--{EMOJI_CLIPBOARD} Copy branch: {safe_branch} | bash='{PLUGIN_PATH}' param1=copy param2='{safe_branch}' terminal=false refresh=false")
            print(f"--{EMOJI_CURSOR} Open in Cursor | bash='{PLUGIN_PATH}' param1=cursor param2='{safe_repo}' param3='{safe_branch}' terminal=false refresh=false")


def render_my_prs(open_prs, merged_prs):
    print(f"My PRs ({len(open_prs) + len(merged_prs)}) | size=11 color={HEX_MUTED}")

    all_prs = []
    for pr in open_prs:
        state, color, emoji = classify(pr, is_merged=False)
        pr["_state"], pr["_color"], pr["_emoji"] = state, color, emoji
        all_prs.append(pr)
    for pr in merged_prs:
        state, color, emoji = classify(pr, is_merged=True)
        pr["_state"], pr["_color"], pr["_emoji"] = state, color, emoji
        all_prs.append(pr)

    by_repo = defaultdict(list)
    for pr in all_prs:
        by_repo[pr["repository"]["name"]].append(pr)

    # Within each repo, sort: ready, in_progress, draft, merged; then newer first
    for repo in by_repo:
        by_repo[repo].sort(key=lambda p: (PR_STATE_RANK.get(p["_state"], 99), -p["number"]))

    if not all_prs:
        print(f"--No PRs today | color={HEX_DIM}")
        return

    first = True
    for repo in sorted(by_repo.keys()):
        if not first:
            print("---")
        first = False
        prs = by_repo[repo]
        repo_url = f"https://github.com/{GITHUB_ORG}/{repo}/pulls"
        print(f"{EMOJI_REPO} {repo} ({len(prs)}) | size=13 color={HEX_MUTED} href={repo_url}")
        for pr in prs:
            title = sanitize(pr["title"])
            safe_branch = (pr.get("headRefName") or "").replace("'", "")
            safe_repo = repo.replace("'", "")
            age = time_ago(pr.get("mergedAt") if pr["_state"] == "merged" else pr.get("createdAt"))
            ci = ci_icon(pr) if pr["_state"] != "merged" else ""

            print(f"{pr['_emoji']} #{pr['number']}: {title} | href={pr['url']} color={pr['_color']}")
            meta_label = {
                "ready": f"Approved · {age}{ci}",
                "in_progress": f"In review · {age}{ci}",
                "draft": f"Draft · {age}{ci}",
                "merged": f"Merged {age}",
            }.get(pr["_state"], age)
            print(f"--{meta_label} | size=11 color={HEX_MUTED}")
            if pr["_state"] != "merged":
                print(f"--+{pr.get('additions', 0)} −{pr.get('deletions', 0)} | size=11 color={HEX_DIM}")
            if safe_branch:
                print(f"--{EMOJI_CLIPBOARD} Copy branch: {safe_branch} | bash='{PLUGIN_PATH}' param1=copy param2='{safe_branch}' terminal=false refresh=false")
                print(f"--{EMOJI_CURSOR} Open in Cursor | bash='{PLUGIN_PATH}' param1=cursor param2='{safe_repo}' param3='{safe_branch}' terminal=false refresh=false")


def render_review_requests(review_prs):
    print(f"{EMOJI_REVIEW} Awaiting your review ({len(review_prs)}) | size=11 color={HEX_BLUE}")

    by_repo = defaultdict(list)
    for pr in review_prs:
        by_repo[pr["repository"]["name"]].append(pr)
    for repo in by_repo:
        by_repo[repo].sort(key=lambda p: -p["number"])

    first = True
    for repo in sorted(by_repo.keys()):
        if not first:
            print("---")
        first = False
        prs = by_repo[repo]
        repo_url = f"https://github.com/{GITHUB_ORG}/{repo}/pulls"
        print(f"{EMOJI_REPO} {repo} ({len(prs)}) | size=13 color={HEX_MUTED} href={repo_url}")
        for pr in prs:
            title = sanitize(pr["title"])
            author = (pr.get("author") or {}).get("login", "?")
            safe_branch = (pr.get("headRefName") or "").replace("'", "")
            safe_repo = repo.replace("'", "")
            age = time_ago(pr.get("createdAt"))
            ci = ci_icon(pr)

            print(f"{EMOJI_REVIEW} #{pr['number']}: {title} | href={pr['url']} color={HEX_BLUE}")
            print(f"--by @{author} · {age}{ci} | size=11 color={HEX_MUTED}")
            if safe_branch:
                print(f"--{EMOJI_CLIPBOARD} Copy branch: {safe_branch} | bash='{PLUGIN_PATH}' param1=copy param2='{safe_branch}' terminal=false refresh=false")
                print(f"--{EMOJI_CURSOR} Open in Cursor | bash='{PLUGIN_PATH}' param1=cursor param2='{safe_repo}' param3='{safe_branch}' terminal=false refresh=false")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "copy":
            copy_to_clipboard(sys.argv[2] if len(sys.argv) > 2 else "")
            return
        if cmd == "cursor":
            repo = sys.argv[2] if len(sys.argv) > 2 else ""
            branch = sys.argv[3] if len(sys.argv) > 3 else ""
            open_in_cursor(repo, branch)
            return

    if not GITHUB_TOKEN or not GITHUB_USERNAME:
        print(f"Git: {EMOJI_WARN} | color={HEX_WARN}")
        print("---")
        print(f"Set GITHUB_TOKEN and GITHUB_USERNAME | color={HEX_WARN}")
        print(f"in config/.env | size=11 color={HEX_MUTED}")
        return

    open_prs, merged_prs, review_prs, known_pr_branches = fetch_prs()
    render(open_prs, merged_prs, review_prs, known_pr_branches)


if __name__ == "__main__":
    main()
