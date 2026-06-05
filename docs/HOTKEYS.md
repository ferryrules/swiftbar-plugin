# Global hotkeys for Rewind

SwiftBar's `<swiftbar.shortcut>` directive only fires while SwiftBar is the
focused app — it isn't a system-wide hotkey. macOS doesn't let arbitrary
scripts register a global hotkey directly, but it ships **Shortcuts.app**
out of the box, which can run a shell script in response to one. That's
the path below.

You'll bind two hotkeys, both calling scripts in this repo's `bin/`:

| Action            | Script                  | Suggested hotkey |
| ----------------- | ----------------------- | ---------------- |
| Pin this moment   | `bin/rewind-pin.sh`     | ⌘⇧P              |
| Speak the 3 lines | `bin/rewind-speak.sh`   | ⌘⇧R              |

Both scripts work fine when run by hand — bind them once and they're
global for the rest of forever.

---

## Setup with Shortcuts.app (default macOS, no install)

Repeat for each script.

1. Open **Shortcuts.app** (in `/Applications/`).
2. Click **+** to create a new shortcut.
3. Name it something findable: `Rewind: Pin Moment` / `Rewind: Speak`.
4. From the Actions sidebar, drag in **Run Shell Script**.
5. Set:
   - **Shell**: `/bin/bash`
   - **Pass input**: `as arguments`
   - **Script**: the absolute path to the script. For this repo:
     - `/Users/ferris.boran/src/alembic/swiftbar-dashboard/bin/rewind-pin.sh`
     - `/Users/ferris.boran/src/alembic/swiftbar-dashboard/bin/rewind-speak.sh`
6. In the Shortcut's **Details** pane (top-right `i`), check **Use as Quick
   Action** and **Pin in menu bar** if you want a menubar fallback.
7. Open **System Settings → Keyboard → Keyboard Shortcuts → Services →
   General**, find your new shortcut, and click the keystroke field to
   record `⌘⇧P` (or `⌘⇧R`). Apply.

The first time the hotkey fires, macOS will ask permission for
Shortcuts to run the script and (for Pin) to control System Events for
the dialog box. Click **Allow** once.

> **Conflict tip.** `⌘⇧P` is a common Cursor / VSCode command-palette
> binding. Either rebind to `⌥⇧P` here, or limit the Shortcut to apps
> where you don't need the palette.

---

## Setup with skhd (if you already use it)

Add to `~/.config/skhd/skhdrc`:

```
cmd + shift - p : /Users/ferris.boran/src/alembic/swiftbar-dashboard/bin/rewind-pin.sh
cmd + shift - r : /Users/ferris.boran/src/alembic/swiftbar-dashboard/bin/rewind-speak.sh
```

Then `brew services restart skhd`.

---

## What the scripts do

### `rewind-pin.sh [label]`

- If no label is passed, pops a System Events dialog asking for one.
- Calls `python3 plugins/rewind.1h.py pin "$LABEL"`, which captures the
  current `gather()` output as a snapshot under `.cache/rewind-pins/`.
- Refreshes the SwiftBar plugin so the new pin shows up immediately.
- Fires a notification so you have visible confirmation outside the menubar.

### `rewind-speak.sh`

- Refreshes the SwiftBar plugin.
- Calls `python3 plugins/rewind.1h.py speak`, which runs the synth
  (template + Claude if configured) and prints the three lines.
- Pipes them into macOS `say` so you hear "Where you were ... Next ...
  Don't forget ..." without opening the menubar.
- Also fires a notification with the same text.

Both scripts are safe to run from any directory and require nothing
beyond `python3` and the existing `config/.env`.
