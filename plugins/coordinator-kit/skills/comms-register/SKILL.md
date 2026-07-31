---
description: How the coordinator talks to the founder outside of asking a question — leading
  with the actionable fact, what a status answer looks like (short, direct, counts not prose,
  closing with whether the founder is needed), why the notify channel is written for a
  phone screen (short, plain text, no markdown tables or wide output), the difference between a
  batch-level checkpoint ping and an immediate ping for something that genuinely needs the
  founder now, the one-ask-per-ping rule, the never-put-a-backtick-in-a-notify-message rule and
  why (a double-quoted shell call can execute backtick-wrapped text instead of displaying it),
  and the concrete notify-channel script invocations (notify.sh, react.sh, typing.sh,
  send-file.sh) for a Telegram-bridge-style setup. Load this when drafting any status update,
  checkpoint ping, or immediate ping, or when formatting text for a notify script. Not for
  deciding whether a message should be a question at all (see
  coordinator-kit:question-protocol) — this is the format and cadence once you already know you
  are sending one.
---

# Comms register

Lead with the actionable fact. Status answers look like: *"Yes. 1 agent running: X. Queued next:
Y. Nothing needs you."* — direct answer, counts not prose, one line per fact, close with whether
the user is needed. Save narrative framing for genuinely new decisions that need context. The
notify channel is typically read on a phone — keep messages short and plain text, no markdown
tables or wide output.

Notifications on `<NOTIFY_CHANNEL>`:
- **Checkpoint ping** when a batch of work closes and pushes (batch-level, not per-task).
- **Immediate ping** the moment something genuinely needs the user (blocking decision, required
  live playthrough, escalation) — don't wait for the next checkpoint.
- **One ask per ping.** Maintain a queue if multiple items need attention; send the top one,
  wait for resolution, send the next. Checkpoint pings stay status-only — don't tack on a
  request list. This is `coordinator-kit:question-protocol` applied over the notify channel
  specifically.
- **Never put a backtick in a notify message body.** A double-quoted `notify.sh "..."` call is
  still a shell command line — backtick-wrapped text inside it triggers bash command
  substitution and can *execute* the embedded text instead of just displaying it. Describe
  commands in prose, or write the literal text to a file in `.coordinator-scratch/` and
  reference its path instead of quoting it inline.

**If the Telegram bridge is installed (at `<BRIDGE_DIR>` — see `<BRIDGE_DIR>/SETUP.md`) and
`<NOTIFY_CHANNEL>` is it:**
- Arm a persistent Monitor on `<BRIDGE_DIR>/relay-inbox.jsonl` at session start — create the
  file first if it doesn't exist yet (`touch`), since it's gitignored and only created once the
  first message actually arrives; a Monitor armed on a missing file has nothing to watch.
  Founder messages arrive **mid-session**, into this same running context, not via a separate
  headless process. Re-arm it if the session is ever resumed.
- Signal "still working" via `<BRIDGE_DIR>/typing.sh [seconds]` as soon as a relayed message is
  picked up but a reply isn't ready yet — the initial acknowledgment reaction alone gives no
  progress signal on a long turn.
- Reply via `<BRIDGE_DIR>/notify.sh "<text>"`.
- Acknowledge each relayed message with `<BRIDGE_DIR>/react.sh <message_id> ok|fail` (sets the
  final ok/fail reaction, replacing the bot's initial acknowledgment).
- Deliver file deliverables via `<BRIDGE_DIR>/send-file.sh <path> [caption]` (see
  `<BRIDGE_DIR>/SETUP.md`) — a file produced in the session UI does not reach the notify channel
  on its own. Run it as an ordinary script, same as `notify.sh`/`react.sh` — never hand-roll a
  raw API call against the notify channel's provider directly; that would collide with the
  installed `CLAUDE.md`'s Role section investigative-Bash prohibition and go around this narrow
  notification-sending exception.
