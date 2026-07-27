---
name: feedback-coordinator-autonomy-on-recovery
description: "User does not want to be asked before re-dispatching a lost/stuck/failed agent, or before starting the next unblocked plan task - that's routine coordination, handle it and keep going."
metadata:
  type: feedback
---

Re-dispatching lost/stuck/failed agents, re-prompting after a bad result, retrying a transient
failure, or starting the next unblocked task from the plan — this is routine execute-phase
mechanics per the build→verify→re-prompt loop, not a strategic or irreversible decision. Asking
for sign-off on it is noise, not diligence.

**Why:** the plan document already names the next unblocked task and its dependencies; asking
"what's next" when the plan answers that itself is the same class of noise as asking to
re-dispatch a lost agent. The build/engine portion of a task is not itself a decision point, even
for a large multi-agent task — only the pieces that explicitly require the user in the loop
(a live playthrough/demo, a public go-live) are.

**How to apply:** when an agent is lost, silently fails, or a task needs a straightforward retry/
re-dispatch, just do it — don't stop to ask. After closing one plan task, immediately dispatch the
next unblocked one per the plan's dependency graph, without an intervening turn asking permission.
This is distinct from genuinely novel decisions (which direction to build, whether to go live
publicly, which environment/target to deploy to) — those still warrant a check. The line: if the
answer is "obviously yes, keep the pipeline moving," don't ask; if it's a real fork with
user-only judgment, do ask. Report progress via checkpoint notifications rather than by pausing
and waiting for acknowledgment.

This autonomy is not unlimited retrying: it covers re-dispatch/re-prompt mechanics, not overriding
an escalation trigger. Once the Execute loop's retry cap is hit — 2 failed re-prompt/respawn
cycles on the same gap — that's a stuck-escalation case (see the escalation-protocols memory), not
another silent retry.

One more exception, orthogonal to escalation: if the founder has recorded a suspension of
autonomous dispatch (`CLAUDE.md`'s Execute loop and Watchdogs sections; the record lives in
`STATE.md`'s Durable decisions), that suspension overrides this file's default — report status on
any lost/stuck/failed agent or newly-unblocked task instead of re-dispatching, until the founder
explicitly lifts it.

Note the "live playthrough/demo" that stays user-only is the user's own attendance/participation
(e.g. a final go/no-go session) — distinct from an agent's own pre-send verification playthrough
(see the verify-by-playing memory), which is mandatory, always agent-executed, and never something
to defer to the user.
