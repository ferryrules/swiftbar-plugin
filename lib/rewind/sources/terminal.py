"""Terminal SSH/mosh history from ~/.zsh_history (extended-history, timestamped). Privacy: hostnames are name-y, so privacy.py swaps for 'ssh session' before sending to Claude; rendered locally because the point is to remind you which box you were on."""

import re
from pathlib import Path

ZSH_HISTORY = Path.home() / ".zsh_history"

ZSH_LINE = re.compile(r"^:\s+(\d+):\d+;(.+)$")
SSH_CMD = re.compile(r"^\s*(ssh|mosh)\b\s*(.*)$")
OPTS_WITH_VALUE = {"-i", "-p", "-l", "-F", "-o", "-J",
                   "-L", "-R", "-D", "-W", "-S", "-c", "-m"}


def _extract_host(args):
    """Pull `[user@]host` out of an ssh argument list, skipping option flags (and their values when they take one)."""
    tokens = args.split()
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("-"):
            if tok in OPTS_WITH_VALUE:
                skip_next = True
            continue
        return tok
    return tokens[0] if tokens else ""


def fetch_terminal(since_ts, max_items=20):
    """SSH/mosh commands run since `since_ts`, newest first, de-duped per host."""
    if not ZSH_HISTORY.exists():
        return []
    try:
        with ZSH_HISTORY.open(encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return []

    raw = []
    for line in lines:
        m = ZSH_LINE.match(line.rstrip("\n"))
        if not m:
            continue
        try:
            ts = float(m.group(1))
        except ValueError:
            continue
        if ts < since_ts:
            continue
        cmd = m.group(2)
        s = SSH_CMD.match(cmd)
        if not s:
            continue
        host = _extract_host(s.group(2))
        if not host or host.startswith("-"):
            continue
        raw.append((ts, s.group(1), host, cmd))

    raw.sort(key=lambda x: -x[0])

    seen, out = set(), []
    for ts, prog, host, cmd in raw:
        if host in seen:
            continue
        seen.add(host)
        out.append({
            "ts": ts, "kind": "ssh", "icon": "🛰️",
            "title": f"{prog} {host}",
            "host": host, "command": cmd, "url": "",
            "claude_safe": True,
        })
        if len(out) >= max_items:
            break
    return out
