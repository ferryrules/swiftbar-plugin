"""Privacy boundary for Rewind — single auditable place that decides what reaches the LLM.

Per Alembic data-classification, customer / sensitive data must not leave the box
(or, with local Ollama, must not leave the synth context window — same rule, same
reducers).
- LLM_UNSAFE_KINDS are dropped entirely (clipboard, notes, stickies, reminders).
- WEB_LIKE_KINDS reduce title to domain (page titles can name customers).
- GENERIC_LABELS reduce title to a kind label (channels, meeting titles, ssh hosts).
- Everything else passes through as structured work metadata.

Test: tests/test_rewind_privacy.py asserts the boundary holds.
"""

from datetime import datetime, timezone

LLM_UNSAFE_KINDS = {"clipboard", "note", "sticky", "reminder"}

WEB_LIKE_KINDS = {"web", "tab"}

# Title is informative locally but name-y enough to swap before sending to the LLM.
GENERIC_LABELS = {
    "slack": "slack message",
    "meeting": "calendar event",
    "ssh": "ssh session",
}

CLAUDE_UNSAFE_KINDS = LLM_UNSAFE_KINDS  # legacy alias


def build_llm_payload(timeline):
    """Return [{min_ago, kind, what, repo?}] suitable to send to the synth LLM."""
    now_ts = datetime.now(timezone.utc).timestamp()
    payload_items = []
    for s in timeline[:30]:
        kind = s.get("kind")
        if kind in LLM_UNSAFE_KINDS or s.get("claude_safe") is False or s.get("llm_safe") is False:
            continue
        if kind in WEB_LIKE_KINDS:
            what = s.get("domain", "")
        elif kind in GENERIC_LABELS:
            what = GENERIC_LABELS[kind]
        else:
            what = s.get("title", "")
        item = {"min_ago": round((now_ts - s["ts"]) / 60), "kind": kind, "what": what}
        if s.get("repo"):
            item["repo"] = s["repo"]
        payload_items.append(item)
    return payload_items


build_claude_payload = build_llm_payload  # legacy alias
