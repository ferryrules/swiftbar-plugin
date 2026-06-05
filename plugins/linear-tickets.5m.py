#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

# <bitbar.title>Linear Tickets</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.author>Ferris Boran</bitbar.author>
# <bitbar.desc>My Linear tickets grouped by state, colored by priority</bitbar.desc>
# <swiftbar.refreshOnOpen>false</swiftbar.refreshOnOpen>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>

import os
import re
import sys
from collections import defaultdict
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
)
from style import (
    ANSI_RESET,
    EMOJI_ATTACHMENT,
    EMOJI_BLOCKED,
    EMOJI_BLOCKS,
    EMOJI_CLIPBOARD,
    EMOJI_COMMENT,
    EMOJI_MILESTONE,
    EMOJI_MOVE,
    EMOJI_PARENT,
    EMOJI_PROJECT,
    EMOJI_RELATED,
    EMOJI_SUBISSUES,
    EMOJI_WARN,
    HEX_DIM,
    HEX_MUTED,
    HEX_TEXT,
    HEX_WARN,
    LINEAR_PRIORITY_ORDER,
    LINEAR_PRIORITY_STYLE,
    STATE_TYPE_RANK,
    state_icon,
)

PLUGIN_PATH = os.path.abspath(__file__)
SLUG = "linear-tickets"

ACTIVE_TYPES = {"started"}
QUEUED_TYPES = {"unstarted", "backlog", "triage"}
ALL_OPEN_TYPES = ACTIVE_TYPES | QUEUED_TYPES

load_env()
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")


def linear_gql(query, variables=None):
    return gql(
        "https://api.linear.app/graphql",
        {"Authorization": LINEAR_API_KEY, "Accept": "application/json"},
        query,
        variables,
    )


def fetch_tickets():
    query = """
    {
      viewer {
        assignedIssues(first: 50, orderBy: updatedAt) {
          nodes {
            id
            identifier
            title
            url
            branchName
            priority
            priorityLabel
            dueDate
            description
            state { id name type position }
            team {
              id
              key
              name
              states {
                nodes { id name type position }
              }
            }
            project { id name url }
            projectMilestone { id name }
            parent { identifier title url }
            children(first: 5) { nodes { id } }
            comments(first: 10) { nodes { id } }
            attachments(first: 5) { nodes { id } }
            relations(first: 5) {
              nodes {
                type
                relatedIssue { identifier title url }
              }
            }
            inverseRelations(first: 5) {
              nodes {
                type
                issue { identifier title url }
              }
            }
          }
        }
      }
    }
    """
    result = linear_gql(query)
    if not result or "data" not in result:
        return []
    return [
        t for t in result["data"]["viewer"]["assignedIssues"]["nodes"]
        if t["state"]["type"] in ALL_OPEN_TYPES
    ]


def description_lines(desc, max_lines=60, max_chars_per_line=140):
    """Return cleaned plain-text lines from a markdown description.

    Strips heading marks, links, bold/italic/code formatting, and images.
    Bullet points are normalized to "• ". Empty/separator lines are dropped.
    """
    if not desc:
        return []
    out = []
    for raw_line in desc.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("---") or line.startswith("==="):
            continue
        line = re.sub(r"^#+\s*", "", line)                       # heading marks
        line = re.sub(r"^[*\-+]\s+", "• ", line)                 # bullets
        line = re.sub(r"^\d+\.\s+", "", line)                    # numbered lists
        line = re.sub(r"^>\s*", "“ ", line)                      # blockquote
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)         # images
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)     # links → text
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)           # bold
        line = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", line)  # italic
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)                 # inline code
        line = line.strip()
        if not line or line == "```":
            continue
        if len(out) >= max_lines:
            out.append("… (open ticket for more)")
            break
        out.append(sanitize(line, max_chars_per_line))
    return out


def collect_relations(t):
    """Return (blocked_by, blocks, related) lists of {identifier, title, url}."""
    blocked_by, blocks, related = [], [], []
    seen_related = set()

    for rel in (t.get("inverseRelations") or {}).get("nodes", []) or []:
        other = rel.get("issue")
        if not other:
            continue
        rtype = rel.get("type")
        if rtype == "blocks":
            blocked_by.append(other)
        elif rtype == "related" and other["identifier"] not in seen_related:
            related.append(other)
            seen_related.add(other["identifier"])

    for rel in (t.get("relations") or {}).get("nodes", []) or []:
        other = rel.get("relatedIssue")
        if not other:
            continue
        rtype = rel.get("type")
        if rtype == "blocks":
            blocks.append(other)
        elif rtype == "related" and other["identifier"] not in seen_related:
            related.append(other)
            seen_related.add(other["identifier"])

    return blocked_by, blocks, related


