"""Linear: my recently-touched assigned issues."""

import os
from datetime import datetime, timezone

from dashboard import gql

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")


def fetch_linear(since_ts):
    if not LINEAR_API_KEY:
        return []
    since_iso = datetime.fromtimestamp(since_ts, tz=timezone.utc).isoformat()
    query = """
    query($since: DateTimeOrDuration!) {
      viewer {
        assignedIssues(
          first: 20
          filter: { updatedAt: { gt: $since } }
          orderBy: updatedAt
        ) {
          nodes {
            identifier title url updatedAt
            state { name type }
            priority
            dueDate
          }
        }
      }
    }
    """
    result = gql("https://api.linear.app/graphql",
                 {"Authorization": LINEAR_API_KEY, "Accept": "application/json"},
                 query, {"since": since_iso})
    if not result or "data" not in result:
        return []
    out = []
    for n in result["data"]["viewer"]["assignedIssues"]["nodes"]:
        try:
            ts = datetime.fromisoformat(n["updatedAt"].replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = since_ts
        out.append({
            "ts": ts, "kind": "ticket", "icon": "📋",
            "title": f"{n['identifier']}: {n['title']}",
            "url": n["url"], "identifier": n["identifier"],
            "state": n["state"]["name"], "state_type": n["state"]["type"],
            "priority": n.get("priority") or 0, "due": n.get("dueDate"),
        })
    return out
