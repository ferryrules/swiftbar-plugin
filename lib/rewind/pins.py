"""Pinned-moment storage: snapshot the synth + timeline on the way out,
restore them on the way back. Lives entirely on disk under
.cache/rewind-pins/. See docs/HOTKEYS.md for global-hotkey wiring."""

import json
import re
import time

from paths import REWIND_PINS_DIR


def _safe_label(label):
    """Filesystem-safe slug for a label, capped at 40 chars."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", label or "").strip("-")
    return cleaned[:40] or "moment"


def save_pin(label, window_min, ignore_min, synth, timeline):
    """Write a pin and return its filename (just the basename, not a path)."""
    REWIND_PINS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.time()
    fname = f"{int(ts)}-{_safe_label(label)}.json"
    payload = {
        "label": label or "(unlabeled)",
        "ts": ts,
        "window_min": window_min,
        "ignore_min": ignore_min,
        "synth": synth,
        "timeline": timeline[:25],
    }
    (REWIND_PINS_DIR / fname).write_text(json.dumps(payload))
    return fname


def list_pins():
    """All pins, newest first; each augmented with `_filename`."""
    if not REWIND_PINS_DIR.exists():
        return []
    out = []
    for p in sorted(REWIND_PINS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        data["_filename"] = p.name
        out.append(data)
    return out


def load_pin(filename):
    """Return the pin dict for `filename`, or None if missing/corrupt."""
    if not filename:
        return None
    p = REWIND_PINS_DIR / filename
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def delete_pin(filename):
    """Best-effort delete; silent on failure (file already gone is fine)."""
    if not filename:
        return
    try:
        (REWIND_PINS_DIR / filename).unlink()
    except OSError:
        pass
