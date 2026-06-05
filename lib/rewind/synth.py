"""Synthesize the three re-entry lines: where you were, next action, forget.

synthesize_template(): deterministic, always works.
synthesize_llm(): local Ollama via privacy.build_llm_payload(); nothing leaves the box.
Each result carries a `_links` dict so the plugin can wire each line to
its underlying entity (open the PR, jump to the ticket, launch the app).
"""

import re

from . import ollama
from .core import extract_tickets
from .privacy import build_llm_payload

CURSOR_BUNDLE = "com.todesktop.230313mzl4w4u92"
NOTES_BUNDLE = "com.apple.Notes"
REMINDERS_URL = "x-apple-reminderkit://"


def _link_url(url):
    return {"href": url} if url else None


def _link_app(bundle, *extra_args):
    """Open an app by bundle id, with optional extra `open` args (a path)."""
    if not bundle:
        return None
    args = ["-b", bundle, *[a for a in extra_args if a]]
    return {"bash": "/usr/bin/open", "args": args}


def _link_app_name(name):
    return {"bash": "/usr/bin/open", "args": ["-a", name]} if name else None


def _link_for_frontmost(front):
    """Click target for 'in <App>': bundle id when we have it, else app name."""
    if not front:
        return None
    return _link_app(front.get("bundle")) or _link_app_name(front.get("app"))


def _link_for_editor(entry):
    """Open the local Cursor folder if we have a path; else fall back to the workspace URI or just Cursor."""
    if not entry:
        return None
    path = entry.get("path")
    if path:
        return _link_app(CURSOR_BUNDLE, path)
    uri = entry.get("uri")
    if uri:
        return {"href": uri}
    return _link_app(CURSOR_BUNDLE)


def _link_for_git(entry):
    """No web URL for a reflog entry — jump back into the repo in Cursor."""
    repo_path = (entry or {}).get("repo_path")
    if repo_path:
        return _link_app(CURSOR_BUNDLE, repo_path)
    return None


def synthesize_template(signals):
    """Deterministic 3-line synthesis. Always works."""
    git = signals.get("git") or []
    prs = signals.get("github") or []
    tickets = signals.get("linear") or []
    browser = signals.get("browser") or []
    open_tabs = signals.get("open_tabs") or []
    editor = signals.get("editor") or []
    apps = signals.get("apps") or []
    reminders = signals.get("reminders") or []
    frontmost = signals.get("frontmost") or {}
    anchor_app = signals.get("anchor_app") or {}
    slack = signals.get("slack") or []
    meetings = signals.get("meeting") or []
    ssh = signals.get("ssh") or []

    where, where_link = None, None
    if git:
        top = git[0]
        tix = extract_tickets(top["title"])
        tix_label = f" ({', '.join(sorted(tix))})" if tix else ""
        where = f"{top['repo']}: {top['title']}{tix_label}"
        where_link = _link_for_git(top)
    elif prs:
        where = f"{prs[0]['repo']} {prs[0]['title']}"
        where_link = _link_url(prs[0].get("url"))
    elif tickets:
        where = tickets[0]["title"]
        where_link = _link_url(tickets[0].get("url"))
    elif editor:
        where = editor[0]["title"]
        where_link = _link_for_editor(editor[0])
    elif ssh:
        where = ssh[0]["title"]
        where_link = None
    elif slack:
        where = slack[0]["title"]
        where_link = _link_url(slack[0].get("url"))
    elif meetings:
        where = f"meeting: {meetings[0]['title']}"
        where_link = _link_url(meetings[0].get("url"))
    elif anchor_app.get("app"):
        where = f"in {anchor_app['app']} — last app before that"
        where_link = _link_app(anchor_app.get("bundle")) or _link_app_name(anchor_app.get("app"))
    elif frontmost.get("app"):
        win = frontmost.get("window") or ""
        where = f"in {frontmost['app']}" + (f" — {win}" if win else "")
        where_link = _link_for_frontmost(frontmost)
    elif apps:
        where = f"in {apps[0].get('app') or apps[0]['title']}"
        where_link = _link_app(apps[0].get("bundle")) or _link_app_name(apps[0].get("app"))
    elif open_tabs:
        signal_tabs = [t for t in open_tabs if t.get("signal")]
        anchor_tab = signal_tabs[0] if signal_tabs else open_tabs[0]
        where = f"reading {anchor_tab['title']}"
        where_link = _link_url(anchor_tab.get("url"))
    elif browser:
        where = f"browsing {browser[0]['domain']}"
        where_link = _link_url(browser[0].get("url"))
    else:
        where = "No recent activity found in this window"

    next_action, next_link = None, None
    approved = [p for p in prs if p.get("review") == "APPROVED"]
    changes = [p for p in prs if p.get("review") == "CHANGES_REQUESTED"]
    in_prog = [t for t in tickets if t.get("state_type") == "started"]
    if approved:
        next_action = f"Merge {approved[0]['title']} — it's approved"
        next_link = _link_url(approved[0].get("url"))
    elif changes:
        next_action = f"Address review on {changes[0]['title']}"
        next_link = _link_url(changes[0].get("url"))
    elif in_prog:
        next_action = f"Continue {in_prog[0]['title']}"
        next_link = _link_url(in_prog[0].get("url"))
    elif git and git[0]["title"].startswith("switched to"):
        branch = git[0]["title"].replace("switched to ", "")
        next_action = f"Pick back up on branch {branch}"
        next_link = _link_for_git(git[0])
    elif prs:
        next_action = f"Check on {prs[0]['title']}"
        next_link = _link_url(prs[0].get("url"))
    elif tickets:
        next_action = f"Keep moving on {tickets[0]['title']}"
        next_link = _link_url(tickets[0].get("url"))
    elif editor:
        next_action = f"Resume {editor[0]['title']}"
        next_link = _link_for_editor(editor[0])
    elif anchor_app.get("app"):
        next_action = f"Pick back up in {anchor_app['app']}"
        next_link = _link_app(anchor_app.get("bundle")) or _link_app_name(anchor_app.get("app"))
    elif frontmost.get("app"):
        next_action = f"Resume in {frontmost['app']}"
        next_link = _link_for_frontmost(frontmost)
    else:
        next_action = "Pick your next ticket from the dashboard"

    if next_link and where_link and next_link == where_link:
        next_action, next_link = None, None

    forget, forget_link = None, None
    due_soon = [t for t in tickets if t.get("due")]
    if approved and len(approved) > 1:
        forget = f"You also have {approved[1]['title']} approved & unmerged"
        forget_link = _link_url(approved[1].get("url"))
    elif due_soon:
        forget = f"{due_soon[0]['identifier']} is due {due_soon[0]['due']}"
        forget_link = _link_url(due_soon[0].get("url"))
    elif reminders:
        forget = f"Reminder: {reminders[0]['title']}"
        forget_link = {"href": REMINDERS_URL}
    elif approved and in_prog:
        forget = f"{in_prog[-1]['identifier']} still in progress"
        forget_link = _link_url(in_prog[-1].get("url"))
    elif in_prog and len(in_prog) > 1:
        forget = f"{in_prog[-1]['identifier']} is still open: {in_prog[-1]['title'].split(': ',1)[-1]}"
        forget_link = _link_url(in_prog[-1].get("url"))
    elif changes and tickets:
        forget = f"{tickets[-1]['identifier']} is waiting on you too"
        forget_link = _link_url(tickets[-1].get("url"))

    return {
        "where": where, "next": next_action, "forget": forget,
        "_links": {"where": where_link, "next": next_link, "forget": forget_link},
    }