def change_state(issue_id, state_id, label_hint=""):
    mutation = """
    mutation MoveIssue($id: String!, $stateId: String!) {
      issueUpdate(id: $id, input: { stateId: $stateId }) {
        success
        issue { identifier state { name } }
      }
    }
    """
    result = linear_gql(mutation, {"id": issue_id, "stateId": state_id})
    if result and result.get("data", {}).get("issueUpdate", {}).get("success"):
        issue = result["data"]["issueUpdate"]["issue"]
        notify(f"{issue['identifier']} → {issue['state']['name']}", "Moved")
    else:
        notify(f"Couldn't move to {label_hint or 'new state'}", "Linear error")


def render(tickets):
    by_priority = defaultdict(list)
    for t in tickets:
        by_priority[int(t.get("priority") or 0)].append(t)

    # ---- Menubar title ----
    if is_compact(SLUG):
        active_total = sum(1 for t in tickets if t["state"]["type"] in ACTIVE_TYPES)
        queued_total = sum(1 for t in tickets if t["state"]["type"] in QUEUED_TYPES)
        if active_total:
            print(f"🟢 {active_total}")
        elif queued_total:
            print(f"🟡 {queued_total}")
        else:
            print("Linear: ✓")
    else:
        segments = []
        for p in LINEAR_PRIORITY_ORDER:
            group = by_priority.get(p, [])
            if not group:
                continue
            active = sum(1 for t in group if t["state"]["type"] in ACTIVE_TYPES)
            queued = sum(1 for t in group if t["state"]["type"] in QUEUED_TYPES)
            _, ansi = LINEAR_PRIORITY_STYLE.get(p, (HEX_MUTED, ""))
            segments.append(f"{ansi}{active}/{queued}{ANSI_RESET}")

        if segments:
            print(f"Linear: {', '.join(segments)} | ansi=true")
        else:
            print("Linear: ✓")
    print("---")

    if not tickets:
        print(f"No assigned tickets | color={HEX_DIM}")
        print_footer()
        return

    # ---- Group by state name ----
    by_state = defaultdict(list)
    state_meta = {}  # state_name -> dict with type, position
    for t in tickets:
        name = t["state"]["name"]
        by_state[name].append(t)
        if name not in state_meta:
            state_meta[name] = {
                "type": t["state"]["type"],
                "position": t["state"].get("position", 0),
            }

    # Sort state groups by type rank, then by position
    sorted_states = sorted(
        by_state.keys(),
        key=lambda n: (STATE_TYPE_RANK.get(state_meta[n]["type"], 99), state_meta[n]["position"]),
    )

    first_section = True
    for state_name in sorted_states:
        group = by_state[state_name]
        icon = state_icon(state_name, state_meta[state_name]["type"])

        if not first_section:
            print("---")
        first_section = False

        print(f"{icon} {state_name} ({len(group)}) | size=13 color={HEX_TEXT}")

        # Sort tickets within group by priority (then identifier desc)
        group.sort(key=lambda t: (LINEAR_PRIORITY_ORDER.index(int(t.get("priority") or 0)) if int(t.get("priority") or 0) in LINEAR_PRIORITY_ORDER else 99, t["identifier"]))

        for t in group:
            render_ticket(t)

    print_footer()


