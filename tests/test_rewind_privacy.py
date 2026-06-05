#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3
"""Guarantee: content-bearing sources never reach the synth LLM.

Rewind reads clipboard, Notes, Stickies, and Reminders for LOCAL display only.
Per Alembic policy, customer/sensitive data must not be sent to a non-local LLM
— and even with local Ollama, the same reducers run as defense-in-depth so the
boundary is identical whether you're online or air-gapped.

Feeds a timeline laced with secrets through build_llm_payload() and asserts
none of it survives into the synth payload.

Run: python3 tests/test_rewind_privacy.py   (exit 0 = pass, 1 = fail)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import rewind  # noqa: E402

# A timeline that includes every content-bearing kind, each carrying a secret.
TIMELINE = [
    {"ts": 1e9, "kind": "git", "title": "switched to ferrisboran/inf-1734", "repo": "causal_graph"},
    {"ts": 1e9, "kind": "pr", "title": "#1093: SV11 DevPod", "repo": "causal_graph"},
    {"ts": 1e9, "kind": "ticket", "title": "INF-1734: devpods"},
    {"ts": 1e9, "kind": "app", "title": "Cursor (12m)"},
    {"ts": 1e9, "kind": "web", "title": "ACME CORP CONFIDENTIAL — Salesforce", "domain": "salesforce.com"},
    {"ts": 1e9, "kind": "tab", "title": "ACME pricing model — Notion", "domain": "notion.so", "url": "https://acme.notion.so/secret"},
    {"ts": 1e9, "kind": "slack", "title": "posted in #sales-acme-renewal-private", "url": "slack://channel?id=C123"},
    {"ts": 1e9, "kind": "meeting", "title": "ACME Pricing Review with hunter2"},
    {"ts": 1e9, "kind": "ssh", "title": "ssh root@bastion.acme-prod.io", "host": "bastion.acme-prod.io"},
    {"ts": 1e9, "kind": "note", "title": "edited note: ACME pricing model", "claude_safe": False},
    {"ts": 1e9, "kind": "sticky", "title": "sticky: prod SSH key is hunter2", "claude_safe": False},
    {"ts": 1e9, "kind": "clipboard", "text": "sk-ant-secret-token-abc123", "claude_safe": False},
    {"ts": 1e9, "kind": "reminder", "title": "call ACME about renewal", "claude_safe": False},
]

FORBIDDEN_SUBSTRINGS = [
    "acme", "confidential", "hunter2", "sk-ant-secret", "pricing", "renewal", "ssh key",
    "bastion", "sales-acme", "acme-prod",
]
FORBIDDEN_KINDS = ["note", "sticky", "clipboard", "reminder"]


def main():
    payload = rewind.build_llm_payload(TIMELINE)
    blob = json.dumps(payload).lower()

    failures = []
    for bad in FORBIDDEN_SUBSTRINGS:
        if bad in blob:
            failures.append(f"sensitive substring leaked: {bad!r}")
    for kind in FORBIDDEN_KINDS:
        if f'"kind": "{kind}"' in blob:
            failures.append(f"content-bearing kind leaked: {kind!r}")
    if "salesforce.com" not in blob:
        failures.append("expected browser domain (salesforce.com) missing")
    if "notion.so" not in blob:
        failures.append("expected open-tab domain (notion.so) missing")
    if "ferrisboran/inf-1734" not in blob:
        failures.append("expected safe git metadata missing")
    for label, kind in (("slack message", "slack"),
                        ("calendar event", "meeting"),
                        ("ssh session", "ssh")):
        if f'"kind": "{kind}"' not in blob:
            failures.append(f"expected reduced kind {kind!r} missing")
        elif label not in blob:
            failures.append(f"expected reduced label {label!r} missing for kind {kind!r}")

    if failures:
        print("FAIL — Rewind privacy boundary broken:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nPayload was:")
        print(json.dumps(payload, indent=2))
        sys.exit(1)

    print("PASS — only structured work metadata reaches the synth LLM.")
    print(f"  {len(payload)} items sent; clipboard/notes/stickies/reminders excluded;")
    print("  browser/tabs reduced to domain; slack/meeting/ssh reduced to generic label.")
    sys.exit(0)


if __name__ == "__main__":
    main()