def _resolve_link(text, signals):
    """Best-effort: turn an LLM-generated line into a clickable target by
    matching ticket IDs, PR numbers, or known app names against signals."""
    if not text:
        return None
    low = text.lower()

    for tix in (signals.get("linear") or []):
        ident = tix.get("identifier")
        if ident and ident.lower() in low:
            return _link_url(tix.get("url"))

    pr_match = re.search(r"#(\d+)", text)
    if pr_match:
        pr_num = pr_match.group(1)
        for pr in (signals.get("github") or []):
            if str(pr.get("title", "")).split(":", 1)[0].endswith(f"#{pr_num}"):
                return _link_url(pr.get("url"))

    front = signals.get("frontmost") or {}
    if front.get("app") and front["app"].lower() in low:
        link = _link_for_frontmost(front)
        if link:
            return link
    for app in (signals.get("apps") or []):
        name = app.get("app")
        if name and name.lower() in low:
            link = _link_app(app.get("bundle")) or _link_app_name(name)
            if link:
                return link

    for tab in (signals.get("open_tabs") or []):
        title = (tab.get("title") or "").lower()
        if title and len(title) > 8 and title in low:
            return _link_url(tab.get("url"))

    return None


_SYSTEM_PROMPT = (
    "You are a re-entry assistant for an engineer with ADHD who just got "
    "interrupted. Read the reverse-chronological activity log (most recent first) "
    "and return a JSON object with keys "
    '"recap", "where", "next", "forget", "tab_classes".\n'
    "- recap: 2 short sentences, natural prose, second-person ('You were…'). "
    "Summarize the work-in-progress story, not just a list. ~220 chars total.\n"
    "- where: where they were / what they were in the middle of (one short line)\n"
    "- next: the single most useful next action, imperative (one short line)\n"
    "- forget: the thing they are most likely to forget, or null (one short line)\n"
    "- tab_classes: object mapping each web/tab domain in the log to one of "
    '"active" (currently working on it), "reference" (looked at but tangential), '
    '"noise" (briefly opened, not really part of current work). '
    "Only include domains that appear in the log.\n"
    "Be concrete. Reference ticket IDs (PROJ-123) and PR numbers (#456) verbatim "
    "when present. No preamble, no explanation, JSON only."
)


