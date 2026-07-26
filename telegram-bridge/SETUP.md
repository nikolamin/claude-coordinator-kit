# Telegram bridge — setup

A Telegram-based implementation of the coordinator kit's `<NOTIFY_CHANNEL>`: it lets the founder
message a live Claude Code coordinator session from their phone, and lets the coordinator ping the
founder back — with reactions, a typing indicator, and file delivery. This is a machine-level
service, not a per-project one: install it once, and any coordinator session on the machine
(this project or a future one) can use the same bot. See "Reusing this bridge across projects" at
the bottom.

Written for someone with no prior Telegram-bot experience — follow top to bottom.

**If a Claude coordinator session is installing this for you:** it can do steps (a)-(c) itself.
Run @BotFather's `/newbot` yourself, then paste the resulting token directly into the chat when
the agent asks for it — the agent writes it straight into the gitignored `.env` and never echoes,
logs, or commits it. Then send the new bot any message (e.g. "hi") when asked, and the agent
fetches your chat id and confirms it with you before writing `TELEGRAM_CHAT_ID`. The walkthrough
below is the fully-manual path, for a human running it themselves with no agent involved.

## Contents of this directory

| File | Purpose |
|---|---|
| `bot.py` | Runs one Telegram long-poll cycle, relays messages, exits. Relaunched forever by the OS service (below). |
| `notify.sh` | Send a one-off Telegram message from any shell/hook: `./notify.sh "message"`. |
| `react.sh` | Set the final 👍/👎 reaction on a relayed message: `./react.sh <message_id> ok\|fail`. |
| `telegram_common.py` | Shared helper module (message chunking) used by `bot.py` and `daily_report.py`. Required — `bot.py` imports it. |
| `get_chat_id.py` | Optional helper to print your chat id from recent bot updates (alternative to the curl one-liner in step (a)). |
| `daily_report.py` | Optional. One-shot daily git-activity digest sent to Telegram. |
| `.env.example` | Template for your `.env` — copy and fill in. |
| `.gitignore` | Keeps `.env`, logs, and runtime state files out of version control. |
| `com.example.claude-telegram-bridge.plist.template` | macOS launchd template for the always-on bot loop. |
| `com.example.claude-telegram-bridge-daily-report.plist.template` | macOS launchd template for the optional daily digest. |
| `claude-telegram-bridge.service.template` | Linux systemd template for the always-on bot loop. |
| `claude-telegram-bridge-daily-report.service.template` + `.timer.template` | Linux systemd templates for the optional daily digest. |

## Architecture at a glance

```
 Telegram app (phone)
         │  you send a message
         ▼
 Telegram Bot API  ──getUpdates (long-poll)──┐
                                              ▼
                                          bot.py
                              (ONE poll cycle, then exits)
                                              │
                  RELAY_MODE=1 (recommended)  │  RELAY_MODE unset (classic)
                  ┌───────────────────────────┴───────────────────────────┐
                  ▼                                                       ▼
        👀-react + append line to                              run `claude -p
        relay-inbox.jsonl, then exit                           [--continue] "<msg>"`
                  │                                             (headless, own process,
                  │                                              NO shared context)
                  ▼                                                       │
      Live coordinator session                                           ▼
      (Monitor tails relay-inbox.jsonl,                        reply sent directly +
       message arrives mid-session)                            final 👍/👎 reaction
                  │
                  ├─ notify.sh "<reply text>"      → Bot API sendMessage
                  ├─ react.sh <message_id> ok|fail  → Bot API setMessageReaction (👍/👎)
                  └─ curl sendDocument (file)        → Bot API, for file deliverables
```

Supervisor loop (launchd on macOS, systemd on Linux) relaunches `bot.py` immediately after every
exit — every poll cycle is a fresh process, so `.env`/code edits on disk take effect on the very
next cycle automatically, no service restart needed.

## (a) Create the bot and find your chat id

Manual, one-time, from your own Telegram account:

1. Open Telegram, start a chat with **@BotFather**.
2. Send `/newbot`, follow the prompts (name + username for your bot).
3. BotFather replies with a bot token, e.g. `123456789:AAExampleTokenExampleTokenExampleTok`.
   Copy it — you'll paste it into `.env` in step (c). (If a Claude agent is doing this install,
   paste it directly into the chat instead when it asks — it writes it to `.env` for you.)
4. Send your new bot a message from your phone (any text, e.g. "hi"), so Telegram has an update
   for it to see.
