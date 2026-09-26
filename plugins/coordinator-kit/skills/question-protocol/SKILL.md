---
name: question-protocol
description: Present one coordinator decision at a time, correlate terse replies to their exact question, and preserve approval scope. Use for an actual founder-only choice or blocker, not routine authorized work or a status answer.
---

# Question protocol

First check current decisions, authorization and agent evidence. Do not ask the founder to
answer something the code/records can establish or to approve routine recovery already granted.
Prepare the concrete reviewable proposal and complete independent authorized work first.

Present one question with: brief context (what it blocks and why now), your reasoning, two to
four meaningful options with a recommendation when useful, and the safe action while waiting.
Use a direct short question instead of artificial options when there is no real choice.
Silence never supplies approval; normally the dependent action remains pending.

Record the exact question/options under a stable id with the outbound message id and scope.
Keep one presented question at a time; others remain queued. A pending decision holds its
channel topic too: do not mix in an unrelated numbered list that could make "2" ambiguous.
Continue work that does not depend on the answer. Explicit "park this" closes the presented
slot without approving its proposed action.

Before acting on a terse reply, inspect reply-to/thread context and the recorded options.
Check that the referenced question is still actionable: a superseded proposal, already-applied
answer or invalidated option is not reactivated by a late reply. Record the late answer and
clarify the current choice when needed; never replay an irreversible action from duplicate input.
If it could refer to multiple questions, ask the narrow clarification rather than guessing.
Store the verbatim answer/source, resolve the queue item, and update any affected original
hold in place with its superseding decision. Approval applies to the named action/scope, not
other environments or the whole backlog.

Use the harness's supported question UI in-app; use the same structure as plain text over the
authorized bridge. Status messages follow `coordinator-kit:comms-register`.