def render_ticket(t):
    title = sanitize(t["title"])
    team = t.get("team", {}).get("key", "")
    due = f" · due {t['dueDate']}" if t.get("dueDate") else ""
    priority = int(t.get("priority") or 0)
    color, _ = LINEAR_PRIORITY_STYLE.get(priority, (HEX_TEXT, ""))
    priority_label = t.get("priorityLabel", "")

    print(f"{t['identifier']}: {title} | href={t['url']} color={color}")
    print(f"--{priority_label} · {team}{due} | size=11 color={HEX_MUTED}")

    # ---- Project / milestone ----
    project = t.get("project")
    milestone = t.get("projectMilestone")
    if project or milestone:
        parts = []
        if project:
            parts.append(f"{EMOJI_PROJECT} {sanitize(project['name'], 40)}")
        if milestone:
            parts.append(f"{EMOJI_MILESTONE} {sanitize(milestone['name'], 30)}")
        proj_href = (project or {}).get("url", "")
        href_attr = f" href={proj_href}" if proj_href else ""
        print(f"--{' · '.join(parts)} | size=11 color={HEX_MUTED}{href_attr}")

    # ---- Relations: blocked-by (critical), blocks, related ----
    blocked_by, blocks, related = collect_relations(t)
    for b in blocked_by:
        bt = sanitize(b.get("title", ""), 50)
        print(f"--{EMOJI_BLOCKED} Blocked by {b['identifier']}: {bt} | size=11 color=#ff4444 href={b['url']}")
    for b in blocks:
        bt = sanitize(b.get("title", ""), 50)
        print(f"--{EMOJI_BLOCKS} Blocks {b['identifier']}: {bt} | size=11 color={HEX_MUTED} href={b['url']}")
    for r in related[:3]:
        rt = sanitize(r.get("title", ""), 50)
        print(f"--{EMOJI_RELATED} Related: {r['identifier']}: {rt} | size=11 color={HEX_MUTED} href={r['url']}")
    if len(related) > 3:
        print(f"--{EMOJI_RELATED} + {len(related) - 3} more related | size=11 color={HEX_DIM}")

    # ---- Hierarchy: parent + sub-issues ----
    parent = t.get("parent")
    if parent:
        pt = sanitize(parent.get("title", ""), 50)
        print(f"--{EMOJI_PARENT} Sub-issue of {parent['identifier']}: {pt} | size=11 color={HEX_MUTED} href={parent['url']}")
    children_nodes = (t.get("children") or {}).get("nodes", []) or []
    if children_nodes:
        n = len(children_nodes)
        label = f"{n}+ sub-issues" if n >= 5 else f"{n} sub-issue{'s' if n != 1 else ''}"
        print(f"--{EMOJI_SUBISSUES} {label} | size=11 color={HEX_MUTED}")

    # ---- Activity counts (display "N+" when at fetch cap) — click to open ticket ----
    comments_nodes = (t.get("comments") or {}).get("nodes", []) or []
    attachments_nodes = (t.get("attachments") or {}).get("nodes", []) or []
    activity = []
    if comments_nodes:
        n = len(comments_nodes)
        activity.append(f"{EMOJI_COMMENT} {n}+" if n >= 10 else f"{EMOJI_COMMENT} {n}")
    if attachments_nodes:
        n = len(attachments_nodes)
        activity.append(f"{EMOJI_ATTACHMENT} {n}+" if n >= 5 else f"{EMOJI_ATTACHMENT} {n}")
    if activity:
        print(f"--{' · '.join(activity)} | size=11 color={HEX_MUTED} href={t['url']}")

    if t.get("branchName"):
        safe_branch = t["branchName"].replace("'", "")
        print(f"--{EMOJI_CLIPBOARD} Copy branch: {safe_branch} | bash='{PLUGIN_PATH}' param1=copy param2='{safe_branch}' terminal=false refresh=false")

    # ---- Move to submenu ----
    print(f"--{EMOJI_MOVE} Move to…")
    team_states = (t.get("team") or {}).get("states", {}).get("nodes", []) or []
    current_state_id = t["state"]["id"]
    issue_id = t["id"]

    # Order workflow states by type rank then position
    team_states_sorted = sorted(
        team_states,
        key=lambda s: (STATE_TYPE_RANK.get(s["type"], 99), s.get("position", 0)),
    )

    for s in team_states_sorted:
        if s["id"] == current_state_id:
            continue
        s_icon = state_icon(s["name"], s["type"])
        safe_id = s["id"].replace("'", "")
        safe_issue = issue_id.replace("'", "")
        safe_name = s["name"].replace("'", "")
        print(f"----{s_icon} {s['name']} | bash='{PLUGIN_PATH}' param1=state param2='{safe_issue}' param3='{safe_id}' param4='{safe_name}' terminal=false refresh=true")

    # ---- Full description (bottom of carrot) — static text, no per-line hover ----
    desc_lines = description_lines(t.get("description") or "")
    if desc_lines:
        for line in desc_lines:
            print(f"--{line} | size=11 color={HEX_DIM}")
    else:
        print(f"--No description | size=11 color={HEX_DIM}")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "copy":
            copy_to_clipboard(sys.argv[2] if len(sys.argv) > 2 else "")
            return
        if cmd == "state":
            issue_id = sys.argv[2] if len(sys.argv) > 2 else ""
            state_id = sys.argv[3] if len(sys.argv) > 3 else ""
            label = sys.argv[4] if len(sys.argv) > 4 else ""
            change_state(issue_id, state_id, label)
            return

    if not LINEAR_API_KEY:
        print(f"Linear: {EMOJI_WARN} | color={HEX_WARN}")
        print("---")
        print(f"Set LINEAR_API_KEY | color={HEX_WARN}")
        print(f"in config/.env | size=11 color={HEX_MUTED}")
        return

    tickets = fetch_tickets()
    render(tickets)


if __name__ == "__main__":
    main()