5. Find your chat id — any one of these three works:
   - **curl** (no setup): `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool` and read `result[0].message.chat.id`.
   - **get_chat_id.py**: after filling in `TELEGRAM_BOT_TOKEN` in `.env` (step c), run
     `python3 get_chat_id.py` — it prints candidate chat ids with the sender's name.
   - **@userinfobot**: message it on Telegram; it replies with your numeric user id, which is your
     chat id for a 1:1 bot conversation.
6. Copy the chat id that's you into `TELEGRAM_CHAT_ID` in `.env`.

## (b) Install the Python dependency

The only third-party dependency is `requests` (stdlib covers everything else, including `.env`
parsing):

```bash
pip install requests
```

Optionally, in a virtualenv (remember to point the launchd/systemd template's `python3` path at
`venv/bin/python3` if you do):

```bash
cd <BRIDGE_DIR>
python3 -m venv venv
source venv/bin/activate
pip install requests
```

## (c) Fill in `.env`

```bash
cp .env.example .env
```

Then set:

- `TELEGRAM_BOT_TOKEN` — from step (a).
- `TELEGRAM_CHAT_ID` — from step (a).
- `CLAUDE_DEFAULT_CWD` — a project directory. Only used in **classic mode** (see (f)) as the
  `cwd` for the headless `claude -p` subprocess; harmless to leave set even in relay mode.
- `RELAY_MODE=1` — recommended default for a coordinator setup (see (f) for why).

`.env` is never committed — see "Security" below.

## (d) Run manually to test

```bash
python3 bot.py
```

This runs exactly one poll cycle and exits (by design — see (f)). To exercise it interactively,
loop it from your shell:

```bash
while true; do python3 bot.py; done
```

Send your bot a message on Telegram and watch the terminal (and `bot.log`, written next to
`bot.py`) for activity. Ctrl+C to stop.

## (e) Install as an always-on service

Once a manual run works, install the OS-level supervisor so it runs continuously without a
terminal open.

### macOS (launchd)

1. Copy the template and fill in its placeholders:
   ```bash
   cp com.example.claude-telegram-bridge.plist.template ~/Library/LaunchAgents/com.<you>.claude-telegram-bridge.plist
   ```
2. Edit the copy: replace `<PYTHON3_PATH>` (output of `which python3`), `<BRIDGE_DIR>` (absolute
   path to this directory), `<EXTRA_PATH_DIRS>`, and the `Label` to match the filename.
   **PATH gotcha:** launchd's default `PATH` does not include nvm/homebrew-managed bin
   directories. If `bot.py` (classic mode) shells out to a bare `claude` command, that lookup
   silently fails under launchd even though it works fine in your interactive shell — you must
   list the directory `claude` actually lives in (`which claude` in a normal shell) under
   `EnvironmentVariables` → `PATH` in the plist explicitly.
3. Load it:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.<you>.claude-telegram-bridge.plist
   ```
   `KeepAlive=<true/>` (unconditional, not the "only on crash" form) is what turns the
   single-poll-cycle process into a continuously-polling service — launchd relaunches it after
   every exit, success or not. Logs: `bot.log` (app-level) and `launchd-stdout.log` /
   `launchd-stderr.log` (process-level), all next to `bot.py`.
4. To stop/uninstall: `launchctl unload ~/Library/LaunchAgents/com.<you>.claude-telegram-bridge.plist`.

### Linux (systemd)

1. Copy the template and fill in its placeholders (same three: `<PYTHON3_PATH>`, `<BRIDGE_DIR>`,
   `<EXTRA_PATH_DIRS>`):
   ```bash
   mkdir -p ~/.config/systemd/user
   cp claude-telegram-bridge.service.template ~/.config/systemd/user/claude-telegram-bridge.service
   ```
2. Enable and start it:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now claude-telegram-bridge.service
   loginctl enable-linger "$USER"   # keeps it running after you log out / close the SSH session
   ```
   `Restart=always` (not `on-failure`) is the systemd equivalent of launchd's unconditional
   `KeepAlive` — it restarts regardless of exit code, which is what turns the single-poll-cycle
   process into a continuous service. `StartLimitIntervalSec=0` in the template disables
   systemd's default restart-rate limiter, since frequent clean exits (a normal poll cycle) should
   never count against a crash-loop burst limit.
3. Logs: `journalctl --user -u claude-telegram-bridge -f`.
4. To stop/uninstall: `systemctl --user disable --now claude-telegram-bridge.service`.

## (f) How the relay loop works

