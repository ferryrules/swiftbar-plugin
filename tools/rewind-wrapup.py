#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3
"""End-of-day Rewind summary.

Re-runs the indexer's gather pipeline with a wide window (default: 6am →
now), asks Ollama for a narrative + structured highlights, compiles the
day's PRs / tickets / repos / files, writes the result to
~/Desktop/rewind-YYYY-MM-DD.md and opens it.

Triggered manually via the Rewind plugin's "📓 Wrap up today" button or
from the CLI:

    tools/rewind-wrapup.py                    # 6am → now
    tools/rewind-wrapup.py --start-hour 9     # 9am → now
    tools/rewind-wrapup.py --since-min 480    # last 8 hours
    tools/rewind-wrapup.py --no-open          # don't open the file when done
"""

import argparse
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from dashboard import load_env  # noqa: E402

load_env()

import rewind  # noqa: E402
from rewind import build_timeline, gather, synthesize_wrapup  # noqa: E402


def _minutes_since(start_hour):
    now = datetime.now()
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if start > now:
        start = start.replace(day=start.day - 1)
    return max(15, int((now - start).total_seconds() // 60))


def _gather_files(signals):
    """Files touched today (from `editor` signals)."""
    by_repo = defaultdict(list)
    for e in signals.get("editor") or []:
        repo = e.get("repo") or "(no repo)"
        path = e.get("path") or e.get("title") or ""
        if path:
            by_repo[repo].append(path)
    return {repo: sorted(set(files)) for repo, files in by_repo.items()}


def _gather_repos(signals):
    """{repo: commit-count} from git signals."""
    counter = Counter()
    for g in signals.get("git") or []:
        repo = g.get("repo")
        if repo:
            counter[repo] += 1
    return counter.most_common()


def _gather_prs(signals):
    """De-duped list of (repo, title, url, review_state)."""
    seen, out = set(), []
    for p in signals.get("github") or []:
        url = p.get("url")
        if url and url not in seen:
            seen.add(url)
            out.append(p)
    return out


def _gather_tickets(signals):
    """De-duped list of (identifier, title, url, state)."""
    seen, out = set(), []
    for t in signals.get("linear") or []:
        ident = t.get("identifier") or t.get("url")
        if ident and ident not in seen:
            seen.add(ident)
            out.append(t)
    return out


def _markdown(date_str, headline, signals, wrapup):
    """Build the wrap-up markdown. Falls back to structured-only if Ollama returned None."""
    lines = [f"# Rewind · {date_str}", ""]

    if headline:
        lines += [f"_{headline}_", ""]

    if wrapup and wrapup.get("narrative"):
        lines += ["## What happened", "", wrapup["narrative"], ""]

    if wrapup and wrapup.get("wins"):
        lines += ["## Wins", ""]
        lines += [f"- {w}" for w in wrapup["wins"]]
        lines += [""]
    if wrapup and wrapup.get("loose_ends"):
        lines += ["## Loose ends", ""]
        lines += [f"- {l}" for l in wrapup["loose_ends"]]
        lines += [""]

    repos = _gather_repos(signals)
    if repos:
        lines += ["## Repos touched", ""]
        for repo, n in repos:
            unit = "commit" if n == 1 else "commits"
            lines.append(f"- **{repo}** — {n} {unit}")
        lines += [""]

    prs = _gather_prs(signals)
    if prs:
        lines += ["## Pull requests", ""]
        for p in prs:
            review = f" · {p['review']}" if p.get("review") else ""
            url = p.get("url") or ""
            title = (p.get("title") or "").strip() or url
            lines.append(f"- [{title}]({url}){review}")
        lines += [""]

    tickets = _gather_tickets(signals)
    if tickets:
        lines += ["## Tickets", ""]
        for t in tickets:
            ident = t.get("identifier") or ""
            state = f" · {t['state']}" if t.get("state") else ""
            url = t.get("url") or ""
            title = (t.get("title") or "").strip() or url
            lines.append(f"- {ident}: [{title}]({url}){state}")
        lines += [""]

    files = _gather_files(signals)
    if files:
        lines += ["## Files edited", ""]
        for repo, paths in sorted(files.items()):
            lines.append(f"- **{repo}**")
            for p in paths[:10]:
                short = "/".join(p.split("/")[-3:])
                lines.append(f"  - `{short}`")
            if len(paths) > 10:
                lines.append(f"  - …+{len(paths) - 10} more")
        lines += [""]

    has_structured = bool(repos or prs or tickets or files)
    has_narrative = bool(wrapup and (wrapup.get("narrative") or wrapup.get("wins") or wrapup.get("loose_ends")))
    if not has_structured and not has_narrative:
        lines += [
            "_(No work signals captured for this window — check that GitHub / "
            "Linear / Slack tokens are set in `config/.env`.)_",
            "",
        ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Write today's Rewind wrap-up.")
    parser.add_argument("--start-hour", type=int, default=6,
                        help="Hour of day to count from (default: 6 = 6am)")
    parser.add_argument("--since-min", type=int, default=None,
                        help="Override: window in minutes (takes precedence over --start-hour)")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't `open` the file when done.")
    parser.add_argument("--out", default=None,
                        help="Output path (default: ~/Desktop/rewind-YYYY-MM-DD.md).")
    args = parser.parse_args()

    window_min = args.since_min or _minutes_since(args.start_hour)

    signals = gather(window_min=window_min, ignore_min=0)
    timeline = build_timeline(signals)

    wrapup = synthesize_wrapup(timeline)
    headline = (wrapup or {}).get("headline")
    if not headline:
        repos = _gather_repos(signals)
        prs = _gather_prs(signals)
        merged = sum(1 for p in prs if p.get("review") == "APPROVED")
        bits = []
        if repos:
            bits.append(f"{repos[0][0]} ({repos[0][1]} commits)")
        if merged:
            bits.append(f"{merged} PR{'s' if merged != 1 else ''} approved")
        headline = "Worked on " + ", ".join(bits) if bits else "Quiet day."

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else Path.home() / "Desktop" / f"rewind-{date_str}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_markdown(date_str, headline, signals, wrapup))

    print(f"Wrote {out_path}")
    if not args.no_open:
        subprocess.run(["/usr/bin/open", str(out_path)], check=False)


if __name__ == "__main__":
    main()
