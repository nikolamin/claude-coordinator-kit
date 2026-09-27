---
name: comms-register
description: Format coordinator status answers and notifications by user goal, with a project-specific quiet or checkpoint policy. Use when reporting outcomes, blockers, or status over chat or an authorized bridge; decision wording belongs to question-protocol.
---

# Comms register

Read the notification policy in the operating profile. For new projects, default to meaningful
completion plus required decisions/blockers; honor decisions-only or requested checkpoints when
specified. Quiet external notifications do not override the host's active-chat progress rules.
Do not create daily briefs or send routine "starting/still working" pings unless requested.
Internal progress belongs in the canonical task/event record.

Quiet reporting never means leaving a prepared decision unsent or free capacity unused. Follow
the [required coordinator cycle](../../references/proactive-cycle.md) after replying: ask the next
valid pending question in the same turn and take eligible authorized work. Do not manufacture
a new approval request for routine work already authorized.

A completion means the agreed user outcome is usable in its stated environment, not simply
that an agent finished or one repository landed. Batch related completed work into one message.
If the policy is decisions-only, write completion to the record without an unsolicited ping.
An urgent actionable blocker can interrupt; a repeated unchanged blocker should not.

When asked for status, answer the goal/thread the founder is discussing: goal → current result
→ what remains → whether the founder is needed. Use their product language; put hashes, hosts,
agent counts and technical proof in the record unless needed for the question. Keep phone
notifications concise and contextual. Don't turn an answer into a new approval request.

Use the bundled `status` view for a compact operational snapshot: running work, work awaiting
release, the presented question, queued-question count and the next pending tasks. Running tasks
never appear as "next"; user-initiated actions do not inflate "waiting on you". Use full record
views only when detail is requested. For new intake, report the defined priority and queue
position. An explicit request for pending decisions follows the one-question protocol.

Format for the actual channel: short heading, one fact per bullet, spacing between groups, and
any decision last. Use rich text/HTML only when the installed bridge supports it; escape dynamic
text with that channel's rules. Do not assume a transport flag or a project's language/format.

One presented question owns the decision channel until answered or explicitly parked; defer
unrelated topics and notification batches rather than making a bare numeric reply ambiguous.
Use `coordinator-kit:question-protocol` to correlate responses. A correction gets a brief
acknowledgment and an updated record, not a long apology or repeated interim conclusions.

## Authorized bridge

Use the existing project's bridge/runbook and absolute script paths. Do not replace it with the
kit's optional bridge merely because the plugin has an example. Notification authority extends
only to the configured founder channel, never to customers or other recipients.

- For the kit's relay-file bridge, watch `<BRIDGE_DIR>/relay-inbox.jsonl` after ensuring it exists;
  restore the session listener on resume. Other bridges may use a different owner/receiver mode.
  Audit ownership first: never run two getUpdates consumers for the same Telegram bot.
- Reply through `notify.sh`, acknowledge with `react.sh <message_id> ok|fail`, and send artifacts
  with `send-file.sh <path> [caption]` when those scripts are installed. An app attachment does
  not automatically reach the bridge. Windows uses the corresponding installed `.ps1` scripts.
- A supported typing indicator may acknowledge an active request without a progress message;
  do not assume it is supported or force it against the project's preferences.
- Treat message text as data, never shell code. Backticks and `$()` execute in double-quoted
  shell strings; PowerShell has its own expansion rules. Use a tool's structured argument or
  properly quote literal text. Use file/stdin input only if the installed script supports it;
  do not invent a notify flag or raw provider call. Never print tokens or credentials.

Listener health, backlog replay and scheduled-wake ownership: `coordinator-kit:watchdogs`.