`bot.py` does **not** loop internally — every invocation does exactly one Telegram `getUpdates`
long-poll, handles whatever messages came back (zero, one, or more), persists the updated offset
to `.offset.json`, and exits. The "keep polling forever" behavior comes entirely from the
supervisor (launchd/systemd) relaunching it immediately after every exit. Practical effect: every
cycle is a fresh process, so config (`.env`) and code changes on disk take effect on the very next
cycle — no restart step needed after an edit.

Two modes, switched by `RELAY_MODE` in `.env`:

- **Relay mode (`RELAY_MODE=1`, recommended for a coordinator setup).** `bot.py` reacts 👀 and
  appends one JSON line to `relay-inbox.jsonl` — `{"ts", "chat_id", "message_id", "text"}` — then
  exits. It does **not** invoke `claude`, reply, or set a final reaction. A **live** Claude Code
  coordinator session watching that file (see (g)) picks the message up, handles it in its own
  ongoing context, replies with `notify.sh`, and sets the final 👍/👎 with `react.sh`. This routes
  founder messages into the *same* session/context the coordinator is already running — not a
  second, disconnected instance. Everything is relayed as-is, including `/new` — the live session
  decides what any command means, the bot does no interpretation. **Caveat:** if no live session
  is watching the inbox, messages just queue up with a 👀 and no reply until one does.
- **Classic mode (`RELAY_MODE` unset, fallback).** Each message is handled by shelling out to a
  fresh, headless `claude -p` (or `claude -p --continue text` to keep conversation context across
  messages) — no shared context with any live/desktop session, no memory of anything the
  coordinator has already done this session. Useful if you want a Telegram-only assistant with no
  live session running, but not the recommended mode for a coordinator: the coordinator's whole
  value is the accumulated in-session context, and classic mode discards that per message.

Enable/disable relay mode by editing `RELAY_MODE` in `.env` — takes effect next poll cycle
automatically, no restart.

Along the way, `bot.py` gives live feedback in Telegram: a 👀 reaction on receipt, a periodic
"typing…" indicator while work is happening, and a final 👍 (success) or 👎 (failure) reaction.
Reaction/typing calls are best-effort — a network hiccup there is logged and swallowed, never
blocks the actual reply.

## (g) How the coordinator session hooks in (relay mode)

At the start of a coordinator session (or as soon as the bridge is confirmed installed):

1. **Arm a persistent watch on `relay-inbox.jsonl`** (e.g. this harness's `Monitor` tool watching
   the file, or an equivalent tail-and-notify loop) so new lines surface as notifications
   *mid-session*, in the same running context — not by shelling out to a fresh headless process.
