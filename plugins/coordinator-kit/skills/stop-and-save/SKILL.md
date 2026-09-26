---
name: stop-and-save
description: Honor a coordinator stop request, preserve in-flight work and pending decisions, and write a durable handoff. Use on "stop and save your step" or equivalent; bootstrap handles the subsequent resume.
---

# Stop and save

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
