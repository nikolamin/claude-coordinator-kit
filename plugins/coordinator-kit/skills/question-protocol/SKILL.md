---
name: question-protocol
description: Present one coordinator decision at a time, correlate terse replies to their exact question, and preserve approval scope. Use for an actual founder-only choice or blocker, not routine authorized work or a status answer.
---

# Question protocol

Use the [required coordinator cycle](../../references/proactive-cycle.md) on every answer and
wakeup. Asking the next pending question is an action for the current turn, not a suggestion
for a future status report. Keep independent authorized work moving while its answer is pending.

First check current decisions, authorization and agent evidence. Do not ask the founder to
answer something the code/records can establish or to approve routine recovery already granted.
Prepare the concrete reviewable proposal and complete its authorized prerequisites before asking.

Present one question with: brief context (what it blocks and why now), your reasoning, two to
four meaningful options with a recommendation when useful, and the safe action while waiting.
Use a direct short question instead of artificial options when there is no real choice.
Silence never supplies approval; normally the dependent action remains pending.

Record the exact question/options under a stable id with the outbound message id and scope.
Keep one presented question at a time; others remain queued. A pending decision holds its
channel topic too: do not mix in an unrelated numbered list that could make "2" ambiguous.
Continue work that does not depend on the answer. Explicit "park this" closes the presented
slot without approving its proposed action.

Link the question to its canonical `tasks` ids. Queued means prepared but not sent; presented
means actually shown/sent, with its outbound id saved. After an answer or explicit park, promptly
present the next still-valid queued question on the authorized channel, then record delivery.
Do not wait for another status request or mark it presented just because it is next in the DB.
One at a time limits concurrent decisions; it does not justify letting the queue sit idle.

"What is waiting on me?" gets the queue count and the current/top question alone, not a list of
separate decisions disguised as status. Work whose sole remaining step is release approval
enters this queue as soon as verification closes. Exclude actions marked `user_initiated`:
the user's instruction to initiate it themselves also means not proposing it as the next ask.

Before acting on a terse reply, inspect reply-to/thread context and the recorded options.
Check that the referenced question is still actionable: a superseded proposal, already-applied
answer or invalidated option is not reactivated by a late reply. Record the late answer and
clarify the current choice when needed; never replay an irreversible action from duplicate input.
If it could refer to multiple questions, ask the narrow clarification rather than guessing.
Store the verbatim answer/source, resolve the queue item, and update any affected original
hold in place with its superseding decision. Approval applies to the named action/scope, not
other environments or the whole backlog.

Use the harness's supported question UI in-app; use the same structure as plain text over the
authorized bridge. Prefer a supported asynchronous question path. Before a blocking question
call, check capacity and dispatch independent ready work; then ask in the same turn without
waiting for those agents to finish. Status messages follow `coordinator-kit:comms-register`.