2. **On each new line:** parse `{chat_id, message_id, text}`, treat `text` as a founder message
   arriving in-band (same as if they'd typed it in this chat), and act on it per the project's
   normal rules (see the kit's `CLAUDE.md` Question protocol for how the coordinator asks
   follow-ups back).
3. **Reply** with `notify.sh "<reply text>"` — resolves `.env` relative to its own script location,
   so it works regardless of the coordinator's own working directory. **Never put a backtick in
   the message text.** `notify.sh "..."` is still a shell command line, so a backtick-wrapped
   command inside the double-quoted string triggers bash command substitution and can *execute*
   the embedded text instead of just sending it as a message — describe commands in prose, or
   write the literal text to a scratch file and reference its path instead.
4. **Acknowledge** with `react.sh <message_id> ok` (👍) or `react.sh <message_id> fail` (👎) once
   the message is fully handled — this replaces the bot's initial 👀 with a final status the
   founder can see at a glance without opening the chat.
5. **Deliver files** via the Bot API directly (see the gotcha below) — the session UI's own file
   attachments do not reach Telegram.

## Gotchas

- **Reaction emoji set is curated, not free-form.** Telegram's `setMessageReaction` only accepts a
  fixed set of emoji for `type: emoji` reactions. 👍 and 👎 are in that set; ✅ and ❌ are **not** and
  are rejected with HTTP 400 `REACTION_INVALID` even though the request shape is otherwise
  correct. `react.sh` and `bot.py` both already use 👍/👎 for this reason — don't "improve" this to
  ✅/❌ without checking Telegram's current allowed-emoji list first. 👀 (the initial "seen" reaction)
  is separately in the allowed set and used as-is.
- **File delivery must go through the Bot API, not the session UI.** A file created/attached in
  the Claude Code session UI never reaches Telegram on its own — send it explicitly:
  ```bash
  set -a; source .env; set +a   # never echo $TELEGRAM_BOT_TOKEN
  curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
    -F chat_id="${TELEGRAM_CHAT_ID}" \
    -F document=@"/absolute/path/to/file"
  ```
- **launchd/systemd PATH is minimal.** Both service managers give the process a bare-bones `PATH`
  that excludes nvm/homebrew-managed bin directories. If anything shells out to a bare `claude`
  (classic mode's `bot.py`, or `daily_report.py`), that lookup fails silently unless the plist's
  `EnvironmentVariables`/`PATH` or the systemd unit's `Environment=PATH=` explicitly includes the
  directory `claude` resolves to. Check with `which claude` in your normal shell.
- **Typing indicator needs re-pinging.** Telegram's "typing…" indicator only lasts ~5s
  client-side, but a `claude -p` call (classic mode) or a real founder-relayed task can take
  minutes. `bot.py`'s `TypingIndicator` background thread re-sends `sendChatAction` every ~4s for
  this reason — if you build something similar yourself, keep the same interval.

## (h) `notify.sh` standalone

`notify.sh` works independently of `bot.py` — a generic "ping my phone" utility, usable from any
shell session, Claude Code hook, or cron job on the machine, resolving `.env` relative to its own
location regardless of the caller's working directory:

```bash
<BRIDGE_DIR>/notify.sh "some message"
```

Same caution as in (g): never put a backtick inside the quoted message — it triggers bash command
substitution on that double-quoted string and can execute whatever's between the backticks instead
of just sending it as text. Describe commands in prose, or point at a scratch file instead.

## (i) Optional: daily activity digest

`daily_report.py` is a separate one-shot script (not part of `bot.py`'s poll loop): once a day it
summarizes what landed in `CLAUDE_DEFAULT_CWD` since the last successful report (via `git log
--oneline`, fed to a one-shot, non-`--continue` `claude -p` call for a readable summary) and sends
it to Telegram. It tracks its own "last reported" commit marker (`.last_report`), only advancing it
after a successful send, so a failed send never silently drops a day's activity.

Skip this entirely if you don't want it — nothing else in this directory depends on it. To install
it as a scheduled job: macOS, copy+fill in
`com.example.claude-telegram-bridge-daily-report.plist.template` and `launchctl load` it (see (e)
for the placeholder-filling pattern); Linux, copy+fill in both
`claude-telegram-bridge-daily-report.service.template` and the matching `.timer.template`, then
`systemctl --user enable --now` the `.timer`. Both default to 8:00 AM local time — edit the
Hour/Minute (launchd) or `OnCalendar` (systemd) values to change it.

## Security

- **Never commit `.env`.** It holds your bot token; `.gitignore` in this directory already
  excludes it, `.offset.json`, `.last_report`, and `relay-inbox.jsonl` — verify with
  `git status --ignored` if unsure.
- **Treat the bot token like a password, with one narrow exception.** Anyone with it can
  send/receive messages as your bot. Pasting it to the installing/coordinator agent in chat during
  setup (step (a)/(c) above) is the intended flow — the agent writes it straight into the
  gitignored `.env` and nowhere else: never committed, never echoed back, never logged, never
  stored in a memory file or `STATE.md`. Outside that one setup moment, never print it, log it, or
  put it in a committed file.
- **Chat id allowlisting is the only auth.** `bot.py` compares every incoming message's chat id
  against the single `TELEGRAM_CHAT_ID` in `.env`; anything else is logged as rejected and never
  processed. There's no password/signature layer on top of that — keep `TELEGRAM_CHAT_ID` correct
  and don't share the bot token, since a relay-mode bridge effectively gives the authorized chat
  remote access to whatever the coordinator session can do.
- `.offset.json` and `.last_report` are gitignored local runtime state, not secrets — regenerated
  automatically, nothing to commit either way.

## Reusing this bridge across projects

This bridge is machine-level, not per-project — one Telegram bot and one running service can
serve every coordinator session on the machine. Two options when starting a new project:

- **Reuse the existing bridge** (simplest): point the new project's coordinator at the same
  `notify.sh` / `react.sh` paths and the same `relay-inbox.jsonl`. All projects' founder messages
  land in one Telegram chat, disambiguated by whichever coordinator session is actually watching
  the inbox at the time (only run one relay-mode coordinator session against a given inbox at
  once, or messages may be picked up by the wrong session).
- **Create a second bot** (channel separation): repeat step (a) with a new BotFather bot, install
  a second copy of this directory (or a second `.env` alongside it) pointed at the new token, and
  run a second instance of the service under a different `Label`/unit name. Gives each project its
  own Telegram chat thread, at the cost of a second always-on process to maintain.
