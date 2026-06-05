"""Shared helpers for Rewind sources — sqlite copy with WAL/SHM, osascript, ticket regex."""

import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TICKET_RE = re.compile(r"\b([A-Z]{2,5}-\d+)\b")

MAC_EPOCH_OFFSET = 978307200


def extract_tickets(text):
    return set(TICKET_RE.findall(text or ""))


def copy_sqlite(src):
    """Copy a (possibly WAL-mode, possibly locked) sqlite DB + sidecars to /tmp; caller must cleanup_sqlite()."""
    tmp = Path(tempfile.gettempdir()) / f"rewind-{src.name}"
    shutil.copy2(src, tmp)
    for sidecar in ("-wal", "-shm"):
        s = src.with_name(src.name + sidecar)
        if s.exists():
            try:
                shutil.copy2(s, tmp.with_name(tmp.name + sidecar))
            except OSError:
                pass
    return tmp


def cleanup_sqlite(tmp):
    if not tmp:
        return
    for p in (tmp, tmp.with_name(tmp.name + "-wal"), tmp.with_name(tmp.name + "-shm")):
        try:
            p.unlink()
        except OSError:
            pass


def open_readonly(tmp):
    con = sqlite3.connect(f"file:{tmp}?immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    return con


def safe_result(future):
    try:
        return future.result() or []
    except Exception:
        return []


def osascript(script, timeout=4):
    """Run an osascript and return stdout, or '' on any failure."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return proc.stdout if proc.returncode == 0 else ""
    except Exception:
        return ""


def osascript_full(script, timeout=4):
    """Run osascript and return (stdout, stderr, returncode) so callers can distinguish 'app not running' from 'permission denied' (errOSAPermissionDenied = -1743)."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return proc.stdout or "", proc.stderr or "", proc.returncode
    except Exception as e:
        return "", str(e), -1


def is_app_running(process_name):
    """True if a process named `process_name` is running (uses pgrep, no automation permission required)."""
    try:
        proc = subprocess.run(
            ["pgrep", "-x", process_name],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return False
