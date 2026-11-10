---
name: stop-and-save
description: Honor a coordinator stop request, preserve in-flight work and pending decisions, and write a durable handoff. Use on "stop and save your step" or equivalent; bootstrap handles the subsequent resume.
---

# Stop and save

**Context cap: checkpoint and continue, never a new session.** Coordinator cost is mostly
re-reading its own context on every turn, but the user must not have to open sessions to keep the
coordinator running. When the context guard reports the coordinator over its checkpoint cap
(default 450k tokens), or at a batch close after roughly 20 dispatches or 4 hours, checkpoint on
your own initiative and keep working in the same session: do steps 3–5 below (reconcile results,
write or update the active `handoff` record, take the backup) without a hold and without stopping
dispatch, then continue the proactive cycle. The host's compaction is the reset. Before it, the
PreCompact hook refreshes `handoff-auto-checkpoint` from canonical state, takes a backup and
commits the designated snapshot. After it, the SessionStart `compact` hook tells you to re-read
`summary`, the handoffs, the lanes and the presented question. Agents launched before compaction
still report to this session. Never ask the user to open a new session. Record founder instructions and answers in the database as they arrive, so the transcript
never holds the only copy, and keep agent briefs and reports small.

The full stop-and-save below, ending in a fresh session through bootstrap, applies only to an
explicit user stop, or to a host that cannot compact (then say so and save as a session handoff;
a self-initiated handoff records no hold).

An explicit stop overrides the proactive cycle. Do not ask a next-goal question or dispatch
new work to clear `sweep --check-idle`; preserve those pending actions in the handoff instead.

1. Stop new dispatch and record the founder's exact instruction, scope, time and source as an
   active hold in the canonical state. Say whether this is a session handoff or a broader hold;
   don't silently broaden it. A later explicit resume lifts only the matching scope.
2. Read native in-flight agent status and latest available outputs. Ask existing agents to
   checkpoint at a safe boundary if the instruction permits; cancel when requested or needed
   to stop harmful effects. Do not mark them finished from an elapsed estimate. No new
   investigation agent while suspended unless the stop request authorizes that cleanup.
3. Reconcile completed results into task records. For remaining agents, preserve ids, lane,
   stage, latest report, active child processes, mutation markers/backups and resource ownership.
   Do not infer a clean tree from a killed-agent notification. Unknown tree state is a named
   first resume check, not a fabricated fact.
4. Write an active `handoff` record in the database with:
   - Each repo/checkout's measured revision/push state, or explicitly unverified state.
   - Uncommitted paths and what they were intended to become, with checkpoint/patch locations.
   - Outstanding questions, exact options, source/message ids, active holds and scopes.
   - Ordered resume actions, including liveness/ownership and mutation-restoration checks.
   - What landed, in which environment, and what still prevents the user's goal being complete.
   - Durable lessons or evidence not yet recorded elsewhere.
5. Persist canonical records and their human view via `coordinator-kit:coordination-state`.
   Create a consistent SQLite backup and commit only that bookkeeping snapshot in its owning repo; a multi-repo workspace root may
   not be a repo. Do not opportunistically commit or push unverified product work.
6. Record which session listeners end, which durable jobs/dated obligations survive, and who
   owns them. Do not cancel a required durable obligation or claim a session monitor survives.
   Confirm the saved handoff and any unresolved persistence/ownership issue concisely.

Resume uses `coordinator-kit:bootstrap`: read the saved handoff, reconcile actual state, honor or
explicitly lift the matching hold, then resolve the handoff record only after its actions are complete.
