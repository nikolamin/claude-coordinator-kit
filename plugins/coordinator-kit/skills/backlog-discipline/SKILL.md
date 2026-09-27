---
name: backlog-discipline
description: Route coordinator follow-ups and external signals into the canonical task record, check stale ticket premises, and preserve the founder's original intent. Use at intake or when an agent discovers work outside its current scope.
---

# Backlog discipline

Use the bundled `.coordinator/coord.db` through `coordinator-kit:coordination-state`.
First-run migration replaces the legacy plan/state/decision companions. No suggestion-chip tools,
unrequested user tasks, scratch-file backlog, or list only the coordinator remembers.

A founder message, crash report, ticket, monitor alert, or agent discovery becomes a task or an
event on an existing task. Record source id and verbatim requirement (redact secrets), goal,
acceptance criteria, dependency, priority, scope and next action. Tracking a signal does not
authorize every proposed remedy; apply the project's approved scope and hold rules.

## Define, prioritize, queue

For a substantive new request, dispatch a bounded read-only definition first: exact outcome,
affected repositories, dependencies, acceptance criteria and unresolved choices. Definition is
not permission to implement. Then assign priority and `queue_pos` in the database and tell the
user its priority and place: after N tasks, or name the preceding tasks when there are few.
Queue new work behind active commitments unless the user explicitly changes priority or an
established incident policy applies. Do not interrupt running lanes just because a new message
arrived. Use the recorded queue order when dependencies permit; update a changed position and
its reason rather than silently reshuffling. A queue position is not a delivery-time promise.

An incidental finding outside the requested goal becomes a sourced task/evidence record, not
another investigation or fix chain. Continue only when it is necessary for the authorized goal
or falls within an established incident-response grant. Severity alone supplies no new scope.
Keep a paused finding paused until its own hold is lifted.

Before dispatching an old item, search the live record and resolved decisions, then have the
agent cheaply verify its premise against current behavior. A suggested fix also contains a
causal hypothesis: "make A match B" may name the wrong side. Already shipped or disproven items
get corrected with evidence at their original record so the next session cannot rediscover them.
A repeatedly cited access blocker deserves a fresh check against existing grants and tooling.

Keep the entire user goal visible across repository tasks. A half-shipped integration or an
on-test change awaiting production approval remains distinguishable from done. Record follow-up
ownership and next steps yourself; do not hand the user an audit list they must manage.

When verified work is on test and only release approval remains, use `awaiting_release`, record
`release_target` and verification evidence, and link a queued question through its `tasks` ids.
If the user has said they will initiate that next action, set `user_initiated: true` and retain
the current environment/status; do not ask, remind, dispatch it or call it "waiting on you".
This is a recorded preference for that action, never a blanket rule for a particular platform.
Set `needs_user: true` only for a concrete remaining user decision/action, not ordinary work.

Agents return findings or append task events only; the coordinator owns task status, priorities,
dependency changes and closure. Put this no-side-backlog rule in each dispatch brief.
