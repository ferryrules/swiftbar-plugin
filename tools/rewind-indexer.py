#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3
"""Background indexer for Rewind.

Runs every 30s via launchd (see --install-launchd), or on demand via --once.
Keeps .cache/rewind-snapshot.json fresh so the plugin opens in <50ms.

Usage:
  tools/rewind-indexer.py --once          # one tick, then exit
  tools/rewind-indexer.py --watch         # loop forever, 30s cadence (for testing)
  tools/rewind-indexer.py --force         # one tick, ignore TTLs and re-fetch every source
  tools/rewind-indexer.py --install-launchd
  tools/rewind-indexer.py --uninstall-launchd
  tools/rewind-indexer.py --status        # print snapshot summary
  tools/rewind-indexer.py --demo morning  # write canned demo snapshot, pause real ticks
  tools/rewind-indexer.py --demo-off      # disable demo mode
  tools/rewind-indexer.py --demo-list     # list available scenarios
  tools/rewind-indexer.py --seed-demo-pins / --unseed-demo-pins
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from dashboard import load_env  # noqa: E402
from rewind import (  # noqa: E402
    demo,
    install_launchd,
    read_snapshot,
    snapshot_age_seconds,
    tick,
    uninstall_launchd,
)


def cmd_once(args):
    load_env()
    started = time.time()
    snap = tick(force=args.force, use_llm=not args.no_llm)
    elapsed = time.time() - started
    src = (snap.get("synth") or {}).get("_source", "?")
    print(
        f"tick ok in {elapsed*1000:.0f}ms · "
        f"window={snap['window_min']}m ignore={snap['ignore_min']}m · "
        f"{len(snap.get('timeline') or [])} events · synth={src}"
    )


def cmd_watch(args):
    load_env()
    interval = max(5, args.interval)
    print(f"watching: tick every {interval}s (ctrl-c to stop)")
    while True:
        cmd_once(args)
        time.sleep(interval)


def cmd_status(_args):
    snap = read_snapshot()
    if not snap:
        print("no snapshot — run --once first")
        sys.exit(1)
    age = snapshot_age_seconds(snap)
    print(json.dumps({
        "generated_iso": snap.get("generated_iso"),
        "age_seconds": round(age, 1) if age is not None else None,
        "window_min": snap.get("window_min"),
        "ignore_min": snap.get("ignore_min"),
        "timeline_count": len(snap.get("timeline") or []),
        "synth_source": (snap.get("synth") or {}).get("_source"),
        "synth": {k: v for k, v in (snap.get("synth") or {}).items() if k in ("where", "next", "forget")},
        "fda_needed": snap.get("fda_needed"),
    }, indent=2))


def cmd_install_launchd(_args):
    path, ok = install_launchd()
    print(f"installed: {path}  ({'loaded' if ok else 'load failed — see `launchctl list`'})")


def cmd_uninstall_launchd(_args):
    path = uninstall_launchd()
    print(f"uninstalled: {path}")


def cmd_demo(args):
    scenario = args.demo
    if scenario not in demo.SCENARIOS:
        print(f"unknown scenario {scenario!r}; available: {', '.join(sorted(demo.SCENARIOS))}")
        sys.exit(2)
    demo.enable(scenario)
    label = demo.SCENARIOS[scenario][0]
    print(f"demo mode ON · scenario: {scenario} — {label}")
    print("  indexer ticks are paused. `--demo-off` to resume live data.")


def cmd_demo_off(_args):
    was = demo.active_scenario()
    demo.disable()
    if was:
        print(f"demo mode OFF (was: {was}). Refreshing snapshot with live data…")
        snap = tick(force=False)
        print(f"  synth source: {(snap or {}).get('synth', {}).get('_source', '?')}")
    else:
        print("demo mode already off.")


def cmd_demo_list(_args):
    active = demo.active_scenario()
    for name, (label, _fn) in demo.SCENARIOS.items():
        mark = " ←active" if name == active else ""
        print(f"  {name:16s}  {label}{mark}")


def cmd_seed_demo_pins(_args):
    names = demo.seed_pins()
    print(f"seeded {len(names)} demo pin(s):")
    for n in names:
        print(f"  {n}")


def cmd_unseed_demo_pins(_args):
    n = demo.unseed_pins()
    print(f"removed {n} demo pin(s).")


def main():
    p = argparse.ArgumentParser(description="Rewind background indexer")
    p.add_argument("--once", action="store_true", help="run one tick and exit (default)")
    p.add_argument("--watch", action="store_true", help="loop forever")
    p.add_argument("--interval", type=int, default=30, help="seconds between ticks in --watch")
    p.add_argument("--force", action="store_true", help="ignore per-source TTLs")
    p.add_argument("--no-llm", action="store_true", help="skip Ollama, use template synth")
    p.add_argument("--status", action="store_true", help="print snapshot summary")
    p.add_argument("--install-launchd", action="store_true")
    p.add_argument("--uninstall-launchd", action="store_true")
    p.add_argument("--demo", metavar="SCENARIO",
                   help="enable demo mode with a canned scenario (try --demo-list)")
    p.add_argument("--demo-off", action="store_true", help="disable demo mode")
    p.add_argument("--demo-list", action="store_true", help="list available demo scenarios")
    p.add_argument("--seed-demo-pins", action="store_true",
                   help="seed three pre-fab pinned moments for the demo")
    p.add_argument("--unseed-demo-pins", action="store_true",
                   help="remove the seeded demo pins")
    args = p.parse_args()

    if args.install_launchd:
        cmd_install_launchd(args)
    elif args.uninstall_launchd:
        cmd_uninstall_launchd(args)
    elif args.demo_list:
        cmd_demo_list(args)
    elif args.demo:
        cmd_demo(args)
    elif args.demo_off:
        cmd_demo_off(args)
    elif args.seed_demo_pins:
        cmd_seed_demo_pins(args)
    elif args.unseed_demo_pins:
        cmd_unseed_demo_pins(args)
    elif args.status:
        cmd_status(args)
    elif args.watch:
        cmd_watch(args)
    else:
        cmd_once(args)


if __name__ == "__main__":
    main()
