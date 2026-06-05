"""Sources package — each file owns one source.

Contract for new sources:
    fetch_<thing>(since_ts) -> list[dict] with at least {ts, kind, icon, title}
    or
    fetch_<thing>() -> dict (point-in-time snapshot, used for "now" anchors
    like the frontmost app or currently-open tabs).

Add a new source by dropping a file here and importing it from
lib/rewind/__init__.py:gather().
"""
