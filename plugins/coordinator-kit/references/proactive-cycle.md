# Required coordinator cycle

Run this cycle on bootstrap/resume, every incoming request or answer, agent completion/failure,
verification/release result, and watchdog wakeup. Run it again before ending an operating turn
or waiting. A status reply, saved report or completed batch does not end the operating loop.
An explicit user stop takes precedence: use stop-and-save without launching another cycle.

## Act on both queues

1. Reconcile new messages and agent evidence once. Apply an answer to its exact saved question,
   update affected tasks/holds within that answer's scope, and retain independent active lanes.
   Do not ask whether to start work the user already requested or approved.
2. Read `summary`, `status` and `sweep`. Resolve stale/answered/parked question records before
   creating another ask. Complete authorized preparation for missing release/user decisions,
   then create their linked queued question records now; a note saying "needs approval" is
   insufficient. Respect actions explicitly reserved for user initiation.
3. If no question is presented, **ask the next valid queued question in this turn** using the
   supported question UI or authorized channel. Save actual delivery/outbound id afterward.
   Do not merely list it, promise to ask later, wait for the user to request it, or finish with
   "let me know". If a question is already presented, keep that one and avoid duplicate asks.
   An unanswered question blocks only its dependent work, not independent tasks.
   Prefer a supported asynchronous question path when available. If the question UI blocks
   the turn, perform steps 4–5 for independent work before opening it, then ask in this same
   turn; do not wait for those agents to finish first. Never open a blocking prompt while
   independent ready work could take free capacity.
4. Check current worker, checkout and shared-resource capacity. Unknown capacity requires a
   check; it does not justify assuming the fleet is full. Run `sweep --available-slots N` with
   the observed number. Define and prioritize unprepared requests through backlog-discipline;
   select prepared work in recorded order, skipping genuinely blocked items. An unranked new
   request must get intake, not disappear because it lacks `queue_pos`.
5. **Use available capacity for authorized, unblocked work now.** Claim a lane, dispatch the
   bounded agent and record its actual handle/ownership. Do not wait for another permission
   to continue, the whole batch to finish, or the pending question to be answered if this task
   is independent. Preserve active commitments; do not preempt them just to take new work.
   Check a hold against each candidate's scope: an unrelated hold is not a global suspension.
6. Repeat after those state changes until the valid question slot is occupied or empty and
   available capacity is filled or no authorized runnable/definable work remains. Work already
   assigned to a live owner is not dispatched again. If action cannot proceed, record the exact
   task, blocker, evidence and next trigger. Never invent a blocker or change status merely to
   make a check pass.

## Before waiting

Run `sweep --available-slots N --check-idle` after the actions above. It still only reads state:
exit 0 means no recorded follow-up item remains, exit 2 means act/reconcile or account for the
specific blocker, and exit 1 means the check failed. A passed check does not verify permissions,
native liveness or monitor delivery; those checks still belong to the coordinator.

Do not stop at reporting actionable sweep output. A valid wait requires one of: all available
capacity is genuinely occupied, remaining work has a recorded dependency/user/access/hold
blocker, or the authorized queue is exhausted. Preserve supported listeners/completion events
and an authorized fallback wakeup when required; record its real id. If the runtime cannot
continue after the turn, state that limitation instead of claiming background work is armed.
An explicit stop/suspension is honored even when the idle check reports work.

When the authorized queue is exhausted, no work is in flight and no decision is pending, ask
once for the next goal through the same question protocol and keep intake open. Record that
ask so each wakeup does not repeat it. Ask again only after new work has been completed or
the user reopens intake. Do not invent new projects, revive parked findings, or create a
user-owned Codex task without its required explicit request.

Quiet reporting suppresses routine progress pings, not required questions or authorized work.
Use the established channel and notification policy; do not contact new recipients or repeatedly
nudge an already-delivered unanswered question. A dispatch candidate or idle check never grants
release, production, spending or other missing authority.
