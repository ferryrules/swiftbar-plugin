# ferris-swiftbar

A SwiftBar dashboard for the Alembic workflow: GitHub PRs, Linear tickets,
Slack mentions, doc search, calendar, focus timer, git WIP, recent Cursor
projects, and Rewind. All state and config lives next to the plugins, so
the repo is self-contained and portable.

## Install

```bash
./install.sh
```

The installer:
- ensures SwiftBar is present (installs via Homebrew if needed),
- copies `.env.example` → `config/.env` (chmod 600) and opens it for you,
- points SwiftBar at `plugins/`,
- offers to install the Rewind launchd indexer.

Fill in `config/.env` and SwiftBar will pick up the plugins automatically.

## Sharing without GitHub

Coworkers without access to the GitHub repo can install from a tarball.

Build one:

```bash
./bin/package.sh                    # writes to ~/Desktop
./bin/package.sh /tmp               # or pick a directory
```

The script excludes `.git/`, `.cache/`, `__pycache__/`, `config/.env`, and
`config/auto-hidden.json`, and refuses to run if `.env.example` looks like
it contains real secrets.

Send the resulting `.tgz` over Slack, Drive, AirDrop, or any internal share.
Recipient:

```bash
tar -xzf ferris-swiftbar-*.tgz
cd ferris-swiftbar
./install.sh
```

## Layout

- `plugins/` — the SwiftBar plugins SwiftBar runs on its own schedule.
- `lib/` — shared helpers imported by plugins (`dashboard.py`, `paths.py`,
  `style.py`, `slack/`, `rewind/`, …). Plugins put the repo root on
  `sys.path` so these import as top-level modules.
- `tools/` — auxiliary scripts (e.g. the Rewind background indexer).
- `bin/` — shell helpers (`package.sh`, `rewind-pin.sh`, `rewind-speak.sh`).
- `config/` — runtime config (`.env`, `plugins.json`, `auto-hidden.json`).
  Only `plugins.json` is tracked; `.env` and `auto-hidden.json` are
  per-machine.
- `.cache/` — runtime state (slack auth cache, focus state, rewind
  snapshots). Never tracked.

## Docs

- [`docs/SLACK_SETUP.md`](docs/SLACK_SETUP.md) — Slack token + scopes.
- [`docs/HOTKEYS.md`](docs/HOTKEYS.md) — keyboard shortcuts.