def synthesize_llm(signals, timeline):
    """Local-Ollama synth via build_llm_payload (metadata only); None on any failure.

    See lib/rewind/ollama.py for the HTTP client and tests/test_rewind_privacy.py
    for the boundary guarantee.
    """
    payload_items = build_llm_payload(timeline)
    if not payload_items:
        return None

    parsed = ollama.chat_json(
        prompt=f"Activity log:\n{payload_items}",
        system=_SYSTEM_PROMPT,
        max_tokens=400,
    )
    if not parsed or "where" not in parsed:
        return None

    where = str(parsed.get("where") or "").strip() or None
    nxt = str(parsed.get("next") or "").strip() or None
    forget_raw = parsed.get("forget")
    forget = str(forget_raw).strip() if forget_raw else None
    recap_raw = parsed.get("recap")
    recap = str(recap_raw).strip() if recap_raw else None

    raw_classes = parsed.get("tab_classes") or {}
    tab_classes = {}
    if isinstance(raw_classes, dict):
        for domain, label in raw_classes.items():
            if isinstance(domain, str) and isinstance(label, str):
                lab = label.strip().lower()
                if lab in ("active", "reference", "noise"):
                    tab_classes[domain.strip().lower()] = lab

    return {
        "recap": recap,
        "where": where,
        "next": nxt,
        "forget": forget,
        "tab_classes": tab_classes,
        "_links": {
            "where": _resolve_link(where, signals),
            "next": _resolve_link(nxt, signals),
            "forget": _resolve_link(forget, signals),
        },
        "_source": "ollama",
        "_runtime": ollama.runtime_label(),
    }


synthesize_claude = synthesize_llm  # legacy alias


_LABEL_SYSTEM_PROMPT = (
    "You name pinned work moments. Read the activity log and return a JSON "
    "object {\"label\": \"<3-5 words>\"}. The label must be a noun phrase, "
    "Title Case, no trailing punctuation, ≤40 chars. Reference ticket IDs "
    "(PROJ-123) and PR numbers (#456) verbatim when present. No preamble."
)


def _template_label(synth):
    """Deterministic fallback used when Ollama is unreachable or refuses to label."""
    where = (synth or {}).get("where") or ""
    where = re.sub(r"^(in|on|at|reading|browsing)\s+", "", where, flags=re.I)
    where = where.split(" — ", 1)[0]
    where = where.split(": ", 1)[-1] if ":" in where else where
    return (where[:38] + "…") if len(where) > 40 else (where or "Pinned moment")


def suggest_label(timeline, synth=None):
    """3-5 word pin label from Ollama; falls back to a template snippet of `where`.

    Privacy boundary is the same as the main synth: only metadata reaches the LLM.
    """
    payload_items = build_llm_payload(timeline) if timeline else []
    if payload_items:
        parsed = ollama.chat_json(
            prompt=f"Activity log:\n{payload_items}",
            system=_LABEL_SYSTEM_PROMPT,
            timeout=8,
            max_tokens=60,
        )
        label = (parsed or {}).get("label")
        if isinstance(label, str):
            label = label.strip().strip('"').strip("'")
            if label:
                return label[:60]
    return _template_label(synth)


_WRAPUP_SYSTEM_PROMPT = (
    "You are writing an end-of-day work journal entry for an engineer. Read "
    "the day's activity log (reverse chronological) and return a JSON object "
    'with keys "headline", "narrative", "wins", "loose_ends".\n'
    "- headline: one sentence (≤ 90 chars), past tense — 'Wrapped up X, shipped Y'\n"
    "- narrative: 2 short paragraphs of natural prose, second-person ('You "
    "spent the morning…'). Tell the story of the day.\n"
    "- wins: array of 3-5 strings, things that got finished/shipped/merged. "
    "Each ≤ 80 chars.\n"
    "- loose_ends: array of 0-4 strings, things still in flight or needing "
    "follow-up. Each ≤ 80 chars.\n"
    "Reference ticket IDs (PROJ-123) and PR numbers (#456) verbatim. "
    "Concrete > vague. JSON only."
)


def synthesize_wrapup(timeline):
    """End-of-day narrative + structured highlights via Ollama; None on failure.

    Privacy boundary identical to the main synth: only metadata reaches the LLM.
    """
    payload_items = build_llm_payload(timeline) if timeline else []
    if not payload_items:
        return None
    parsed = ollama.chat_json(
        prompt=f"Activity log (full day):\n{payload_items}",
        system=_WRAPUP_SYSTEM_PROMPT,
        timeout=25,
        max_tokens=900,
    )
    if not parsed:
        return None
    headline = str(parsed.get("headline") or "").strip() or None
    narrative = str(parsed.get("narrative") or "").strip() or None
    wins = [str(w).strip() for w in (parsed.get("wins") or []) if str(w).strip()]
    loose = [str(l).strip() for l in (parsed.get("loose_ends") or []) if str(l).strip()]
    return {
        "headline": headline,
        "narrative": narrative,
        "wins": wins,
        "loose_ends": loose,
    }


def synthesize(signals, timeline, use_llm=True, **_legacy):
    """Try Ollama (local LLM) first, fall back to template."""
    if use_llm:
        result = synthesize_llm(signals, timeline)
        if result:
            return result
    out = synthesize_template(signals)
    out["_source"] = "template"
    return out
