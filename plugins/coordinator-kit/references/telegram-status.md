# Telegram idle-status updater

Use the bundled `scripts/telegram_status.py` when a project requests an automatic Telegram
status post. It sends a silent post after 30 minutes without an exchange, edits the same post
every 30 minutes, and deletes it after the next recorded exchange. Both intervals are configurable.
The post groups active lanes by task and uses fresh `public_summary` / `summary_updated_at`
fields. Missing summaries or stale ownership are reported as gaps, never as completed work.

This is an executable sender component, not an inbox receiver. It never calls `getUpdates`,
launches a model, installs a daemon or creates a scheduler. Reuse the existing bridge's receiver
and process supervision. Do not start a second status publisher for the same bot/chat. Installing
the plugin alone leaves the feed disabled; enable only the project's requested recipient.

## Configure and preview

Run database bootstrap first. Resolve `STATUS_SCRIPT` to this installed plugin's
`scripts/telegram_status.py` and `WORKSPACE` to the project's existing coordinator root.
Use an environment/secret-store injection for `TELEGRAM_BOT_TOKEN` (or another chosen variable).
Never pass the token in argv, print it, or put it in the database. Credentials are not copied
from another project. The sender supports a numeric private chat id, not a group or channel.

```sh
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" configure \
  --chat-id "$AUTHORIZED_CHAT_ID" --token-env TELEGRAM_BOT_TOKEN \
  --timezone "$PROJECT_TIMEZONE" --source "$AUTHORIZATION_SOURCE"
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" preview
```

`configure` preserves other profile fields and records the authorization source. The default
silence/refresh intervals are 30 minutes, summary freshness 6 hours and lane freshness 24 hours.
Configure them with `--interval-minutes`, `--refresh-minutes`, `--summary-max-age-minutes` and
`--lane-max-age-minutes`. The timezone defaults to UTC; choose the project's actual
IANA timezone. On systems without a timezone database, UTC works through the standard library.
Configuration and preview make no Telegram calls. Inspect the preview before first activation.

## Integrate with an existing bridge

Import from the resolved plugin scripts directory, or invoke the same commands as subprocesses.
Use the active installed version's path; restart the supervised process after a plugin upgrade.

```python
from telegram_status import IdleStatus

status = IdleStatus(workspace)
# After an inbound message/button passes the bridge's sender/chat checks and durable receipt:
status.exchange("inbound", f"{bot_id}:update:{update_id}", at=original_iso_timestamp)
# After Telegram confirms an ordinary outbound message/file/question send:
status.exchange("outbound", f"{bot_id}:message:{sent_message_id}")
# At the end of every poll, including an empty poll:
outcome = status.tick()
```

The receiver must validate sender/chat identity before calling `exchange`; the status module
does not interpret raw Telegram updates. Use stable ids including the public bot id, preserve
the original inbound timestamp, and never mark a rejected or merely attempted send as delivered.
Typed messages and accepted button answers count. Typing, reactions and idle-post sends/edits
do not. Record the inbound exchange before advancing the receiver's durable cursor, so an
interruption replays safely. Duplicate/old exchanges do not restart the silence timer.
Isolate status errors from durable message delivery; log only fixed error categories, never
exception strings that may carry credential-bearing URLs. Surface a persistent integration
failure to the coordinator instead of claiming the feed is healthy.

The equivalent exchange command is:

```sh
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" exchange \
  --direction inbound --event-id "$STABLE_UPDATE_ID" --at "$ORIGINAL_ISO_TIMESTAMP"
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" tick
```

If the bridge cannot call `tick`, its existing supervisor can run:

```sh
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" run --poll-seconds 15
```

The sender loop still requires the bridge's exchange hooks; without them it cannot know a
conversation resumed. It runs in the foreground and emits changes in status only. A terminal
command is not an installed service. Record its real supervisor/owner in the workspace profile.
The same workspace lock serializes concurrent ticks and exchanges; no SQLite transaction is
held during network calls. Do not run separate coordinator databases for the same bot/chat.

## State, recovery and disabling

All authoritative state stays in `.coordinator/coord.db`: configuration in the workspace
profile, exchange receipts in events, and timers/post identity/action journal in the
`telegram_idle_status.v1` meta entry. The lock file stores no authoritative state. Existing
schema-1 databases need no table rebuild; no JSON state, timestamp or summary companion is added.
Read-only `preview` does not initialize or migrate a missing database.

Restarting resumes editing the recorded post. Known transient failures back off; the post is
rotated before Telegram's deletion-age limit. A real exchange takes priority over an earlier
send/edit backoff. Only confirmed deletion or a confirmed missing post clears its identity.

A send interrupted after Telegram may have accepted it has an **unknown outcome**. The journal
stops automatic resending instead of creating duplicate posts. `tick` returns `reconcile_send`;
inspect the authorized chat and record the observed message id or confirmed absence:

```sh
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" reconcile \
  --message-id "$OBSERVED_MESSAGE_ID" --source "$OBSERVATION_EVIDENCE"
# Use --absent instead only after confirming the outstanding post is absent.
```

A post Telegram cannot delete requires the same observed reconciliation; it is not silently
forgotten or replaced. Never use `--absent` to clear an inconvenient error. Telegram does not
offer exactly-once sending through this component. An API delivery receipt is not a guarantee
that the human read the message.

```sh
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" disable --source "$STOP_SOURCE"
python3 "$STATUS_SCRIPT" --root "$WORKSPACE" tick
```

Disable stops new posts; the next tick deletes the existing one using its original bot/chat.
Keep that credential available for cleanup. Changing the recipient or token variable while a
post/action is outstanding is refused. A stopped process leaves durable state for the next
owner; do not claim cleanup until `preview` confirms no outstanding post/action.

Commands emit JSON; exit 0 means the operation succeeded or no action was due, exit 2 signals
an unresolved retry/reconciliation/state issue, and exit 1 is an invalid configuration/runtime
failure. Check `action` as well as exit status. The loop reports those outcomes for its supervisor.

API reference: [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage),
[editing](https://core.telegram.org/bots/api#editmessagetext),
[deletion](https://core.telegram.org/bots/api#deletemessage).
