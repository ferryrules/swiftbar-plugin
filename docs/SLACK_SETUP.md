# Slack plugin setup

The `slack.5m.py` plugin reads your unread DMs and recent @mentions through
the Slack Web API. To do that as you (not as a bot), you need a **User OAuth
Token**. This is a one-time setup.

## 1. Create a Slack app

1. Visit <https://api.slack.com/apps> and click **Create New App** → **From scratch**.
2. Name it something like *Personal Dashboard* and pick the Alembic workspace.
3. Click **Create App**.

## 2. Add User Token Scopes

In the new app's sidebar: **OAuth & Permissions** → scroll to **Scopes** →
**User Token Scopes**. Add all of these:

| Scope | Why |
| --- | --- |
| `channels:history`  | read messages in public channels (for mentions) |
| `groups:history`    | read messages in private channels |
| `im:history`        | read 1:1 DMs |
| `mpim:history`      | read group DMs |
| `channels:read`     | list public channels |
| `groups:read`       | list private channels |
| `im:read`           | list DMs |
| `mpim:read`         | list group DMs |
| `search:read`       | search for `@you` mentions |
| `users:read`        | resolve `U12345` IDs to display names |

> **Note:** Use the **User Token Scopes** column, *not* Bot Token Scopes.
> A user token impersonates you (which is what you want); a bot token can only
> see channels the bot is added to.

## 3. Install to workspace

Still in **OAuth & Permissions**, click **Install to Workspace** at the top.

- If your workspace allows self-install, you'll be prompted to approve.
- If it requires admin approval, you'll see a "request to install" button —
  hit it and ping a workspace admin.

After approval, copy the **User OAuth Token** (starts with `xoxp-`).

## 4. Save the token

Add it to `<repo>/config/.env`:

```
SLACK_USER_TOKEN=xoxp-your-token-here
```

The file is `chmod 600` (created by `install.sh`) and gitignored, so the
token never leaves your machine.

## 5. Verify

Refresh the menubar (open the Control Center → ↻ Refresh all). The Slack
plugin should show one of:

- `💬 ✓` — you're caught up
- `💬 N` — N unread DMs/mentions
- `💬 ⚙` — token missing (re-check step 4)
- `💬 ⚠️` — auth failed (re-check scopes in step 2)

If it shows `⚠️`, the most likely cause is missing scopes. Add them in the
app settings, **reinstall** the app to your workspace (the scope change
requires reinstall), and copy the new token.

## What the plugin reads

- **Unread DMs** (1:1 and group) — `search.messages` with `is:unread in:dm,mpim`,
  augmented with a `conversations.info` poll of the 10 most-recent DMs for
  real-time accuracy on brand-new messages.
- **@mentions in channels** — `search.messages` for `<@YOU>` within a configurable
  time window. DMs/group-DMs excluded (already in the DMs section).
- **Thread replies** — `search.messages` for `from:<@YOU> threaded:true`, then
  `conversations.replies` per matching thread to find replies posted after yours.
- **Keyword watchlist** — one `search.messages` per keyword, in parallel.
- **Bot messages** are filtered out by default.

No posting, no DM body access beyond the previewed last message, no channel
digests.

## Customizing what shows up

All Slack settings live in **one file**: `lib/slack_config.py`. Each setting
has an inline comment explaining what it does.

To change settings:

1. Click the menubar's 💬 icon → **Edit preferences** (opens the file in your
   default editor), OR just open `lib/slack_config.py` directly.
2. Edit any value in the `CONFIG` dict, save.
3. Refresh the plugin (click the menubar or wait 5 minutes).

## Removing access

Two ways to revoke the token:

1. **api.slack.com/apps** → your app → **Manage Distribution** or just delete
   the app.
2. **Slack workspace** → Settings → **Manage Apps** → find the app → revoke.

Then delete the line from `config/.env`.
