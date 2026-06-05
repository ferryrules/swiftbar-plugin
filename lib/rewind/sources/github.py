"""GitHub: my recently-touched open PRs."""

import os
from datetime import datetime

from dashboard import gql

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_ORG = os.environ.get("GITHUB_ORG", "twothinkinc")


def fetch_github(since_ts):
    if not GITHUB_TOKEN:
        return []
    query = """
    {
      viewer {
        pullRequests(states: OPEN, first: 30, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            number title url updatedAt reviewDecision isDraft headRefName
            repository { name owner { login } }
          }
        }
      }
    }
    """
    result = gql("https://api.github.com/graphql",
                 {"Authorization": f"bearer {GITHUB_TOKEN}"}, query)
    if not result or "data" not in result:
        return []
    org_lower = GITHUB_ORG.lower()
    out = []
    for n in result["data"]["viewer"]["pullRequests"]["nodes"]:
        if (n.get("repository") or {}).get("owner", {}).get("login", "").lower() != org_lower:
            continue
        try:
            ts = datetime.fromisoformat(n["updatedAt"].replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if ts < since_ts:
            continue
        out.append({
            "ts": ts, "kind": "pr", "icon": "🔀",
            "title": f"#{n['number']}: {n['title']}",
            "url": n["url"], "repo": n["repository"]["name"],
            "review": n.get("reviewDecision"), "draft": n.get("isDraft"),
            "branch": n.get("headRefName", ""),
        })
    return out
